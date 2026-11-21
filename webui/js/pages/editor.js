/* MarkNest for TOS - the editor.

   The writing surface is the committed CodeMirror 6 bundle (window.MDEditor);
   everything around it is this module. Four things are worth stating because
   they are the parts a rewrite tends to lose:

   * Saving is optimistic and revision-checked. `base_rev` is the revision the
     loaded content came with, so a note changed elsewhere comes back as code
     3007 and is surfaced in a banner with three honest choices: overwrite,
     reload, or save a copy. Nothing is discarded silently.

   * Images are uploaded before they are referenced. The backend stores them in
     `.assets/` beside the note folder and returns the Markdown to insert, so
     the editor never invents an attachment path.

   * The preview is not a second parser. It calls Render.markdown, the same
     function the reader uses, and its images are hydrated through the same
     authenticated cache.

   * Leaving with unsaved work is guarded. A saved note is autosaved on the way
     out; a draft with nowhere to go asks before it is dropped. */

(function (global) {
  'use strict';

  var state = {
    note: null,
    editor: null,
    dirty: false,
    saving: false,
    conflict: false,
    draft: true,
    mode: 'split',
    outlineOn: true,
    outline: [],
    previewTimer: null,
    outlineTimer: null,
    autosaveTimer: null,
    refreshTimer: null,
    syncGuard: 0,
    lastSaved: 0,
    mounted: false,
    nodes: {},
    onBeforeUnload: null
  };

  function mount(host, params) {
    reset();
    state.mounted = true;
    var path = (params && params.p) || '';

    var page = UI.el('div', { class: 'page page-editor' });
    host.appendChild(page);
    state.nodes.page = page;
    build(page);
    setMode('split');

    Shell.setActions([]);
    Shell.setTitle(path ? Render.stemOf(path) : I18N.t('editor.untitled'));
    Shell.setCrumb(crumbFor(path));
    Router.setGuard(guard);

    state.onBeforeUnload = function (event) {
      if (state.dirty) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    global.addEventListener('beforeunload', state.onBeforeUnload);

    if (path) {
      loadNote(path);
    } else {
      startDraft();
    }
  }

  function reset() {
    if (state.editor) {
      try {
        state.editor.destroy();
      } catch (error) {
        /* already gone */
      }
    }
    clearTimers();
    if (state.onBeforeUnload) {
      global.removeEventListener('beforeunload', state.onBeforeUnload);
      state.onBeforeUnload = null;
    }
    state.note = null;
    state.editor = null;
    state.dirty = false;
    state.saving = false;
    state.conflict = false;
    state.draft = true;
    state.outline = [];
    state.lastSaved = 0;
    state.nodes = {};
  }

  function unmount() {
    Router.clearGuard();
    reset();
    state.mounted = false;
  }

  function setDocumentTitle(params) {
    Shell.setTitle((params && params.p) ? Render.stemOf(params.p) : I18N.t('editor.untitled'));
  }

  function clearTimers() {
    global.clearTimeout(state.previewTimer);
    global.clearTimeout(state.outlineTimer);
    global.clearTimeout(state.autosaveTimer);
    global.clearTimeout(state.refreshTimer);
    state.previewTimer = null;
    state.outlineTimer = null;
    state.autosaveTimer = null;
    state.refreshTimer = null;
  }

  function crumbFor(path) {
    if (!path) {
      return [
        { label: I18N.t('nav.library'), href: Router.href('library', {}) }
      ];
    }
    // The top bar carries the folders only; the note name is the heading.
    return Shell.folderCrumb(Render.folderOf(path));
  }

  /* ----------------------------------------------------------------- build */

  function build(page) {
    var nodes = state.nodes;

    nodes.banner = UI.el('div', { class: 'conflict-banner', id: 'editor-banner', hidden: true }, [
      UI.el('span', { class: 'conflict-text' }, [
        UI.el('span', { class: 'conflict-title', text: I18N.t('editor.conflictTitle') }),
        UI.el('span', { text: I18N.t('editor.conflictBody') })
      ]),
      UI.el('button', {
        type: 'button',
        class: 'btn btn-primary',
        text: I18N.t('editor.overwrite'),
        onclick: function () { save(true); }
      }),
      UI.el('button', {
        type: 'button',
        class: 'btn',
        text: I18N.t('editor.reload'),
        onclick: reloadNote
      }),
      UI.el('button', {
        type: 'button',
        class: 'btn',
        text: I18N.t('editor.saveCopy'),
        onclick: saveCopy
      })
    ]);
    page.appendChild(nodes.banner);

    nodes.notice = UI.el('div', { class: 'editor-notice', hidden: true }, [
      UI.icon('alert'),
      UI.el('span', { text: I18N.t('editor.readOnlyHint') })
    ]);
    page.appendChild(nodes.notice);

    var head = UI.el('header', { class: 'editor-head' });
    head.appendChild(UI.el('button', {
      type: 'button',
      class: 'icon-btn editor-back',
      title: I18N.t('editor.backToLibrary'),
      'aria-label': I18N.t('editor.backToLibrary'),
      onclick: function () { Router.navigate('library'); }
    }, [UI.icon('arrow-left')]));

    nodes.name = UI.el('div', { class: 'editor-name', text: I18N.t('editor.untitled') });
    nodes.path = UI.el('div', { class: 'editor-path', text: '' });
    head.appendChild(UI.el('div', { class: 'editor-heading' }, [nodes.name, nodes.path]));

    nodes.saveState = UI.el('span', { class: 'save-state' });
    head.appendChild(nodes.saveState);

    var actions = UI.el('div', { class: 'editor-actions' });
    nodes.modeButtons = [];
    [
      ['edit', 'pen', I18N.t('common.edit')],
      ['split', 'split', I18N.t('editor.split')],
      ['preview', 'eye', I18N.t('editor.preview')]
    ].forEach(function (entry) {
      var button = UI.el('button', {
        type: 'button',
        class: 'icon-btn',
        title: entry[2],
        'aria-label': entry[2],
        onclick: function () { setMode(entry[0]); }
      }, [UI.icon(entry[1])]);
      button.dataset.mode = entry[0];
      nodes.modeButtons.push(button);
    });
    actions.appendChild(UI.el('div', {
      class: 'segmented',
      role: 'group',
      'aria-label': I18N.t('editor.preview')
    }, nodes.modeButtons));

    nodes.outlineBtn = UI.el('button', {
      type: 'button',
      class: 'icon-btn',
      title: I18N.t('editor.outline'),
      'aria-label': I18N.t('editor.outline'),
      onclick: toggleOutline
    }, [UI.icon('hash')]);
    actions.appendChild(nodes.outlineBtn);

    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'icon-btn',
      title: I18N.t('editor.exportShare'),
      'aria-label': I18N.t('editor.exportShare'),
      onclick: function (event) { Pages.doc.shareMenu(event.currentTarget, currentNote()); }
    }, [UI.icon('share')]));

    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'icon-btn',
      title: I18N.t('common.more'),
      'aria-label': I18N.t('common.more'),
      onclick: function (event) { moreMenu(event.currentTarget); }
    }, [UI.icon('more')]));

    nodes.saveBtn = UI.el('button', {
      type: 'button',
      class: 'btn btn-primary',
      id: 'btn-save',
      disabled: true,
      onclick: function () { save(); }
    }, [UI.icon('save'), UI.el('span', { text: I18N.t('editor.save') })]);
    actions.appendChild(nodes.saveBtn);

    head.appendChild(actions);
    page.appendChild(head);

    var body = UI.el('div', { class: 'editor-body' });
    var main = UI.el('div', { class: 'editor-main' });

    nodes.toolbar = buildToolbar();
    main.appendChild(nodes.toolbar);

    var split = UI.el('div', { class: 'editor-split' });

    nodes.editorPane = UI.el('div', { class: 'editor-pane editor-pane-editor' }, [
      UI.el('div', { class: 'editor-pane-head' }, [
        UI.el('span', { text: I18N.t('editor.markdown') }),
        UI.el('span', { text: 'Markdown' })
      ])
    ]);
    nodes.editorHost = UI.el('div', { class: 'editor-host', id: 'editor-host' });
    nodes.editorPane.appendChild(nodes.editorHost);

    nodes.previewPane = UI.el('div', { class: 'editor-pane editor-pane-preview' }, [
      UI.el('div', { class: 'editor-pane-head' }, [
        UI.el('span', { text: I18N.t('editor.preview') }),
        UI.el('span', { text: I18N.t('editor.split') })
      ])
    ]);
    nodes.preview = UI.el('div', { class: 'editor-preview', id: 'editor-preview' });
    nodes.previewProse = UI.el('div', { class: 'prose' });
    nodes.preview.appendChild(nodes.previewProse);
    nodes.previewPane.appendChild(nodes.preview);

    split.appendChild(nodes.editorPane);
    split.appendChild(nodes.previewPane);
    main.appendChild(split);

    nodes.footStats = UI.el('span', { class: 'foot-item' });
    nodes.footChars = UI.el('span', { class: 'foot-item' });
    nodes.footCursor = UI.el('span', { class: 'foot-item' });
    main.appendChild(UI.el('div', { class: 'editor-foot' }, [
      nodes.footStats,
      nodes.footChars,
      nodes.footCursor,
      UI.el('span', { class: 'foot-spacer' }),
      UI.el('span', { class: 'foot-item', text: I18N.t('editor.saveHint') })
    ]));

    body.appendChild(main);

    nodes.outline = UI.el('aside', { class: 'editor-outline', 'aria-label': I18N.t('editor.outline') });
    nodes.outlineHead = UI.el('div', { class: 'outline-head' }, [
      UI.el('span', { text: I18N.t('editor.outline') }),
      UI.el('button', {
        type: 'button',
        class: 'icon-btn icon-btn-sm',
        title: I18N.t('common.close'),
        'aria-label': I18N.t('common.close'),
        onclick: toggleOutline
      }, [UI.icon('x')])
    ]);
    nodes.outlineList = UI.el('div', { class: 'outline-list' });
    nodes.outline.appendChild(nodes.outlineHead);
    nodes.outline.appendChild(nodes.outlineList);
    body.appendChild(nodes.outline);

    page.appendChild(body);
    bindImageIntake();
  }

  function buildToolbar() {
    var toolbar = UI.el('div', {
      class: 'editor-toolbar',
      role: 'toolbar',
      'aria-label': I18N.t('editor.toolbar')
    });

    function add(icon, label, handler) {
      toolbar.appendChild(UI.el('button', {
        type: 'button',
        class: 'tb-btn',
        title: label,
        'aria-label': label,
        onclick: handler
      }, [UI.icon(icon)]));
    }

    function sep() {
      toolbar.appendChild(UI.el('span', { class: 'tb-sep' }));
    }

    add('bold', I18N.t('editor.bold'), function () { wrapSelection('**', '**', I18N.t('editor.bold')); });
    add('italic', I18N.t('editor.italic'), function () { wrapSelection('*', '*', I18N.t('editor.italic')); });
    add('strike', I18N.t('editor.strike'), function () { wrapSelection('~~', '~~', I18N.t('editor.strike')); });
    sep();
    add('heading', I18N.t('editor.heading'), function (event) {
      UI.menu(event.currentTarget, [
        { label: I18N.t('editor.h1'), onClick: function () { prefixLines('# '); } },
        { label: I18N.t('editor.h2'), onClick: function () { prefixLines('## '); } },
        { label: I18N.t('editor.h3'), onClick: function () { prefixLines('### '); } }
      ], { align: 'left' });
    });
    add('quote', I18N.t('editor.quote'), function () { prefixLines('> '); });
    sep();
    add('list-ul', I18N.t('editor.ul'), function () { prefixLines('- '); });
    add('list-ol', I18N.t('editor.ol'), function () { prefixLines('1. ', true); });
    add('task', I18N.t('editor.task'), function () { prefixLines('- [ ] '); });
    sep();
    add('link', I18N.t('editor.link'), linkDialog);
    add('image', I18N.t('editor.image'), pickImage);
    sep();
    add('code', I18N.t('editor.code'), function () { insertBlock('```\n\n```'); });
    add('table', I18N.t('editor.table'), function () {
      insertBlock('|  |  |\n| --- | --- |\n|  |  |');
    });
    add('minus', I18N.t('editor.hr'), function () { insertBlock('---'); });

    return toolbar;
  }

  /* ------------------------------------------------------------------ load */

  function loadNote(path) {
    state.nodes.editorHost.classList.add('is-loading');
    API.getNote(path).then(function (note) {
      state.nodes.editorHost.classList.remove('is-loading');
      openNote(note);
    }, function (error) {
      state.nodes.editorHost.classList.remove('is-loading');
      failed(error);
    });
  }

  function failed(error) {
    var host = state.nodes.editorHost;
    UI.clear(host);
    UI.errorBox(host, (error && error.message) || I18N.t('err.network'),
      function () { loadNote(Router.current().params.p); },
      error && error.code === 3005 ? I18N.t('reader.notFoundBody') : '');
  }

  function startDraft() {
    openNote({
      path: '',
      name: '',
      content: '',
      rev: '',
      size: 0,
      mtime_ns: 0,
      eol: 'lf',
      bom: false,
      writable: true
    });
    state.draft = true;
    state.nodes.path.textContent = I18N.t('library.newNoteHint');
    setSaveState();
  }

  function openNote(note) {
    state.note = note;
    state.draft = !note.path;
    state.dirty = false;
    state.conflict = false;
    state.lastSaved = 0;
    hideBanner();

    state.nodes.name.textContent = note.path
      ? Render.titleOf(note.content, note.path)
      : I18N.t('editor.untitled');
    state.nodes.path.textContent = note.path || '';

    if (state.editor) {
      state.editor.destroy();
      state.editor = null;
    }
    UI.clear(state.nodes.editorHost);

    state.editor = global.MDEditor.create(state.nodes.editorHost, {
      value: note.content || '',
      readOnly: note.writable === false,
      onChange: onDocChange,
      onSave: function () { save(); }
    });

    var readonly = note.writable === false;
    state.nodes.notice.hidden = !readonly;
    state.nodes.saveBtn.disabled = readonly;
    state.nodes.toolbar.classList.toggle('is-disabled', readonly);

    state.editor.scrollDOM.addEventListener('scroll', onEditorScroll, { passive: true });
    state.nodes.preview.addEventListener('scroll', onPreviewScroll, { passive: true });
    state.editor.view.dom.addEventListener('keyup', updateCursor);
    state.editor.view.dom.addEventListener('mouseup', updateCursor);
    state.editor.view.dom.addEventListener('focus', updateCursor);

    renderPreview();
    renderOutline();
    updateStats();
    setSaveState();

    Shell.setTitle(note.path ? Render.titleOf(note.content, note.path) : I18N.t('editor.untitled'));
    Shell.setCrumb(crumbFor(note.path));
    state.editor.focus();
  }

  function reloadNote() {
    if (!state.note || !state.note.path) {
      return;
    }
    var path = state.note.path;
    API.getNote(path).then(function (note) {
      state.dirty = false;
      state.conflict = false;
      openNote(note);
      UI.toast(I18N.t('editor.reload'), 'ok');
    }).catch(Shell.reportError);
  }

  /* ------------------------------------------------------------------ save */

  function save(force) {
    if (!state.editor || state.saving || !state.note || state.note.writable === false) {
      return Promise.resolve(false);
    }
    var content = state.editor.getValue();
    state.saving = true;
    clearTimers();
    setSaveState();

    var chain;
    if (!state.note.path) {
      chain = askPath().then(function (path) {
        if (!path) {
          return false;
        }
        return API.createNote({ path: path, content: content, eol: state.note.eol || 'lf' })
          .then(function (saved) {
            adopt(saved, content, true);
            return true;
          });
      });
    } else {
      chain = API.saveNote({
        path: state.note.path,
        content: content,
        base_rev: state.note.rev,
        eol: state.note.eol || 'lf',
        force: !!force
      }).then(function (saved) {
        adopt(saved, content, false);
        return true;
      });
    }

    return chain.catch(function (error) {
      if (error && error.code === 3007) {
        showConflict();
      } else {
        UI.toast((error && error.message) || I18N.t('err.unknown'), 'bad');
      }
      return false;
    }).then(function (ok) {
      state.saving = false;
      setSaveState();
      if (ok) {
        scheduleLibraryRefresh();
      }
      return ok;
    });
  }

  function adopt(saved, content, created) {
    var previous = state.note.path;
    state.note = {
      path: saved.path || state.note.path,
      name: saved.name || state.note.name,
      content: content,
      rev: saved.rev || '',
      size: saved.size || 0,
      mtime_ns: saved.mtime_ns || Date.now() * 1e6,
      eol: saved.eol || state.note.eol || 'lf',
      bom: !!saved.bom,
      writable: saved.writable !== false
    };
    state.draft = false;
    state.conflict = false;
    state.lastSaved = Date.now();
    hideBanner();

    var current = state.editor ? state.editor.getValue() : content;
    state.dirty = current !== content;

    state.nodes.name.textContent = Render.titleOf(content, state.note.path);
    state.nodes.path.textContent = state.note.path;
    Shell.setTitle(state.nodes.name.textContent);
    Shell.setCrumb(crumbFor(state.note.path));
    if (created || previous !== state.note.path) {
      try {
        global.history.replaceState(null, '', Router.href('edit', { p: state.note.path }));
      } catch (error) {
        /* history may be restricted inside a sandboxed frame */
      }
    }
    setSaveState();
    if (state.dirty) {
      scheduleAutosave();
    }
  }

  function askPath() {
    var folder = Render.folderOf(state.note.path) || Store.settings.get('lastFolder') || '';
    var suggested = (folder ? folder + '/' : '') + (I18N.t('common.untitled')) + '.md';
    return UI.promptDialog({
      title: I18N.t('library.newNoteTitle'),
      label: I18N.t('library.newNoteLabel'),
      value: suggested,
      hint: I18N.t('library.newNoteHint'),
      confirmLabel: I18N.t('common.create')
    }).then(function (value) {
      if (!value) {
        return null;
      }
      if (value.indexOf('/') === -1 && folder) {
        return folder + '/' + value;
      }
      return value;
    });
  }

  function saveCopy() {
    var content = state.editor ? state.editor.getValue() : '';
    var path = state.note.path;
    var folder = Render.folderOf(path);
    var stem = Render.stemOf(path) || I18N.t('editor.untitled');
    UI.promptDialog({
      title: I18N.t('editor.saveCopy'),
      label: I18N.t('library.newNoteLabel'),
      value: (folder ? folder + '/' : '') + stem + ' (copy).md',
      confirmLabel: I18N.t('common.create')
    }).then(function (value) {
      if (!value) {
        return null;
      }
      return API.createNote({ path: value, content: content, eol: state.note.eol || 'lf' });
    }).then(function (created) {
      if (!created) {
        return;
      }
      UI.toast(I18N.t('library.noteCreated', { name: created.name }), 'ok');
      state.dirty = false;
      Router.navigate('edit', { p: created.path });
    }).catch(Shell.reportError);
  }

  function showConflict() {
    state.conflict = true;
    state.dirty = true;
    state.saving = false;
    state.nodes.banner.hidden = false;
    setSaveState();
  }

  function hideBanner() {
    if (state.nodes.banner) {
      state.nodes.banner.hidden = true;
    }
  }

  function scheduleAutosave() {
    global.clearTimeout(state.autosaveTimer);
    if (!Store.settings.get('autosave') || state.draft || !state.note || !state.note.path) {
      return;
    }
    state.autosaveTimer = global.setTimeout(function () {
      if (state.dirty && !state.saving && !state.conflict) {
        save();
      }
    }, 2400);
  }

  function scheduleLibraryRefresh() {
    global.clearTimeout(state.refreshTimer);
    state.refreshTimer = global.setTimeout(function () {
      if (!state.mounted) {
        return;
      }
      Store.loadLibraryAndStats().then(function () {
        Shell.renderFolders();
        Shell.renderStorage();
      }).catch(function () {});
    }, 900);
  }

  function setSaveState() {
    var node = state.nodes.saveState;
    if (!node) {
      return;
    }
    node.classList.remove('is-dirty', 'is-saving');
    if (state.saving) {
      node.classList.add('is-saving');
      node.textContent = I18N.t('editor.saving');
    } else if (state.dirty) {
      node.classList.add('is-dirty');
      node.textContent = I18N.t('editor.unsavedShort');
    } else if (state.lastSaved) {
      node.textContent = I18N.t('editor.savedAt', { time: UI.formatTimeAgo(state.lastSaved) });
    } else {
      node.textContent = state.note && state.note.path ? I18N.t('editor.saved') : '';
    }
    if (state.nodes.saveBtn) {
      state.nodes.saveBtn.disabled = state.saving || state.note == null ||
        state.note.writable === false || (!state.dirty && !!state.note.path);
    }
  }

  function onDocChange(value) {
    var changed = !state.note || value !== state.note.content;
    state.dirty = changed;
    setSaveState();
    updateStats();
    schedulePreview();
    scheduleOutline();
    if (changed) {
      scheduleAutosave();
    } else {
      global.clearTimeout(state.autosaveTimer);
    }
  }

  /* --------------------------------------------------------------- preview */

  function currentSource() {
    if (state.editor) {
      return state.editor.getValue();
    }
    return state.note ? state.note.content : '';
  }

  function currentNote() {
    return {
      path: state.note ? state.note.path : '',
      content: currentSource(),
      rev: state.note ? state.note.rev : '',
      eol: state.note ? state.note.eol : 'lf'
    };
  }

  function schedulePreview() {
    global.clearTimeout(state.previewTimer);
    state.previewTimer = global.setTimeout(renderPreview, 160);
  }

  function renderPreview() {
    if (!state.nodes.previewProse) {
      return;
    }
    var source = currentSource();
    state.nodes.previewProse.innerHTML = Render.markdown(source);
    Render.hydrateImages(state.nodes.previewProse, state.note ? state.note.path : '');
    updateOutlineActive();
  }

  function syncPreviewFromEditor() {
    if (state.mode !== 'split' || !state.editor || !state.nodes.preview) {
      return;
    }
    var now = Date.now();
    if (state.syncGuard > now) {
      return;
    }
    var dom = state.editor.scrollDOM;
    var max = dom.scrollHeight - dom.clientHeight;
    var ratio = max > 0 ? dom.scrollTop / max : 0;
    var preview = state.nodes.preview;
    state.syncGuard = now + 80;
    preview.scrollTop = ratio * (preview.scrollHeight - preview.clientHeight);
  }

  var previewScrollLock = 0;

  function onPreviewScroll() {
    if (state.mode !== 'split' || !state.editor) {
      return;
    }
    var now = Date.now();
    if (previewScrollLock > now) {
      return;
    }
    previewScrollLock = now + 80;
    var preview = state.nodes.preview;
    var max = preview.scrollHeight - preview.clientHeight;
    var ratio = max > 0 ? preview.scrollTop / max : 0;
    var dom = state.editor.scrollDOM;
    dom.scrollTop = ratio * (dom.scrollHeight - dom.clientHeight);
  }

  /* --------------------------------------------------------------- outline */

  function scheduleOutline() {
    global.clearTimeout(state.outlineTimer);
    state.outlineTimer = global.setTimeout(renderOutline, 260);
  }

  function renderOutline() {
    if (!state.nodes.outlineList) {
      return;
    }
    var source = currentSource();
    state.outline = Render.outline(source).filter(function (item) { return item.level <= 4; });
    UI.clear(state.nodes.outlineList);
    if (!state.outline.length) {
      state.nodes.outlineList.appendChild(UI.el('div', { class: 'outline-empty' }, [
        UI.el('div', { text: I18N.t('editor.outlineEmpty') }),
        UI.el('div', { text: I18N.t('editor.outlineEmptyBody') })
      ]));
      return;
    }
    state.outline.forEach(function (item) {
      state.nodes.outlineList.appendChild(UI.el('button', {
        type: 'button',
        class: 'outline-item',
        text: item.text,
        dataset: { level: String(item.level), line: String(item.line) },
        onclick: function () {
          if (!state.editor) {
            return;
          }
          state.editor.scrollToLine(item.line);
          state.editor.focus();
          setOutlineActive(item.line);
        }
      }));
    });
    updateOutlineActive();
    var name = Render.titleOf(source, state.note ? state.note.path : '');
    if (state.nodes.name && name) {
      state.nodes.name.textContent = name;
    }
  }

  function updateOutlineActive() {
    if (!state.editor) {
      return;
    }
    setOutlineActive(state.editor.getTopLine());
  }

  function setOutlineActive(line) {
    if (!state.nodes.outlineList) {
      return;
    }
    var activeLine = 0;
    state.outline.forEach(function (item) {
      if (item.line <= line) {
        activeLine = item.line;
      }
    });
    Array.prototype.forEach.call(state.nodes.outlineList.querySelectorAll('.outline-item'), function (button) {
      button.classList.toggle('is-active', Number(button.dataset.line) === activeLine);
    });
  }

  function onEditorScroll() {
    syncPreviewFromEditor();
    updateOutlineActive();
  }

  function toggleOutline() {
    state.outlineOn = !state.outlineOn;
    state.nodes.outline.hidden = !state.outlineOn;
    state.nodes.outlineBtn.classList.toggle('is-active', state.outlineOn);
  }

  /* ------------------------------------------------------------------ mode */

  function setMode(mode) {
    state.mode = mode === 'edit' || mode === 'preview' ? mode : 'split';
    var nodes = state.nodes;
    if (!nodes.page) {
      return;
    }
    nodes.page.classList.toggle('is-preview', state.mode === 'preview');
    nodes.editorPane.hidden = state.mode === 'preview';
    nodes.previewPane.hidden = state.mode === 'edit';
    nodes.toolbar.hidden = state.mode === 'preview';
    nodes.modeButtons.forEach(function (button) {
      button.classList.toggle('is-active', button.dataset.mode === state.mode);
    });
    if (state.mode !== 'edit') {
      renderPreview();
    }
  }

  /* --------------------------------------------------------------- toolbar */

  function view() {
    return state.editor ? state.editor.view : null;
  }

  function wrapSelection(before, after, placeholder) {
    var instance = view();
    if (!instance) {
      return;
    }
    var selection = instance.state.selection.main;
    var selected = instance.state.sliceDoc(selection.from, selection.to) || placeholder || '';
    var insert = before + selected + after;
    instance.dispatch({
      changes: { from: selection.from, to: selection.to, insert: insert },
      selection: {
        anchor: selection.from + before.length,
        head: selection.from + before.length + selected.length
      }
    });
    instance.focus();
  }

  function prefixLines(prefix, numbered) {
    var instance = view();
    if (!instance) {
      return;
    }
    var selection = instance.state.selection.main;
    var first = instance.state.doc.lineAt(selection.from);
    var last = instance.state.doc.lineAt(selection.to);
    var changes = [];
    var counter = 1;
    for (var number = first.number; number <= last.number; number += 1) {
      var line = instance.state.doc.line(number);
      changes.push({
        from: line.from,
        insert: numbered ? counter++ + '. ' : prefix
      });
    }
    instance.dispatch({ changes: changes });
    instance.focus();
  }

  function insertBlock(text) {
    var instance = view();
    if (!instance) {
      return;
    }
    var selection = instance.state.selection.main;
    var before = selection.from > 0 ? '\n\n' : '';
    var insert = before + text + '\n\n';
    instance.dispatch({
      changes: { from: selection.from, to: selection.to, insert: insert },
      selection: { anchor: selection.from + insert.length }
    });
    instance.focus();
  }

  function insertSnippet(text) {
    insertBlock(text);
  }

  function linkDialog(event) {
    var instance = view();
    if (!instance) {
      return;
    }
    var selection = instance.state.selection.main;
    var selected = instance.state.sliceDoc(selection.from, selection.to);
    var textInput = UI.el('input', {
      class: 'input',
      type: 'text',
      value: selected,
      placeholder: I18N.t('editor.linkText')
    });
    var urlInput = UI.el('input', {
      class: 'input',
      type: 'text',
      value: 'https://',
      placeholder: I18N.t('editor.linkUrl'),
      spellcheck: 'false'
    });
    var settled = false;
    var errorNode = UI.el('div', { class: 'field-error', hidden: true });
    var dialog = UI.modal({
      title: I18N.t('editor.linkTitle'),
      body: UI.el('div', null, [
        UI.el('label', { class: 'field' }, [
          UI.el('span', { class: 'field-label', text: I18N.t('editor.linkText') }),
          textInput
        ]),
        UI.el('label', { class: 'field' }, [
          UI.el('span', { class: 'field-label', text: I18N.t('editor.linkUrl') }),
          urlInput
        ]),
        errorNode
      ]),
      onClose: function () { settle(null); },
      actions: [
        {
          label: I18N.t('common.cancel'),
          onClick: function () { settle(null); }
        },
        {
          label: I18N.t('common.confirm'),
          kind: 'primary',
          close: false,
          onClick: function () {
            var url = urlInput.value.trim();
            if (!url || url === 'https://') {
              errorNode.hidden = false;
              errorNode.textContent = I18N.t('editor.linkUrl');
              urlInput.focus();
              return;
            }
            settle({ text: textInput.value.trim() || url, url: url });
          }
        }
      ]
    });

    function settle(result) {
      if (settled) {
        return;
      }
      settled = true;
      dialog.close(true);
      if (!result) {
        return;
      }
      var instance2 = view();
      if (!instance2) {
        return;
      }
      var current = instance2.state.selection.main;
      var insert = '[' + result.text + '](' + result.url + ')';
      instance2.dispatch({
        changes: { from: current.from, to: current.to, insert: insert },
        selection: { anchor: current.from + insert.length }
      });
      instance2.focus();
    }
  }

  function pickImage() {
    var input = UI.el('input', {
      type: 'file',
      accept: 'image/png,image/jpeg,image/gif,image/webp,image/bmp,image/avif',
      style: { display: 'none' }
    });
    input.addEventListener('change', function () {
      if (input.files && input.files[0]) {
        uploadImage(input.files[0]);
      }
      if (input.parentNode) {
        input.parentNode.removeChild(input);
      }
    });
    global.document.body.appendChild(input);
    input.click();
  }

  /* ---------------------------------------------------------------- images */

  function maxAttachmentMb() {
    var options = Store.state.options;
    return (options && options.max_attachment_mb) || 64;
  }

  function uploadImage(file) {
    if (!file) {
      return;
    }
    if (!/^image\//.test(file.type || '')) {
      UI.toast(I18N.t('editor.unsupportedImage'), 'warn');
      return;
    }
    if (file.size > maxAttachmentMb() * 1024 * 1024) {
      UI.toast(I18N.t('editor.imageTooLarge'), 'warn');
      return;
    }

    var chip = UI.el('div', { class: 'upload-chip' }, [
      UI.el('span', { class: 'spinner' }),
      UI.el('span', { text: I18N.t('editor.imageUploading') })
    ]);
    state.nodes.editorHost.appendChild(chip);

    ensurePathForAttachment().then(function (dir) {
      if (dir === null) {
        if (chip.parentNode) {
          chip.parentNode.removeChild(chip);
        }
        return null;
      }
      return API.uploadAttachment({
        dir: dir,
        file: file,
        onProgress: function (ratio) {
          var label = chip.querySelector('span:last-child');
          if (label) {
            label.textContent = I18N.t('editor.uploadProgress', { n: Math.round(ratio * 100) });
          }
        }
      }).then(function (attachment) {
        insertSnippet(attachment.markdown);
        UI.toast(I18N.t('editor.imageInserted'), 'ok');
        schedulePreview();
      }).catch(function (error) {
        var message = error && error.code === 3015 ? I18N.t('editor.unsupportedImage')
          : error && error.code === 3016 ? I18N.t('editor.imageTooLarge')
            : I18N.t('editor.imageFailed');
        UI.toast(message, 'bad');
      });
    }).then(function () {
      if (chip.parentNode) {
        chip.parentNode.removeChild(chip);
      }
    });
  }

  function ensurePathForAttachment() {
    if (state.note && state.note.path) {
      return Promise.resolve(Render.folderOf(state.note.path));
    }
    return save().then(function (ok) {
      return ok && state.note.path ? Render.folderOf(state.note.path) : null;
    });
  }

  function bindImageIntake() {
    var host = state.nodes.editorHost;

    host.addEventListener('paste', function (event) {
      var items = event.clipboardData && event.clipboardData.items;
      if (!items) {
        return;
      }
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].type && items[i].type.indexOf('image/') === 0) {
          event.preventDefault();
          var file = items[i].getAsFile();
          if (file) {
            UI.toast(I18N.t('editor.pasteImage'));
            uploadImage(file);
          }
          return;
        }
      }
    }, true);

    var depth = 0;
    host.addEventListener('dragenter', function (event) {
      if (event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types || [], 'Files') !== -1) {
        depth += 1;
        host.classList.add('is-dragover');
      }
    });
    host.addEventListener('dragleave', function () {
      depth = Math.max(0, depth - 1);
      if (!depth) {
        host.classList.remove('is-dragover');
      }
    });
    host.addEventListener('dragover', function (event) {
      if (event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types || [], 'Files') !== -1) {
        event.preventDefault();
      }
    });
    host.addEventListener('drop', function (event) {
      if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) {
        return;
      }
      event.preventDefault();
      depth = 0;
      host.classList.remove('is-dragover');
      Array.prototype.forEach.call(event.dataTransfer.files, function (file) {
        if (file.type.indexOf('image/') === 0) {
          uploadImage(file);
        }
      });
    });
  }

  /* ------------------------------------------------------------------ misc */

  function updateStats() {
    var source = currentSource();
    var words = Render.countWords(source);
    var lines = state.editor ? state.editor.view.state.doc.lines : (source.split('\n').length);
    var chars = source.replace(/\s/g, '').length;
    if (state.nodes.footStats) {
      state.nodes.footStats.textContent = I18N.t('editor.stats', { words: words, lines: lines });
    }
    if (state.nodes.footChars) {
      state.nodes.footChars.textContent = I18N.t('editor.charCount', { n: chars });
    }
    updateCursor();
  }

  function updateCursor() {
    if (!state.editor || !state.nodes.footCursor) {
      return;
    }
    var instance = state.editor.view;
    var head = instance.state.selection.main.head;
    var line = instance.state.doc.lineAt(head);
    state.nodes.footCursor.textContent = I18N.t('editor.lineCol', {
      line: line.number,
      col: head - line.from + 1
    });
  }

  /* ---------------------------------------------------------------- menu */

  function moreMenu(anchor) {
    var note = currentNote();
    var items = [
      {
        label: I18N.t('editor.versions'),
        icon: 'clock',
        onClick: function () {
          if (!note.path) {
            UI.toast(I18N.t('editor.versionEmptyBody'), 'warn');
            return;
          }
          Pages.doc.versions(note, function (restored) {
            state.dirty = false;
            openNote(restored);
          });
        }
      },
      { label: I18N.t('editor.exportMd'), icon: 'download', onClick: function () { Pages.doc.exportMarkdown(note); } },
      { label: I18N.t('editor.exportHtml'), icon: 'file-text', onClick: function () { Pages.doc.exportHtml(note); } },
      { divider: true },
      {
        label: I18N.t('common.copy') + ' · ' + I18N.t('common.path'),
        icon: 'copy',
        disabled: !note.path,
        onClick: function () {
          UI.copyText(note.path).then(function (ok) {
            UI.toast(ok ? I18N.t('library.pathCopied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
          });
        }
      },
      { label: I18N.t('reader.print'), icon: 'file', onClick: function () { global.print(); } }
    ];
    if (note.path) {
      items.push({ divider: true });
      items.push({
        label: I18N.t('reader.deleteNote'),
        icon: 'trash',
        danger: true,
        onClick: removeNote
      });
    }
    UI.menu(anchor, items);
  }

  function removeNote() {
    if (!state.note || !state.note.path) {
      return;
    }
    var path = state.note.path;
    UI.confirm({
      title: I18N.t('reader.deleteTitle', { name: path }),
      message: I18N.t('reader.deleteConfirm'),
      confirmLabel: I18N.t('common.delete'),
      danger: true
    }).then(function (ok) {
      if (!ok) {
        return;
      }
      return API.deleteNote(path).then(function () {
        state.dirty = false;
        UI.toast(I18N.t('reader.deleted', { name: path }), 'ok');
        return Store.loadLibraryAndStats().catch(function () { return null; });
      }).then(function () {
        Shell.renderFolders();
        Shell.renderStorage();
        Router.navigate('library');
      });
    }).catch(Shell.reportError);
  }

  /* --------------------------------------------------------------- leaving */

  function guard() {
    if (!state.dirty || !state.editor) {
      return true;
    }
    if (state.note && state.note.path && !state.conflict) {
      return save().then(function (ok) {
        return ok ? true : confirmLeave();
      });
    }
    return confirmLeave();
  }

  function confirmLeave() {
    return UI.confirm({
      title: I18N.t('editor.unsaved'),
      message: I18N.t('editor.unsavedShort'),
      confirmLabel: I18N.t('editor.leaveDiscard'),
      cancelLabel: I18N.t('editor.stayEditing'),
      danger: true
    });
  }

  global.Pages = global.Pages || {};
  global.Pages.editor = {
    mount: mount,
    unmount: unmount,
    setDocumentTitle: setDocumentTitle,
    save: save
  };
})(window);
