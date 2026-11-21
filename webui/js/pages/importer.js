/* MarkNest for TOS - upload and import.

   Files are collected first and sent as one multipart batch, because that is
   what the server accepts and because one request means one progress bar. The
   queue keeps the File objects, so a failed item can be retried without the
   operator picking it again. The server answers per file; this page only
   projects those verdicts onto the rows the operator already sees. */

(function (global) {
  'use strict';

  var FALLBACK_EXTENSIONS = ['.md', '.markdown', '.mdown', '.txt'];

  var state = {
    queue: [],
    dir: '',
    conflict: 'rename',
    busy: false,
    progress: 0,
    result: null
  };

  var nodes = {};
  var mounted = false;
  var nextId = 1;
  var dragDepth = 0;

  /* --------------------------------------------------------------- helpers */

  function extensions() {
    var options = Store.state.options;
    var list = options && options.note_extensions;
    return (list && list.length ? list : FALLBACK_EXTENSIONS).map(function (ext) {
      return String(ext).toLowerCase();
    });
  }

  function acceptAttribute() {
    return extensions().join(',');
  }

  function acceptedLabel() {
    return extensions().map(function (ext) {
      return ext.replace(/^\./, '').toUpperCase();
    }).join(', ');
  }

  function maxFiles() {
    var options = Store.state.options;
    return (options && options.max_import_files) || 50;
  }

  function maxNoteBytes() {
    var options = Store.state.options;
    return ((options && options.max_note_mb) || 8) * 1024 * 1024;
  }

  function supported(file) {
    var name = String(file.name || '').toLowerCase();
    return extensions().some(function (ext) {
      return name.slice(-ext.length) === ext;
    });
  }

  function isDuplicate(file) {
    return state.queue.some(function (entry) {
      return entry.file.name === file.name &&
        entry.file.size === file.size &&
        entry.file.lastModified === file.lastModified;
    });
  }

  function refreshLibrary() {
    Store.loadLibraryAndStats().then(function () {
      Shell.sync();
    }).catch(function () {
      /* the import result is still authoritative for this page */
    });
  }

  /* ------------------------------------------------------------------ mount */

  function mount(host) {
    mounted = true;
    state.dir = Store.settings.get('lastFolder') || '';
    state.conflict = 'rename';
    state.result = null;
    state.progress = 0;
    state.busy = false;

    var page = UI.el('div', { class: 'page page-import' });
    var scroll = UI.el('div', { class: 'page-scroll' });
    page.appendChild(scroll);
    host.appendChild(page);

    var head = UI.el('div', { class: 'page-head' }, [
      UI.el('div', { class: 'page-head-text' }, [
        UI.el('h1', { class: 'page-title', text: I18N.t('import.title') }),
        UI.el('p', { class: 'page-sub', text: I18N.t('import.subtitle') })
      ]),
      UI.el('div', { class: 'page-head-actions' }, [
        UI.el('button', {
          type: 'button',
          class: 'btn btn-ghost',
          onclick: function () { Router.navigate('library'); }
        }, [UI.icon('library'), UI.el('span', { text: I18N.t('import.goLibrary') })])
      ])
    ]);
    scroll.appendChild(head);

    var grid = UI.el('div', { class: 'import-grid' });
    scroll.appendChild(grid);

    var left = UI.el('div', { class: 'import-col' });
    var right = UI.el('div', { class: 'import-col' });
    grid.appendChild(left);
    grid.appendChild(right);

    nodes.scroll = scroll;
    nodes.grid = grid;
    nodes.dropzone = buildDropzone();
    left.appendChild(nodes.dropzone);
    left.appendChild(buildQueue());

    nodes.destination = buildDestination();
    right.appendChild(nodes.destination.panel);
    right.appendChild(buildConflict());
    right.appendChild(buildTextCreate());

    Shell.setCrumb([
      { label: I18N.t('nav.library'), href: Router.href('library', {}) }
    ]);
    Shell.setTitle(I18N.t('import.title'));
    Shell.setActions([
      UI.el('button', {
        type: 'button',
        class: 'btn',
        onclick: function () { Router.navigate('library'); }
      }, [UI.icon('library'), UI.el('span', { text: I18N.t('nav.library') })])
    ]);

    if (!Store.state.folders) {
      Store.loadLibrary().then(function () {
        if (mounted) {
          nodes.destination.render();
        }
      }).catch(function () {
        /* the destination stays at the root folder */
      });
    }

    renderQueue();
  }

  function unmount() {
    mounted = false;
    state.queue = [];
    state.result = null;
    state.busy = false;
    state.progress = 0;
    dragDepth = 0;
    nodes = {};
  }

  /* --------------------------------------------------------------- dropzone */

  function buildDropzone() {
    var input = UI.el('input', {
      type: 'file',
      multiple: true,
      accept: acceptAttribute(),
      style: { display: 'none' }
    });
    input.addEventListener('change', function () {
      addFiles(input.files);
      input.value = '';
    });
    nodes.fileInput = input;

    var browse = UI.el('button', {
      type: 'button',
      class: 'btn btn-primary',
      onclick: function (event) {
        if (event) {
          event.stopPropagation();
        }
        input.click();
      }
    }, [UI.icon('upload'), UI.el('span', { text: I18N.t('import.browse') })]);

    var zone = UI.el('div', {
      class: 'dropzone',
      role: 'button',
      tabindex: '0',
      'aria-label': I18N.t('import.browse'),
      onclick: function () { input.click(); },
      onkeydown: function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          input.click();
        }
      }
    }, [
      input,
      UI.el('div', { class: 'dropzone-art' }, [UI.icon('upload')]),
      UI.el('div', { class: 'dropzone-title', text: I18N.t('import.dropTitle') }),
      UI.el('div', {
        class: 'dropzone-body',
        text: I18N.t('import.dropBody', { n: maxFiles() })
      }),
      browse,
      UI.el('div', {
        class: 'dropzone-note',
        text: I18N.t('import.accepted', { exts: acceptedLabel() })
      })
    ]);

    function allow(event) {
      event.preventDefault();
      event.stopPropagation();
    }

    zone.addEventListener('dragenter', function (event) {
      allow(event);
      dragDepth += 1;
      zone.classList.add('is-over');
    });
    zone.addEventListener('dragover', function (event) {
      allow(event);
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
      zone.classList.add('is-over');
    });
    zone.addEventListener('dragleave', function (event) {
      allow(event);
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) {
        zone.classList.remove('is-over');
      }
    });
    zone.addEventListener('drop', function (event) {
      allow(event);
      dragDepth = 0;
      zone.classList.remove('is-over');
      if (event.dataTransfer) {
        addFiles(event.dataTransfer.files);
      }
    });

    return zone;
  }

  function addFiles(fileList) {
    if (state.busy || !fileList) {
      return;
    }
    var files = Array.prototype.slice.call(fileList);
    if (!files.length) {
      return;
    }
    var room = maxFiles() - state.queue.length;
    if (room <= 0 || files.length > room) {
      UI.toast(I18N.t('import.tooMany', { n: maxFiles() }), 'bad');
      files = files.slice(0, Math.max(0, room));
    }

    var rejected = 0;
    var duplicates = 0;
    files.forEach(function (file) {
      if (!supported(file)) {
        rejected += 1;
        return;
      }
      if (isDuplicate(file)) {
        duplicates += 1;
        return;
      }
      var entry = {
        id: nextId += 1,
        file: file,
        relative: file.name,
        status: file.size > maxNoteBytes() ? 'failed' : 'pending',
        message: file.size > maxNoteBytes() ? I18N.t('err.code1413') : ''
      };
      state.queue.push(entry);
    });

    if (rejected) {
      UI.toast(I18N.t('import.invalidType'), 'warn');
    }
    if (duplicates) {
      UI.toast(I18N.t('import.queueEmpty'), 'warn');
    }
    state.result = null;
    renderQueue();
  }

  /* ------------------------------------------------------------------ queue */

  function buildQueue() {
    var panel = UI.el('section', { class: 'panel queue' });
    var count = UI.el('span', { class: 'badge' });
    var clearBtn = UI.el('button', {
      type: 'button',
      class: 'btn btn-sm btn-ghost',
      disabled: true,
      onclick: clearQueue
    }, [UI.icon('trash'), UI.el('span', { text: I18N.t('import.clear') })]);

    panel.appendChild(UI.el('div', { class: 'panel-head' }, [
      UI.el('div', null, [
        UI.el('h2', { class: 'panel-title', text: I18N.t('import.queue') }),
        UI.el('p', { class: 'panel-sub', text: I18N.t('import.queueEmptyBody') })
      ]),
      UI.el('div', { class: 'panel-actions' }, [count, clearBtn])
    ]));

    nodes.queueCount = count;
    nodes.clearBtn = clearBtn;
    nodes.queueBody = UI.el('div', { class: 'queue' });
    panel.appendChild(nodes.queueBody);

    nodes.progress = UI.el('div', { class: 'progress', hidden: true, role: 'progressbar' }, [
      UI.el('span', { class: 'progress-fill' })
    ]);
    nodes.progressFill = nodes.progress.firstChild;
    nodes.progressText = UI.el('div', { class: 'progress-text', hidden: true });
    panel.appendChild(nodes.progress);
    panel.appendChild(nodes.progressText);

    nodes.summary = UI.el('div', { class: 'import-summary', hidden: true });
    panel.appendChild(nodes.summary);

    nodes.actions = UI.el('div', { class: 'import-actions' });
    nodes.startBtn = UI.el('button', {
      type: 'button',
      class: 'btn btn-primary',
      onclick: function () { startImport(); }
    }, [UI.icon('upload'), UI.el('span', { text: I18N.t('import.start') })]);
    nodes.actions.appendChild(nodes.startBtn);
    panel.appendChild(nodes.actions);

    return panel;
  }

  function renderQueue() {
    if (!nodes.queueBody) {
      return;
    }
    UI.clear(nodes.queueBody);

    if (nodes.queueCount) {
      nodes.queueCount.textContent = String(state.queue.length);
    }
    if (nodes.clearBtn) {
      nodes.clearBtn.disabled = state.busy || !state.queue.length;
    }

    if (!state.queue.length) {
      nodes.queueBody.appendChild(UI.emptyState({
        icon: 'file-text',
        title: I18N.t('import.queueEmpty'),
        body: I18N.t('import.queueEmptyBody')
      }));
      renderActions();
      renderSummary();
      return;
    }

    var list = UI.el('div', { class: 'queue-list' });
    state.queue.forEach(function (entry) {
      list.appendChild(queueItem(entry));
    });
    nodes.queueBody.appendChild(list);
    renderActions();
    renderSummary();
  }

  function queueItem(entry) {
    var meta = UI.el('div', {
      class: 'queue-meta' + (entry.status === 'failed' ? ' is-error' : ''),
      text: UI.formatBytes(entry.file.size)
    });
    if (entry.status === 'failed' && entry.message) {
      meta.textContent = UI.formatBytes(entry.file.size) + ' · ' + entry.message;
    } else if (entry.status === 'skipped' && entry.message) {
      meta.textContent = UI.formatBytes(entry.file.size) + ' · ' + entry.message;
    }

    var remove = UI.el('button', {
      type: 'button',
      class: 'icon-btn icon-btn-sm',
      title: I18N.t('import.removeFile'),
      'aria-label': I18N.t('import.removeFile'),
      disabled: state.busy || entry.status === 'uploading',
      onclick: function () {
        removeEntry(entry);
      }
    }, [UI.icon('x')]);

    return UI.el('div', { class: 'queue-item' }, [
      UI.el('span', { class: 'queue-icon' }, [UI.icon('file-text')]),
      UI.el('div', { class: 'queue-text' }, [
        UI.el('div', { class: 'queue-name', text: entry.relative, title: entry.relative }),
        meta
      ]),
      UI.el('span', { class: 'queue-status' }, [UI.statusBadge(entry.status)]),
      remove
    ]);
  }

  function removeEntry(entry) {
    if (state.busy) {
      return;
    }
    state.queue = state.queue.filter(function (item) {
      return item !== entry;
    });
    state.result = null;
    renderQueue();
  }

  function clearQueue() {
    if (state.busy) {
      return;
    }
    if (!state.queue.length) {
      return;
    }
    state.queue = [];
    state.result = null;
    state.progress = 0;
    renderQueue();
  }

  function renderActions() {
    if (!nodes.startBtn) {
      return;
    }
    var pending = state.queue.some(function (entry) {
      return entry.status === 'pending' || entry.status === 'failed';
    });
    nodes.startBtn.disabled = state.busy || !pending;
    nodes.startBtn.textContent = '';
    nodes.startBtn.appendChild(UI.icon('upload'));
    nodes.startBtn.appendChild(UI.el('span', {
      text: state.busy ? I18N.t('import.uploading') : I18N.t('import.start')
    }));
  }

  /* --------------------------------------------------------------- progress */

  function setProgress(fraction) {
    state.progress = Math.max(0, Math.min(1, fraction || 0));
    if (nodes.progress) {
      nodes.progress.hidden = false;
      nodes.progressFill.style.width = (state.progress * 100).toFixed(1) + '%';
    }
    if (nodes.progressText) {
      nodes.progressText.hidden = false;
      nodes.progressText.textContent = I18N.t('common.uploading') + ' ' +
        Math.round(state.progress * 100) + '%';
    }
  }

  function hideProgress() {
    state.progress = 0;
    if (nodes.progress) {
      nodes.progress.hidden = true;
      nodes.progressFill.style.width = '0%';
    }
    if (nodes.progressText) {
      nodes.progressText.hidden = true;
    }
  }

  /* ----------------------------------------------------------------- import */

  function startImport() {
    if (state.busy) {
      return;
    }
    var pending = state.queue.filter(function (entry) {
      return entry.status === 'pending' || entry.status === 'failed';
    });
    if (!pending.length) {
      UI.toast(I18N.t('import.noFiles'), 'warn');
      return;
    }

    state.busy = true;
    state.result = null;
    pending.forEach(function (entry) {
      entry.status = 'uploading';
      entry.message = '';
    });
    setProgress(0);
    renderQueue();

    var files = pending.map(function (entry) {
      return { file: entry.file, relative: entry.relative };
    });

    API.importNotes({
      dir: state.dir,
      conflict: state.conflict,
      files: files,
      onProgress: function (fraction) {
        if (mounted) {
          setProgress(fraction);
        }
      }
    }).then(function (result) {
      if (!mounted) {
        return;
      }
      applyResult(pending, result);
      hideProgress();
      state.busy = false;
      renderQueue();
      refreshLibrary();
    }, function (error) {
      if (!mounted) {
        return;
      }
      pending.forEach(function (entry) {
        entry.status = 'failed';
        entry.message = I18N.errorText(error);
      });
      hideProgress();
      state.busy = false;
      renderQueue();
      Shell.reportError(error);
    });
  }

  function applyResult(entries, result) {
    var results = (result && result.results) || [];
    var created = 0;
    var skipped = 0;
    var failed = 0;

    entries.forEach(function (entry, index) {
      var item = results[index];
      if (!item) {
        entry.status = 'failed';
        entry.message = I18N.t('err.unknown');
        failed += 1;
        return;
      }
      if (item.status === 'created') {
        entry.status = 'created';
        entry.resultPath = item.path || '';
        entry.message = '';
        created += 1;
      } else if (item.status === 'skipped') {
        entry.status = 'skipped';
        entry.message = item.message || '';
        skipped += 1;
      } else {
        entry.status = 'failed';
        entry.message = I18N.errorText({ code: item.code, message: item.message });
        failed += 1;
      }
    });

    state.result = { created: created, skipped: skipped, failed: failed };
  }

  function renderSummary() {
    if (!nodes.summary) {
      return;
    }
    var result = state.result;
    if (!result) {
      nodes.summary.hidden = true;
      UI.clear(nodes.summary);
      return;
    }

    UI.clear(nodes.summary);
    nodes.summary.hidden = false;
    nodes.summary.className = 'import-summary ' + (result.failed ? 'is-warn' : 'is-ok');
    nodes.summary.appendChild(UI.el('div', {
      text: I18N.t('import.summary', {
        created: result.created,
        skipped: result.skipped,
        failed: result.failed
      })
    }));

    var actions = UI.el('div', { class: 'import-actions' });
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn btn-sm',
      onclick: function () { Router.navigate('library'); }
    }, [UI.icon('library'), UI.el('span', { text: I18N.t('import.goLibrary') })]));

    if (result.failed) {
      actions.appendChild(UI.el('button', {
        type: 'button',
        class: 'btn btn-sm',
        disabled: state.busy,
        onclick: retryFailed
      }, [UI.icon('refresh'), UI.el('span', { text: I18N.t('import.retryFailed') })]));
    }
    nodes.summary.appendChild(actions);
  }

  function retryFailed() {
    if (state.busy) {
      return;
    }
    state.queue.forEach(function (entry) {
      if (entry.status === 'failed') {
        entry.status = 'pending';
        entry.message = '';
      }
    });
    state.result = null;
    renderQueue();
    startImport();
  }

  /* ------------------------------------------------------------ destination */

  function buildDestination() {
    var select = UI.el('select', { class: 'select' });
    select.addEventListener('change', function () {
      state.dir = select.value;
      Store.settings.set('lastFolder', state.dir);
    });

    function render() {
      UI.clear(select);
      select.appendChild(UI.el('option', {
        value: '',
        text: I18N.t('import.rootFolder')
      }));
      (Store.state.folders || []).forEach(function (folder) {
        select.appendChild(UI.el('option', {
          value: folder.path,
          text: folder.path
        }));
      });
      var known = (Store.state.folders || []).some(function (folder) {
        return folder.path === state.dir;
      });
      if (!known) {
        state.dir = '';
      }
      select.value = state.dir;
    }

    render();

    var panel = UI.el('section', { class: 'panel' }, [
      UI.el('div', { class: 'panel-head' }, [
        UI.el('div', null, [
          UI.el('h2', { class: 'panel-title', text: I18N.t('import.destination') }),
          UI.el('p', { class: 'panel-sub', text: I18N.t('import.noteHint') })
        ])
      ]),
      UI.el('label', { class: 'field' }, [select])
    ]);

    return { panel: panel, render: render };
  }

  /* --------------------------------------------------------------- conflict */

  function buildConflict() {
    var options = [
      { value: 'rename', title: 'import.conflictRename', desc: 'import.conflictRenameHint' },
      { value: 'skip', title: 'import.conflictSkip', desc: 'import.conflictSkipHint' }
    ];
    var cards = [];
    var list = UI.el('div', { class: 'radio-list' });

    options.forEach(function (option) {
      var input = UI.el('input', {
        type: 'radio',
        name: 'import-conflict',
        value: option.value,
        checked: state.conflict === option.value
      });
      input.addEventListener('change', function () {
        if (input.checked) {
          state.conflict = option.value;
          cards.forEach(function (card) {
            card.classList.toggle('is-active', card.dataset.value === state.conflict);
          });
        }
      });
      var card = UI.el('label', {
        class: 'radio-card' + (state.conflict === option.value ? ' is-active' : ''),
        dataset: { value: option.value }
      }, [
        input,
        UI.el('div', { class: 'radio-text' }, [
          UI.el('div', { class: 'radio-title', text: I18N.t(option.title) }),
          UI.el('div', { class: 'radio-desc', text: I18N.t(option.desc) })
        ])
      ]);
      cards.push(card);
      list.appendChild(card);
    });

    return UI.el('section', { class: 'panel' }, [
      UI.el('div', { class: 'panel-head' }, [
        UI.el('div', null, [
          UI.el('h2', { class: 'panel-title', text: I18N.t('import.conflict') })
        ])
      ]),
      list
    ]);
  }

  /* ------------------------------------------------------- text to a note */

  function buildTextCreate() {
    var pathInput = UI.el('input', {
      class: 'input',
      type: 'text',
      placeholder: I18N.t('import.textNamePlaceholder')
    });
    var textArea = UI.el('textarea', {
      class: 'textarea',
      rows: '6',
      placeholder: I18N.t('import.textPlaceholder')
    });
    var create = UI.el('button', {
      type: 'button',
      class: 'btn btn-primary',
      onclick: function () {
        createNote(pathInput, textArea, create);
      }
    }, [UI.icon('plus'), UI.el('span', { text: I18N.t('import.textCreate') })]);

    return UI.el('section', { class: 'panel text-create' }, [
      UI.el('div', { class: 'panel-head' }, [
        UI.el('div', null, [
          UI.el('h2', { class: 'panel-title', text: I18N.t('import.textTitle') }),
          UI.el('p', { class: 'panel-sub', text: I18N.t('import.textBody') })
        ])
      ]),
      UI.el('div', { class: 'field' }, [
        UI.el('span', { class: 'field-label', text: I18N.t('import.textName') }),
        pathInput
      ]),
      UI.el('div', { class: 'field' }, [textArea]),
      UI.el('div', { class: 'import-actions' }, [create])
    ]);
  }

  function createNote(pathInput, textArea, button) {
    var path = pathInput.value.trim();
    if (!path) {
      UI.toast(I18N.t('import.textName'), 'warn');
      pathInput.focus();
      return;
    }
    var content = textArea.value;
    if (!content) {
      UI.toast(I18N.t('common.empty'), 'warn');
      textArea.focus();
      return;
    }
    var full = path;
    if (full.charAt(0) === '/') {
      full = full.replace(/^\/+/, '');
    }
    if (state.dir && full.indexOf('/') < 0) {
      full = state.dir + '/' + full;
    }

    button.disabled = true;
    API.createNote({ path: full, content: content, eol: 'lf' }).then(function (note) {
      if (!mounted) {
        return;
      }
      button.disabled = false;
      pathInput.value = '';
      textArea.value = '';
      UI.toast(I18N.t('import.textCreated', { name: note.path }), 'ok');
      refreshLibrary();
    }).catch(function (error) {
      if (!mounted) {
        return;
      }
      button.disabled = false;
      Shell.reportError(error);
    });
  }

  /* ------------------------------------------------------------- document */

  function setDocumentTitle() {
    Shell.setTitle(I18N.t('import.title'));
  }

  global.Pages = global.Pages || {};
  global.Pages.importer = {
    mount: mount,
    unmount: unmount,
    setDocumentTitle: setDocumentTitle
  };
})(window);
