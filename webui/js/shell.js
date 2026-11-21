/* MarkNest for TOS - the application shell.

   Owns everything that is not a page: the sidebar, the breadcrumb, the topbar
   action slot, the theme switch and the command palette. Pages render into
   #view and call `Shell` when the shell needs to know something - a different
   breadcrumb, different topbar buttons, or that the library changed.

   The sidebar's folder list is a projection of the same library document the
   library page renders, so a folder cannot exist in one and not the other. */

(function (global) {
  'use strict';

  var nodes = {};
  var collapsedKey = 'marknest.collapsed';

  function $(id) {
    return global.document.getElementById(id);
  }

  function init() {
    nodes.app = $('app');
    nodes.sidebar = $('sidebar');
    nodes.scrim = $('scrim');
    nodes.nav = $('nav');
    nodes.crumb = $('crumb');
    nodes.actions = $('topbar-actions');
    nodes.folderList = $('folder-list');
    nodes.storageText = $('storage-text');
    nodes.storageBar = $('storage-bar');
    nodes.connDot = $('conn-dot');
    nodes.connText = $('conn-text');
    nodes.userName = $('user-name');
    nodes.userAvatar = $('user-avatar');

    try {
      if (global.localStorage.getItem(collapsedKey) === '1') {
        nodes.app.classList.add('is-collapsed');
      }
    } catch (error) {
      /* storage may be unavailable; the expanded layout is the default */
    }

    var collapse = $('btn-collapse');
    if (collapse) {
      collapse.addEventListener('click', function () {
        var collapsed = nodes.app.classList.toggle('is-collapsed');
        collapse.setAttribute('title', I18N.t(collapsed ? 'nav.expand' : 'nav.collapse'));
        collapse.setAttribute('aria-label', I18N.t(collapsed ? 'nav.expand' : 'nav.collapse'));
        try {
          global.localStorage.setItem(collapsedKey, collapsed ? '1' : '0');
        } catch (error) {
          /* not fatal */
        }
      });
    }

    var menu = $('btn-menu');
    if (menu) {
      menu.addEventListener('click', function () { setMenuOpen(!nodes.app.classList.contains('is-menu-open')); });
    }
    if (nodes.scrim) {
      nodes.scrim.addEventListener('click', function () { setMenuOpen(false); });
    }

    var search = $('btn-search');
    if (search) {
      search.addEventListener('click', openPalette);
    }

    var theme = $('btn-theme');
    if (theme) {
      theme.addEventListener('click', toggleTheme);
    }

    var user = $('user-chip');
    if (user) {
      user.addEventListener('click', function () { Router.navigate('settings'); });
    }

    var newFolder = $('btn-new-folder');
    if (newFolder) {
      newFolder.addEventListener('click', function () { createFolderFlow(); });
    }

    global.document.addEventListener('keydown', function (event) {
      var mod = event.ctrlKey || event.metaKey;
      if (mod && (event.key === 'k' || event.key === 'K')) {
        event.preventDefault();
        openPalette();
      }
    }, true);

    global.addEventListener('resize', function () {
      if (global.innerWidth > 980) {
        setMenuOpen(false);
      }
    });

    global.addEventListener('beforeunload', Store.releaseAssets);

    Router.onChange(onRoute);
    I18N.apply(global.document);
    renderIdentity();
    renderConnection();
  }

  function setMenuOpen(open) {
    nodes.app.classList.toggle('is-menu-open', !!open);
    if (nodes.scrim) {
      nodes.scrim.hidden = !open;
    }
  }

  function onRoute() {
    var route = Router.current();
    if (!route) {
      return;
    }
    setMenuOpen(false);
    markNav(route.name);
    if (route.name === 'library') {
      markFolder(route.params.f || '');
    } else {
      markFolder(null);
    }
    if (route.name !== 'read' && route.name !== 'edit') {
      defaultCrumb(route);
    }
  }

  function markNav(name) {
    if (!nodes.nav) {
      return;
    }
    var group = name === 'read' || name === 'edit' ? 'library' : name;
    Array.prototype.forEach.call(nodes.nav.querySelectorAll('.nav-item'), function (item) {
      item.classList.toggle('is-active', item.getAttribute('data-route') === group);
    });
  }

  function markFolder(path) {
    if (!nodes.folderList) {
      return;
    }
    Array.prototype.forEach.call(nodes.folderList.querySelectorAll('.folder-item'), function (item) {
      item.classList.toggle('is-active', path !== null && item.getAttribute('data-folder') === path);
    });
  }

  /* ------------------------------------------------------------- breadcrumb */

  function setCrumb(items) {
    if (!nodes.crumb) {
      return;
    }
    while (nodes.crumb.firstChild) {
      nodes.crumb.removeChild(nodes.crumb.firstChild);
    }
    var list = items || [];
    list.forEach(function (item, index) {
      if (index > 0) {
        nodes.crumb.appendChild(UI.icon('chevron-right', 'crumb-sep'));
      }
      var last = index === list.length - 1;
      if (item.href && !last) {
        nodes.crumb.appendChild(UI.el('a', {
          class: 'crumb-item',
          href: item.href,
          text: item.label,
          title: item.label
        }));
      } else {
        nodes.crumb.appendChild(UI.el('span', {
          class: 'crumb-item' + (last ? ' is-current' : ''),
          text: item.label,
          title: item.label
        }));
      }
    });
  }

  function folderCrumb(folder) {
    var items = [{ label: I18N.t('nav.library'), href: Router.href('library', {}) }];
    var accum = '';
    String(folder || '').split('/').forEach(function (segment) {
      if (!segment) {
        return;
      }
      accum = accum ? accum + '/' + segment : segment;
      items.push({
        label: segment,
        href: Router.href('library', { f: accum })
      });
    });
    return items;
  }

  function defaultCrumb(route) {
    if (route.name === 'library') {
      setCrumb(folderCrumb(route.params.f || ''));
    } else if (route.name === 'import') {
      setCrumb([
        { label: I18N.t('nav.library'), href: Router.href('library', {}) },
        { label: I18N.t('nav.import') }
      ]);
    } else if (route.name === 'settings') {
      setCrumb([
        { label: I18N.t('nav.library'), href: Router.href('library', {}) },
        { label: I18N.t('nav.settings') }
      ]);
    }
  }

  function setTitle(text) {
    global.document.title = text ? text + ' · MarkNest' : 'MarkNest';
  }

  /* --------------------------------------------------------- topbar actions */

  function setActions(nodes_) {
    if (!nodes.actions) {
      return;
    }
    while (nodes.actions.firstChild) {
      nodes.actions.removeChild(nodes.actions.firstChild);
    }
    (nodes_ || []).forEach(function (node) {
      if (node) {
        nodes.actions.appendChild(node);
      }
    });
  }

  /* -------------------------------------------------------------- identity */

  function renderIdentity() {
    var me = Store.state.me;
    var name = (me && me.user) || I18N.t('shell.userFallback');
    if (nodes.userName) {
      nodes.userName.textContent = name;
    }
    if (nodes.userAvatar) {
      nodes.userAvatar.textContent = (name.charAt(0) || 'M').toUpperCase();
    }
  }

  function renderConnection() {
    var health = Store.state.health;
    var ok = !health || health.status === 'ok';
    if (nodes.connDot) {
      nodes.connDot.classList.toggle('is-ok', ok);
      nodes.connDot.classList.toggle('is-bad', !ok);
    }
    if (nodes.connText) {
      nodes.connText.textContent = ok ? I18N.t('settings.writable') : I18N.t('shell.libraryDown');
    }
  }

  function renderStorage() {
    var stats = Store.state.stats;
    if (!nodes.storageText) {
      return;
    }
    if (!stats) {
      nodes.storageText.textContent = '—';
      return;
    }
    nodes.storageText.textContent = UI.formatBytes(stats.bytes) + ' · ' +
      I18N.t('library.notesHere', { n: stats.notes });
    if (nodes.storageBar) {
      // There is no quota in the API, so the meter is scaled against a soft
      // 512 MB reference and the exact figure is always written beside it.
      var ratio = Math.min(100, Math.max(2, (stats.bytes / (512 * 1024 * 1024)) * 100));
      nodes.storageBar.style.width = ratio.toFixed(1) + '%';
      nodes.storageText.setAttribute('title', UI.formatBytes(stats.bytes));
    }
  }

  /* --------------------------------------------------------------- folders */

  function renderFolders() {
    if (!nodes.folderList) {
      return;
    }
    var list = Store.state.folders || [];
    var notes = (Store.state.library && Store.state.library.notes) || [];
    while (nodes.folderList.firstChild) {
      nodes.folderList.removeChild(nodes.folderList.firstChild);
    }

    var current = Router.current();
    var active = current && current.name === 'library' ? (current.params.f || '') : null;

    nodes.folderList.appendChild(folderButton({
      path: '',
      label: I18N.t('nav.allNotes'),
      count: notes.length,
      depth: 0,
      icon: 'library',
      active: active === ''
    }));

    list.forEach(function (folder) {
      nodes.folderList.appendChild(folderButton({
        path: folder.path,
        label: folder.name,
        count: folder.count || 0,
        depth: folder.depth || 0,
        icon: 'folder',
        active: active === folder.path
      }));
    });

    if (!list.length) {
      nodes.folderList.appendChild(UI.el('div', {
        class: 'folder-empty',
        text: I18N.t('library.emptyFolderBody')
      }));
    }
  }

  function folderButton(options) {
    var button = UI.el('button', {
      type: 'button',
      class: 'folder-item' + (options.active ? ' is-active' : ''),
      dataset: { folder: options.path },
      title: options.path || I18N.t('nav.allNotes'),
      style: { paddingLeft: (9 + Math.min(options.depth, 8) * 12) + 'px' },
      onclick: function () {
        Store.settings.set('lastFolder', options.path);
        Router.navigate('library', { f: options.path });
      }
    }, [
      UI.icon(options.icon),
      UI.el('span', { class: 'folder-name', text: options.label }),
      UI.el('span', { class: 'folder-count', text: String(options.count) })
    ]);
    button.addEventListener('contextmenu', function (event) {
      event.preventDefault();
      folderMenu(button, options.path);
    });
    return button;
  }

  function folderMenu(anchor, path) {
    var items = [
      {
        label: I18N.t('library.newNote'),
        icon: 'plus',
        onClick: function () { Pages.library.createNoteIn(path); }
      },
      {
        label: I18N.t('nav.newFolder'),
        icon: 'folder-plus',
        onClick: function () { createFolderFlow(path); }
      }
    ];
    if (path) {
      items.push({ divider: true });
      items.push({
        label: I18N.t('common.copy') + ' · ' + I18N.t('common.path'),
        icon: 'copy',
        onClick: function () {
          UI.copyText(path).then(function (ok) {
            UI.toast(ok ? I18N.t('library.pathCopied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
          });
        }
      });
      items.push({
        label: I18N.t('library.deleteFolder'),
        icon: 'trash',
        danger: true,
        onClick: function () {
          removeFolder(path);
        }
      });
    }
    UI.menu(anchor, items, { align: 'left' });
  }

  function removeFolder(path) {
    UI.confirm({
      title: I18N.t('library.deleteFolderTitle'),
      message: I18N.t('library.deleteFolderConfirm'),
      confirmLabel: I18N.t('common.delete'),
      danger: true
    }).then(function (ok) {
      if (!ok) {
        return;
      }
      API.deleteFolder(path).then(function () {
        UI.toast(I18N.t('library.folderDeleted'), 'ok');
        return Store.loadLibraryAndStats();
      }).then(function () {
        renderFolders();
        renderStorage();
        if (Router.current().name === 'library') {
          Router.refresh();
        }
      }).catch(reportError);
    });
  }

  function createFolderFlow(parent) {
    UI.promptDialog({
      title: I18N.t('library.newFolderTitle'),
      label: I18N.t('library.newFolderLabel'),
      placeholder: I18N.t('library.newFolderPlaceholder'),
      hint: parent ? I18N.t('common.path') + ': ' + parent : I18N.t('library.newFolderHint'),
      confirmLabel: I18N.t('common.create')
    }).then(function (value) {
      if (!value) {
        return null;
      }
      var path = value.indexOf('/') === -1 && parent ? parent + '/' + value : value;
      return API.createFolder(path).then(function (result) {
        UI.toast(I18N.t('library.folderCreated'), 'ok');
        return Store.loadLibraryAndStats().then(function () {
          return result;
        });
      });
    }).then(function (result) {
      if (!result) {
        return;
      }
      renderFolders();
      renderStorage();
      if (Router.current().name === 'library') {
        Router.refresh();
      }
    }).catch(reportError);
  }

  /* ---------------------------------------------------------------- theme */

  function toggleTheme() {
    var current = global.document.documentElement.getAttribute('data-theme');
    Store.settings.set('theme', current === 'dark' ? 'light' : 'dark');
  }

  function applyLanguage(tag) {
    I18N.setLanguage(tag);
    Store.settings.set('language', tag);
    I18N.apply(global.document);
    renderStorage();
    renderConnection();
    var route = Router.current();
    if (route) {
      markNav(route.name);
      if (route.name !== 'read' && route.name !== 'edit') {
        defaultCrumb(route);
      }
    }
  }

  /* ------------------------------------------------------- command palette */

  var palette = null;

  function closePalette() {
    if (!palette) {
      return;
    }
    var node = palette;
    palette = null;
    if (node.parentNode) {
      node.parentNode.removeChild(node);
    }
    global.document.removeEventListener('keydown', paletteKeys, true);
  }

  function paletteKeys(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closePalette();
    }
  }

  function openPalette() {
    if (palette) {
      var existing = palette.querySelector('.palette-input');
      if (existing) {
        existing.focus();
      }
      return;
    }

    var input = UI.el('input', {
      class: 'palette-input',
      type: 'search',
      placeholder: I18N.t('search.placeholder'),
      autocomplete: 'off',
      spellcheck: 'false',
      'aria-label': I18N.t('search.title')
    });
    var results = UI.el('div', { class: 'palette-results' });
    var node = UI.el('div', { class: 'modal-backdrop palette-backdrop' }, [
      UI.el('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true' }, [
        UI.el('div', { class: 'palette-input-row' }, [UI.icon('search'), input]),
        results,
        UI.el('div', { class: 'palette-foot' }, [
          UI.el('span', { text: I18N.t('search.hint') }),
          UI.el('span', { class: 'kbd', text: 'Esc' })
        ])
      ])
    ]);
    node.addEventListener('mousedown', function (event) {
      if (event.target === node) {
        closePalette();
      }
    });
    (($('overlay-root') || global.document.body)).appendChild(node);

    palette = node;
    global.document.addEventListener('keydown', paletteKeys, true);
    input.focus();

    var noteResults = [];
    var activeIndex = 0;

    function renderRows(nodes_) {
      UI.clear(results);
      noteResults = nodes_;
      nodes_.forEach(function (entry, index) {
        var row = UI.el('button', {
          type: 'button',
          class: 'palette-item' + (index === activeIndex ? ' is-active' : ''),
          onclick: function () {
            choose(index);
          }
        }, [
          UI.el('span', { class: 'file-chip' }, [UI.icon('file-text')]),
          UI.el('span', { class: 'palette-text' }, [
            UI.el('span', { class: 'palette-title', text: entry.title }),
            entry.path ? UI.el('span', { class: 'palette-path', text: entry.path }) : null,
            entry.snippet ? UI.el('span', { class: 'palette-snippet', text: entry.snippet }) : null
          ])
        ]);
        results.appendChild(row);
      });
    }

    function choose(index) {
      var entry = noteResults[index];
      if (!entry) {
        return;
      }
      closePalette();
      if (entry.route) {
        Router.navigate(entry.route, entry.params || {});
      } else {
        Router.navigate('read', { p: entry.path });
      }
    }

    function emptyRow(title, body) {
      UI.clear(results);
      results.appendChild(UI.el('div', { class: 'palette-empty' }, [
        UI.el('div', { class: 'palette-empty-title', text: title }),
        UI.el('div', { class: 'palette-empty-body', text: body })
      ]));
    }

    function localMatches(query) {
      var list = (Store.state.library && Store.state.library.notes) || [];
      var needle = query.toLowerCase();
      return list.filter(function (note) {
        return note.path.toLowerCase().indexOf(needle) !== -1 ||
          (note.title || '').toLowerCase().indexOf(needle) !== -1;
      }).slice(0, 20).map(function (note) {
        return { title: note.title, path: note.path, snippet: note.excerpt };
      });
    }

    function showInitial() {
      activeIndex = 0;
      var quick = [
        { title: I18N.t('library.newNote'), snippet: I18N.t('editor.markdown'), route: 'edit', params: { p: '' } },
        { title: I18N.t('nav.import'), snippet: I18N.t('import.subtitle'), route: 'import' },
        { title: I18N.t('nav.settings'), snippet: I18N.t('settings.subtitle'), route: 'settings' }
      ];
      var recent = ((Store.state.library && Store.state.library.notes) || []).slice(0, 6)
        .map(function (note) {
          return { title: note.title, path: note.path, snippet: note.excerpt };
        });
      renderRows(quick.concat(recent));
    }

    var runSearch = UI.debounce(function (query) {
      var local = localMatches(query);
      if (local.length) {
        activeIndex = 0;
        renderRows(local);
        return;
      }
      API.search(query, 20).then(function (payload) {
        if (input.value.trim() !== query) {
          return;
        }
        var hits = (payload && payload.hits) || [];
        if (!hits.length) {
          emptyRow(I18N.t('search.noResults'), I18N.t('search.noResultsBody'));
          noteResults = [];
          return;
        }
        activeIndex = 0;
        renderRows(hits.map(function (hit) {
          return { title: hit.title || hit.path, path: hit.path, snippet: hit.snippet };
        }));
      }).catch(function () {
        emptyRow(I18N.t('search.noResults'), I18N.t('err.network'));
      });
    }, 180);

    input.addEventListener('input', function () {
      var query = input.value.trim();
      if (!query) {
        showInitial();
        return;
      }
      runSearch(query);
    });

    input.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        activeIndex = Math.min(noteResults.length - 1, activeIndex + 1);
        renderRows(noteResults);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeIndex = Math.max(0, activeIndex - 1);
        renderRows(noteResults);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        choose(activeIndex);
      }
    });

    // A palette opened before the library has loaded still works: the search
    // endpoint answers, and the quick actions need no data at all.
    showInitial();
    if (!Store.state.library) {
      Store.loadLibraryAndStats().then(function () {
        if (palette === node && !input.value.trim()) {
          showInitial();
        }
        renderFolders();
        renderStorage();
      }).catch(function () {});
    }
  }

  /* ------------------------------------------------------------------ misc */

  function reportError(error) {
    UI.toast((error && error.message) || I18N.t('err.unknown'), 'bad');
  }

  function sync() {
    renderIdentity();
    renderConnection();
    renderWelcome();
    renderFolders();
    renderStorage();
  }

  /* A library that could not be read is the one failure that changes what the
     whole application can offer, so it is stated in the sidebar rather than
     only on the page that happens to ask first. */
  function renderWelcome() {
    var health = Store.state.health;
    var me = Store.state.me;
    if (me && me.exists === false) {
      renderConnection();
    } else if (health && health.library_ready === false) {
      if (nodes.connDot) {
        nodes.connDot.classList.remove('is-ok');
        nodes.connDot.classList.add('is-bad');
      }
      if (nodes.connText) {
        nodes.connText.textContent = I18N.t('shell.libraryDown');
      }
    }
  }

  global.Shell = {
    init: init,
    sync: sync,
    setCrumb: setCrumb,
    setActions: setActions,
    setTitle: setTitle,
    renderFolders: renderFolders,
    renderStorage: renderStorage,
    folderCrumb: folderCrumb,
    createFolderFlow: createFolderFlow,
    openPalette: openPalette,
    applyLanguage: applyLanguage,
    toggleTheme: toggleTheme,
    reportError: reportError,
    setMenuOpen: setMenuOpen
  };
})(window);
