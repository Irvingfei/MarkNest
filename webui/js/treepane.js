/* MarkNest for TOS - the note tree.

   The API lists one directory at a time, so the tree is built lazily: a folder
   is expanded on first click and its children are cached until a refresh. That
   keeps opening the application to one small request regardless of how large
   the library is, which matters because the whole tree travels over the
   platform's Unix-socket proxy as JSON. */

(function (global) {
  'use strict';

  var state = {
    children: {},
    expanded: {},
    current: '',
    loading: false,
    onOpen: null
  };

  var hosts = {};

  function cacheHosts() {
    hosts.body = document.getElementById('tree-body');
    hosts.footer = document.getElementById('tree-footer');
  }

  function baseName(path) {
    var trimmed = String(path || '').replace(/\/+$/, '');
    var index = trimmed.lastIndexOf('/');
    return index === -1 ? trimmed : trimmed.slice(index + 1);
  }

  function parentOf(path) {
    var index = String(path || '').lastIndexOf('/');
    return index === -1 ? '' : path.slice(0, index);
  }

  function setFooter(text, kind) {
    if (!hosts.footer) {
      return;
    }
    hosts.footer.textContent = text || '';
    hosts.footer.className = 'pane-foot' + (kind ? ' is-' + kind : '');
  }

  function ensure(path) {
    if (state.children[path]) {
      return Promise.resolve(state.children[path]);
    }
    return API.getTree(path).then(function (payload) {
      state.children[path] = (payload && payload.entries) || [];
      return state.children[path];
    });
  }

  function openNote(path) {
    state.current = path;
    render();
    if (typeof state.onOpen === 'function') {
      state.onOpen(path);
    }
  }

  function row(entry, depth) {
    var isDir = entry.type === 'dir';
    var expanded = !!state.expanded[entry.path];
    var node = UI.el('button', {
      type: 'button',
      class: 'tree-row' +
        (isDir ? ' is-dir' : '') +
        (entry.path === state.current ? ' is-current' : '') +
        (entry.type === 'other' ? ' is-other' : ''),
      title: entry.path
    });
    node.style.paddingLeft = (10 + depth * 14) + 'px';

    if (isDir) {
      node.appendChild(UI.el('span', { class: 'tree-caret', text: expanded ? '▾' : '▸' }));
    } else {
      node.appendChild(UI.el('span', { class: 'tree-caret', text: '' }));
    }
    node.appendChild(UI.el('span', { class: 'tree-name', text: entry.name }));
    if (entry.type === 'other') {
      node.appendChild(UI.el('span', { class: 'tree-meta', text: I18N.t('tree.unsupported') }));
    }

    node.addEventListener('click', function () {
      if (isDir) {
        toggleDir(entry.path);
        return;
      }
      if (entry.type !== 'note') {
        UI.toast(I18N.t('tree.unsupported'), 'warn');
        return;
      }
      openNote(entry.path);
    });

    node.addEventListener('contextmenu', function (event) {
      event.preventDefault();
      menu(entry, event);
    });

    return node;
  }

  function toggleDir(path) {
    if (state.expanded[path]) {
      delete state.expanded[path];
      render();
      return;
    }
    state.expanded[path] = true;
    render();
    ensure(path).then(function () {
      render();
    }).catch(function (error) {
      delete state.expanded[path];
      setFooter(I18N.errorText(error), 'is-bad');
      render();
    });
  }

  function renderInto(container, path, depth) {
    var entries = state.children[path] || [];
    entries.forEach(function (entry) {
      container.appendChild(row(entry, depth));
      if (entry.type === 'dir' && state.expanded[entry.path]) {
        renderInto(container, entry.path, depth + 1);
      }
    });
  }

  function render() {
    if (!hosts.body) {
      return;
    }
    UI.clear(hosts.body);
    var list = UI.el('div', { class: 'tree-list' });
    var rootEntries = state.children[''];
    if (!rootEntries) {
      UI.loading(hosts.body, I18N.t('common.loading'));
      return;
    }
    if (!rootEntries.length) {
      hosts.body.appendChild(UI.el('div', { class: 'empty', text: I18N.t('tree.empty') }));
      return;
    }
    renderInto(list, '', 0);
    hosts.body.appendChild(list);
  }

  function refresh(path) {
    delete state.children[path === undefined ? '' : path];
    return reload();
  }

  function reload() {
    state.loading = true;
    return ensure('').then(function () {
      state.loading = false;
      render();
    }).catch(function (error) {
      state.loading = false;
      UI.clear(hosts.body);
      hosts.body.appendChild(
        UI.errorBox(UI.el('div'), I18N.errorText(error), reload)
      );
    });
  }

  /* ------------------------------------------------------------- mutations */

  function newNote() {
    var suggested = state.current
      ? parentOf(state.current) + (parentOf(state.current) ? '/' : '')
      : '';
    var answer = global.prompt(I18N.t('tree.newNotePrompt'), suggested + I18N.t('tree.newNoteDefault'));
    if (!answer) {
      return;
    }
    API.createNote({ path: answer.trim(), content: '' }).then(function (created) {
      // The note may have created folders on the way, so the whole tree is
      // re-read rather than patched: guessing which parents appeared is how a
      // tree ends up disagreeing with the disk.
      delete state.children;
      state.children = {};
      state.expanded[parentOf(created.path)] = true;
      return reload().then(function () {
        openNote(created.path);
        UI.toast(I18N.t('tree.created', { name: baseName(created.path) }), 'ok');
      });
    }).catch(function (error) {
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  function rename(entry) {
    var answer = global.prompt(I18N.t('tree.renamePrompt'), entry.path);
    if (!answer || answer === entry.path) {
      return;
    }
    API.renameNote({ from: entry.path, to: answer.trim() }).then(function () {
      state.children = {};
      state.expanded = {};
      return reload().then(function () {
        UI.toast(I18N.t('tree.renamed'), 'ok');
      });
    }).catch(function (error) {
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  function remove(entry) {
    if (!global.confirm(I18N.t('tree.deleteConfirm', { name: entry.name }))) {
      return;
    }
    API.deleteNote(entry.path).then(function () {
      if (state.current === entry.path) {
        state.current = '';
        if (typeof state.onOpen === 'function') {
          state.onOpen('');
        }
      }
      state.children = {};
      return reload().then(function () {
        UI.toast(I18N.t('tree.deleted', { name: entry.name }), 'ok');
      });
    }).catch(function (error) {
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  /* A right-click menu rather than a button on every row: a note library is
     mostly read, and a permanent delete affordance beside every note is a
     hazard with no upside. The menu is positioned at the pointer and closes on
     the next click anywhere. */
  function closeMenu() {
    var existing = document.getElementById('tree-menu');
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  function menu(entry, event) {
    closeMenu();
    var node = UI.el('div', { class: 'ctx-menu', id: 'tree-menu' }, [
      UI.el('button', {
        type: 'button',
        class: 'ctx-item',
        text: I18N.t('tree.rename'),
        onclick: function () {
          closeMenu();
          rename(entry);
        }
      }),
      UI.el('button', {
        type: 'button',
        class: 'ctx-item is-danger',
        text: I18N.t('tree.delete'),
        onclick: function () {
          closeMenu();
          remove(entry);
        }
      })
    ]);
    node.style.left = Math.max(4, event.clientX) + 'px';
    node.style.top = Math.max(4, event.clientY) + 'px';
    document.body.appendChild(node);
    global.setTimeout(function () {
      document.addEventListener('mousedown', closeMenu, { once: true });
    }, 0);
  }

  function init(options) {
    cacheHosts();
    if (options && typeof options.onOpen === 'function') {
      state.onOpen = options.onOpen;
    }
  }

  function setCurrent(path) {
    state.current = path || '';
    render();
  }

  global.TreePane = {
    init: init,
    reload: reload,
    refresh: refresh,
    newNote: newNote,
    setCurrent: setCurrent,
    setFooter: setFooter,
    render: render,
    current: function () { return state.current; }
  };
})(window);
