/* MarkNest for TOS - document list and file management.

   The library is one flat note document plus one folder index. Rendering it
   as cards or rows is presentation; the underlying data is the same list the
   sidebar projects into folders, so a note can never appear in one place and
   not the other.

   Search here is local and instantaneous. It runs over the listing that is
   already in memory (title, path, excerpt); the server index is used by the
   command palette, which has to answer for notes the list may have truncated. */

(function (global) {
  'use strict';

  var state = {
    query: '',
    sort: 'updated',
    view: 'grid',
    folder: '',
    busy: false
  };

  var nodes = {};
  var mounted = false;

  function mount(host, params) {
    mounted = true;
    state.query = '';
    state.folder = (params && params.f) || '';
    state.sort = Store.settings.get('sort') || 'updated';
    state.view = Store.settings.get('view') || 'grid';

    var page = UI.el('div', { class: 'page page-library' });
    var scroll = UI.el('div', { class: 'page-scroll' });
    page.appendChild(scroll);
    host.appendChild(page);

    nodes.scroll = scroll;
    nodes.head = UI.el('div', { class: 'page-head' });
    nodes.stats = UI.el('section', { class: 'stats', 'aria-label': I18N.t('library.title') });
    nodes.toolbar = UI.el('div', { class: 'library-toolbar' });
    nodes.body = UI.el('div', { class: 'library-body' });
    nodes.body.id = 'library-body';

    scroll.appendChild(nodes.head);
    scroll.appendChild(nodes.stats);
    scroll.appendChild(nodes.toolbar);
    scroll.appendChild(nodes.body);

    renderHead();
    renderToolbar();
    Shell.setCrumb(folderTrail(state.folder));
    Shell.setTitle(state.folder ? state.folder : I18N.t('library.title'));
    Shell.setActions([
      UI.el('button', {
        type: 'button',
        class: 'btn',
        onclick: function () { Router.navigate('import'); }
      }, [UI.icon('upload'), UI.el('span', { text: I18N.t('library.import') })]),
      UI.el('button', {
        type: 'button',
        class: 'btn btn-primary',
        onclick: function () { createNoteIn(state.folder); }
      }, [UI.icon('plus'), UI.el('span', { text: I18N.t('library.newNote') })])
    ]);

    load();
  }

  function unmount() {
    mounted = false;
    nodes = {};
  }

  function folderTrail(folder) {
    if (!folder) {
      return Shell.folderCrumb('');
    }
    // The heading already names the folder being viewed, so the trail stops at
    // its parent instead of repeating it in the top bar.
    var parent = folder.indexOf('/') === -1 ? '' : folder.slice(0, folder.lastIndexOf('/'));
    return Shell.folderCrumb(parent);
  }

  /* ------------------------------------------------------------------ head */

  function renderHead() {
    UI.clear(nodes.head);
    var title = state.folder ? lastSegment(state.folder) : I18N.t('library.allNotes');
    var sub = state.folder
      ? I18N.t('library.inFolder', { name: state.folder })
      : I18N.t('library.subtitle');
    nodes.head.appendChild(UI.el('div', { class: 'page-head-text' }, [
      UI.el('h1', { class: 'page-title', text: title }),
      UI.el('p', { class: 'page-sub', text: sub })
    ]));
    var actions = UI.el('div', { class: 'page-head-actions' }, []);
    if (state.folder) {
      actions.appendChild(UI.el('button', {
        type: 'button',
        class: 'btn btn-ghost',
        onclick: function () { Router.navigate('library', {}); }
      }, [UI.icon('arrow-left'), UI.el('span', { text: I18N.t('library.allNotes') })]));
    }
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn btn-ghost',
      onclick: openFromNas
    }, [UI.icon('folder'), UI.el('span', { text: I18N.t('library.openFromNas') })]));
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn btn-ghost',
      title: I18N.t('common.refresh'),
      onclick: function () { load(true); }
    }, [UI.icon('refresh'), UI.el('span', { text: I18N.t('common.refresh') })]));
    nodes.head.appendChild(actions);
  }

  /* Browse the NAS folder that backs the library and open a file by path, so a
     note dropped in over SMB can be reached without waiting for the grid. */
  function openFromNas() {
    var list = UI.el('div', { class: 'nas-list' });
    var pathLabel = UI.el('span', { class: 'nas-path-text' });
    var current = '';
    var up = UI.el('button', {
      type: 'button',
      class: 'btn btn-sm btn-ghost',
      onclick: function () { if (current) { load(parentOf(current)); } }
    }, [UI.icon('arrow-up'), UI.el('span', { text: I18N.t('library.nasUp') })]);
    var dialog = UI.modal({
      title: I18N.t('library.openFromNas'),
      subtitle: I18N.t('library.openFromNasHint'),
      body: UI.el('div', { class: 'nas-browser' }, [
        UI.el('p', { class: 'nas-hint', text: I18N.t('library.nasScopeHint') }),
        UI.el('div', { class: 'nas-bar' }, [up, pathLabel]),
        list
      ]),
      actions: [{ label: I18N.t('common.close'), close: true }]
    });

    function parentOf(path) {
      var at = path.lastIndexOf('/');
      return at < 0 ? '' : path.slice(0, at);
    }

    function locationLabel(path) {
      var root = I18N.t('library.allNotes');
      return path ? root + ' / ' + path.split('/').join(' / ') : root;
    }

    function openNote(path) {
      dialog.close(true);
      Router.navigate('read', { p: path });
    }

    function render(result) {
      UI.clear(list);
      if (!result.entries || !result.entries.length) {
        list.appendChild(UI.el('div', {
          class: 'nas-empty',
          text: I18N.t('library.nasEmpty')
        }));
        return;
      }
      result.entries.forEach(function (entry) {
        var isDir = entry.type === 'dir';
        var row = UI.el(isDir || entry.note ? 'button' : 'div', {
          type: isDir || entry.note ? 'button' : null,
          class: 'nas-row' + (isDir || entry.note ? '' : ' is-disabled'),
          onclick: isDir
            ? function () { load(entry.path); }
            : (entry.note ? function () { openNote(entry.path); } : null)
        }, [
          UI.icon(isDir ? 'folder' : 'file-text'),
          UI.el('span', { class: 'nas-name', text: entry.name }),
          UI.el('span', {
            class: 'nas-meta',
            text: isDir ? '' : (entry.note
              ? UI.formatBytes(entry.size)
              : I18N.t('library.nasUnsupported'))
          }),
          isDir ? UI.icon('chevron-right') : null
        ]);
        list.appendChild(row);
      });
    }

    function load(path) {
      list.textContent = '';
      list.appendChild(UI.el('div', { class: 'nas-empty', text: I18N.t('common.loading') }));
      API.getTree(path).then(function (result) {
        current = result.path || '';
        pathLabel.textContent = locationLabel(current);
        // At the root there is nowhere above; showing a dead button reads as
        // broken, so it only appears once a folder has been entered.
        up.style.display = current ? '' : 'none';
        render(result);
      }).catch(function (error) {
        UI.toast(I18N.errorText(error), 'bad');
        render({ entries: [] });
      });
    }

    up.style.display = 'none';
    pathLabel.textContent = locationLabel('');
    load('');
  }

  function lastSegment(path) {
    var parts = String(path || '').split('/');
    return parts[parts.length - 1] || path;
  }

  /* ----------------------------------------------------------------- stats */

  function renderStats() {
    UI.clear(nodes.stats);
    var stats = Store.statsFor(state.folder);
    var view = Store.state.library;
    var notes = stats ? stats.notes : (view ? view.totals.notes : 0);
    var folders = stats ? stats.folders : (view ? view.folders.length : 0);
    var bytes = stats ? stats.bytes : (view ? view.totals.bytes : 0);
    var versions = stats ? stats.versions : 0;

    [
      ['file-text', notes, I18N.t('library.statsNotes')],
      ['folder', folders, I18N.t('library.statsFolders')],
      ['library', UI.formatBytes(bytes), I18N.t('library.statsSize')],
      ['clock', versions, I18N.t('settings.versionCount')]
    ].forEach(function (entry) {
      nodes.stats.appendChild(UI.el('div', { class: 'stat' }, [
        UI.el('div', { class: 'stat-icon' }, [UI.icon(entry[0])]),
        UI.el('div', null, [
          UI.el('div', { class: 'stat-value', text: String(entry[1]) }),
          UI.el('div', { class: 'stat-label', text: entry[2] })
        ])
      ]));
    });
  }

  /* --------------------------------------------------------------- toolbar */

  function renderToolbar() {
    UI.clear(nodes.toolbar);

    var input = UI.el('input', {
      class: 'input',
      type: 'search',
      placeholder: I18N.t('library.searchPlaceholder'),
      autocomplete: 'off',
      value: state.query
    });
    input.addEventListener('input', UI.debounce(function () {
      state.query = input.value.trim();
      renderNotes();
    }, 120));

    nodes.toolbar.appendChild(UI.el('label', { class: 'input-icon' }, [
      UI.icon('search'), input
    ]));

    nodes.toolbar.appendChild(UI.el('div', { class: 'library-scope' }, [
      UI.icon('folder'),
      UI.el('strong', { text: state.folder ? state.folder : I18N.t('library.allNotes') })
    ]));

    var select = UI.el('select', { class: 'select', 'aria-label': I18N.t('library.sortLabel') }, [
      UI.el('option', { value: 'updated', text: I18N.t('library.sortUpdated') }),
      UI.el('option', { value: 'name', text: I18N.t('library.sortName') }),
      UI.el('option', { value: 'size', text: I18N.t('library.sortSize') })
    ]);
    select.value = state.sort;
    select.addEventListener('change', function () {
      state.sort = select.value;
      Store.settings.set('sort', state.sort);
      renderNotes();
    });

    var grid = UI.el('button', {
      type: 'button',
      class: 'icon-btn' + (state.view === 'grid' ? ' is-active' : ''),
      title: I18N.t('library.grid'),
      'aria-label': I18N.t('library.grid'),
      onclick: function () { setView('grid'); }
    }, [UI.icon('grid')]);
    var list = UI.el('button', {
      type: 'button',
      class: 'icon-btn' + (state.view === 'list' ? ' is-active' : ''),
      title: I18N.t('library.list'),
      'aria-label': I18N.t('library.list'),
      onclick: function () { setView('list'); }
    }, [UI.icon('list')]);

    nodes.toolbar.appendChild(UI.el('div', { class: 'library-toolbar-tail' }, [
      select,
      UI.el('div', { class: 'segmented', role: 'group', 'aria-label': I18N.t('library.viewLabel') }, [grid, list])
    ]));
  }

  function setView(view) {
    state.view = view === 'list' ? 'list' : 'grid';
    Store.settings.set('view', state.view);
    renderToolbar();
    renderNotes();
  }

  /* ------------------------------------------------------------------ load */

  function load(showSkeleton) {
    if (!mounted || state.busy) {
      return;
    }
    state.busy = true;
    if (showSkeleton) {
      UI.clear(nodes.body);
      UI.skeleton(nodes.body, 6);
    }
    Store.loadLibraryAndStats(state.folder).then(function () {
      state.busy = false;
      if (!mounted) {
        return;
      }
      renderStats();
      renderNotes();
      Shell.renderFolders();
      Shell.renderStorage();
    }, function (error) {
      state.busy = false;
      if (!mounted) {
        return;
      }
      failed(error);
    });
  }

  function failed(error) {
    UI.clear(nodes.body);
    var me = Store.state.me;
    var action = null;
    if (me && me.exists === false && TosHost.canOpenSharedFolders()) {
      action = {
        label: I18N.t('shell.openShared'),
        onClick: function () { TosHost.openSharedFolders(); }
      };
    }
    UI.errorBox(nodes.body, (error && error.message) || I18N.t('err.network'),
      function () { load(true); },
      (error && error.code === 3003) || (me && me.readable === false)
        ? I18N.t('shell.libraryDownHint') : '',
      action);
  }

  /* ---------------------------------------------------------------- filter */

  function visibleNotes() {
    var notes = (Store.state.library && Store.state.library.notes) || [];
    var folder = state.folder;
    var query = state.query.toLowerCase();
    var result = notes.filter(function (note) {
      if (folder && note.folder !== folder && note.path.indexOf(folder + '/') !== 0) {
        return false;
      }
      if (!query) {
        return true;
      }
      return note.path.toLowerCase().indexOf(query) !== -1 ||
        (note.title || '').toLowerCase().indexOf(query) !== -1 ||
        (note.excerpt || '').toLowerCase().indexOf(query) !== -1;
    });
    result.sort(function (a, b) {
      if (state.sort === 'name') {
        return (a.title || a.path).localeCompare(b.title || b.path, I18N.getLanguage());
      }
      if (state.sort === 'size') {
        return (b.size || 0) - (a.size || 0);
      }
      return (b.mtime_ns || 0) - (a.mtime_ns || 0);
    });
    return result;
  }

  function renderNotes() {
    if (!nodes.body) {
      return;
    }
    var notes = visibleNotes();
    UI.clear(nodes.body);

    if (state.query) {
      nodes.body.appendChild(UI.el('div', { class: 'library-result-count' }, [
        UI.el('span', { text: I18N.t('search.results', { n: notes.length }) })
      ]));
    }

    if (!notes.length) {
      nodes.body.appendChild(emptyFor());
      return;
    }

    if (state.view === 'list') {
      var list = UI.el('div', { class: 'note-list' });
      notes.forEach(function (note) {
        list.appendChild(noteRow(note));
      });
      nodes.body.appendChild(list);
    } else {
      var grid = UI.el('div', { class: 'note-grid' });
      notes.forEach(function (note) {
        grid.appendChild(noteCard(note));
      });
      nodes.body.appendChild(grid);
    }
  }

  function emptyFor() {
    var hasLibrary = (Store.state.library && Store.state.library.notes.length);
    if (state.query) {
      return UI.emptyState({
        icon: 'search',
        title: I18N.t('library.noResults'),
        body: I18N.t('library.noResultsBody'),
        actions: [UI.el('button', {
          type: 'button',
          class: 'btn',
          text: I18N.t('library.clearFilters'),
          onclick: function () {
            state.query = '';
            renderToolbar();
            renderNotes();
          }
        })]
      });
    }
    if (hasLibrary && state.folder) {
      return UI.emptyState({
        icon: 'folder',
        title: I18N.t('library.emptyFolder'),
        body: I18N.t('library.emptyFolderBody', {
          name: lastSegment(state.folder) || state.folder
        }),
        actions: [UI.el('button', {
          type: 'button',
          class: 'btn btn-primary',
          text: I18N.t('library.newNote'),
          onclick: function () { createNoteIn(state.folder); }
        }), UI.el('button', {
          type: 'button',
          class: 'btn',
          text: I18N.t('library.allNotes'),
          onclick: function () { Router.navigate('library', {}); }
        })]
      });
    }
    return UI.emptyState({
      icon: 'book-open',
      title: I18N.t('library.emptyTitle'),
      body: I18N.t('library.emptyBody'),
      actions: [
        UI.el('button', {
          type: 'button',
          class: 'btn btn-primary',
          text: I18N.t('library.newNote'),
          onclick: function () { createNoteIn(''); }
        }),
        UI.el('button', {
          type: 'button',
          class: 'btn',
          text: I18N.t('library.import'),
          onclick: function () { Router.navigate('import'); }
        })
      ]
    });
  }

  /* ----------------------------------------------------------------- cards */

  function isMarkdown(note) {
    return /\.(md|markdown|mdown)$/i.test(note.path);
  }

  function noteCard(note) {
    var card = UI.el('article', {
      class: 'note-card',
      tabindex: '0',
      role: 'button',
      'aria-label': note.title || note.path,
      onclick: function () { open(note); },
      onkeydown: function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open(note);
        }
      }
    }, [
      UI.el('div', { class: 'note-card-top' }, [
        UI.el('span', { class: 'file-chip' + (isMarkdown(note) ? ' is-text' : '') },
          [UI.icon(isMarkdown(note) ? 'file-text' : 'file')]),
        UI.el('button', {
          type: 'button',
          class: 'icon-btn icon-btn-sm card-menu-btn',
          title: I18N.t('common.more'),
          'aria-label': I18N.t('common.more'),
          onclick: function (event) {
            event.stopPropagation();
            noteMenu(event.currentTarget, note);
          }
        }, [UI.icon('more')])
      ]),
      UI.el('h3', { class: 'note-card-title', text: note.title || note.path }),
      UI.el('p', { class: 'note-card-excerpt', text: note.excerpt || I18N.t('common.empty') }),
      UI.el('div', { class: 'note-card-foot' }, [
        UI.el('span', { class: 'note-card-folder' }, [
          UI.icon('folder'), UI.el('span', { text: note.folder || I18N.t('common.rootFolder') })
        ]),
        UI.el('span', { class: 'note-card-dot' }),
        UI.el('span', { text: UI.formatBytes(note.size) }),
        UI.el('span', { class: 'meta-time', text: UI.formatTimeAgo(note.mtime_ns) })
      ])
    ]);
    return card;
  }

  function noteRow(note) {
    var row = UI.el('div', {
      class: 'note-row',
      tabindex: '0',
      role: 'button',
      'aria-label': note.title || note.path,
      onclick: function () { open(note); },
      onkeydown: function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open(note);
        }
      }
    }, [
      UI.el('span', { class: 'file-chip' + (isMarkdown(note) ? ' is-text' : '') },
        [UI.icon(isMarkdown(note) ? 'file-text' : 'file')]),
      UI.el('span', { class: 'note-row-title', text: note.title || note.path }),
      UI.el('span', { class: 'note-row-folder', text: note.folder || I18N.t('common.rootFolder') }),
      UI.el('span', { class: 'note-row-size', text: UI.formatBytes(note.size) }),
      UI.el('span', { class: 'note-row-time', text: UI.formatTimeAgo(note.mtime_ns) }),
      UI.el('button', {
        type: 'button',
        class: 'icon-btn icon-btn-sm',
        title: I18N.t('common.more'),
        'aria-label': I18N.t('common.more'),
        onclick: function (event) {
          event.stopPropagation();
          noteMenu(event.currentTarget, note);
        }
      }, [UI.icon('more')])
    ]);
    return row;
  }

  /* ---------------------------------------------------------------- actions */

  function open(note) {
    Router.navigate('read', { p: note.path });
  }

  function noteMenu(anchor, note) {
    UI.menu(anchor, [
      { label: I18N.t('library.openReader'), icon: 'book-open', onClick: function () { open(note); } },
      { label: I18N.t('library.editNote'), icon: 'pen', onClick: function () { Router.navigate('edit', { p: note.path }); } },
      { label: I18N.t('library.copyPath'), icon: 'copy', onClick: function () {
        UI.copyText(note.path).then(function (ok) {
          UI.toast(ok ? I18N.t('library.pathCopied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
        });
      } },
      { divider: true },
      { label: I18N.t('common.rename'), icon: 'pen', onClick: function () { rename(note); } },
      { label: I18N.t('common.delete'), icon: 'trash', danger: true, onClick: function () { remove(note); } }
    ]);
  }

  function rename(note) {
    UI.promptDialog({
      title: I18N.t('library.renameTitle'),
      label: I18N.t('library.renameLabel'),
      value: note.path,
      hint: I18N.t('library.newNoteHint'),
      confirmLabel: I18N.t('common.rename')
    }).then(function (value) {
      if (!value || value === note.path) {
        return null;
      }
      var target = value.indexOf('/') === -1 && note.folder ? note.folder + '/' + value : value;
      return API.renameNote({ from: note.path, to: target }).then(function (result) {
        UI.toast(I18N.t('library.renamed'), 'ok');
        return result;
      });
    }).then(function (result) {
      if (!result) {
        return;
      }
      refresh();
    }).catch(Shell.reportError);
  }

  function remove(note) {
    UI.confirm({
      title: I18N.t('library.deleteTitle', { name: note.title || note.path }),
      message: I18N.t('library.deleteConfirm'),
      confirmLabel: I18N.t('common.delete'),
      danger: true
    }).then(function (ok) {
      if (!ok) {
        return;
      }
      API.deleteNote(note.path).then(function () {
        UI.toast(I18N.t('library.deleted', { name: note.title || note.path }), 'ok');
        refresh();
      }).catch(Shell.reportError);
    });
  }

  function createNoteIn(folder) {
    var suggested = (folder ? folder + '/' : '') + I18N.t('common.untitled') + '.md';
    UI.promptDialog({
      title: I18N.t('library.newNoteTitle'),
      label: I18N.t('library.newNoteLabel'),
      value: suggested,
      placeholder: I18N.t('library.newNotePlaceholder'),
      hint: I18N.t('library.newNoteHint'),
      confirmLabel: I18N.t('common.create')
    }).then(function (value) {
      if (!value) {
        return null;
      }
      var path = value;
      if (path.indexOf('/') === -1 && folder) {
        path = folder + '/' + path;
      }
      return API.createNote({ path: path, content: '', eol: 'lf' }).then(function (note) {
        UI.toast(I18N.t('library.noteCreated', { name: note.name || note.path }), 'ok');
        return note;
      });
    }).then(function (note) {
      if (!note) {
        return;
      }
      refresh();
      Router.navigate('edit', { p: note.path });
    }).catch(Shell.reportError);
  }

  function refresh() {
    return Store.loadLibraryAndStats(state.folder).then(function () {
      if (mounted) {
        renderStats();
        renderNotes();
      }
      Shell.renderFolders();
      Shell.renderStorage();
    }).catch(Shell.reportError);
  }

  function setDocumentTitle(params) {
    var folder = params && params.f;
    Shell.setTitle(folder ? lastSegment(folder) : I18N.t('library.title'));
  }

  global.Pages = global.Pages || {};
  global.Pages.library = {
    mount: mount,
    unmount: unmount,
    setDocumentTitle: setDocumentTitle,
    createNoteIn: createNoteIn,
    refresh: refresh
  };
})(window);
