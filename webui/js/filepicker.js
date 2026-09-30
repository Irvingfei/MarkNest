/* MarkNest for TOS - the open-file dialog.
 *
 * Two sources, one dialog, because they answer the same question and the person
 * asking it should not have to know where the file lives before choosing where
 * to look. The library side renders the same tree the left pane does; the local
 * side imports, since a note that is not in the library would be a second place
 * notes live and there is deliberately only one. */

(function (global) {
  'use strict';

  /* The types a local file may have. The markup's accept attribute is a filter
     in the file dialog, not a constraint - "all files" is one click away - so
     the same list is enforced here, where it cannot be overridden. It is a
     literal rather than a read of /options because it is what the frontend
     promises in the design; the server still refuses a note that is too large,
     which is a limit only it can know. */
  var LOCAL_TYPES = ['.md', '.markdown', '.mdown', '.txt'];

  var state = { open: false, tab: 'library', onOpen: null };
  var hosts = {};
  var lastFocus = null;

  function cacheHosts() {
    hosts.modal = document.getElementById('file-picker');
    hosts.body = document.getElementById('picker-body');
    hosts.tabLibrary = document.getElementById('picker-tab-library');
    hosts.tabLocal = document.getElementById('picker-tab-local');
    hosts.browse = document.getElementById('picker-browse');
    hosts.file = document.getElementById('picker-file');
    hosts.close = document.getElementById('picker-close');
  }

  function setTab(tab) {
    state.tab = tab;
    var isLibrary = tab === 'library';
    hosts.tabLibrary.classList.toggle('is-active', isLibrary);
    hosts.tabLocal.classList.toggle('is-active', !isLibrary);
    hosts.browse.hidden = isLibrary;
    if (isLibrary) {
      renderLibrary('');
    } else {
      UI.clear(hosts.body);
      hosts.body.appendChild(UI.el('div', {
        class: 'empty',
        text: I18N.t('picker.localHint')
      }));
    }
  }

  function renderLibrary(path) {
    UI.loading(hosts.body, I18N.t('common.loading'));
    API.getTree(path).then(function (payload) {
      UI.clear(hosts.body);
      var entries = (payload && payload.entries) || [];
      if (!entries.length) {
        hosts.body.appendChild(UI.el('div', { class: 'empty', text: I18N.t('tree.empty') }));
        return;
      }
      // Reuses the tree row styling rather than inventing a second look for
      // the same thing. `.nas-*` does not exist in this stylesheet - that was
      // the previous application's naming - so a copy of it here would render
      // as unstyled markup.
      var list = UI.el('div', { class: 'tree-list' });
      entries.forEach(function (entry) {
        // The same question the tree asks, asked the same way: the backend's
        // `note` boolean, not a `type` value. `type` is derived from it, so a
        // literal test here would be a second place to keep in step with
        // library.py - which is the drift that made the tree refuse every note.
        // A folder is neither: it is kept, and descended into on click, even
        // though `note` is false for it too.
        if (entry.type !== 'dir' && !entry.note) {
          return;
        }
        var row = UI.el('button', { type: 'button',
                                    class: 'tree-row' + (entry.type === 'dir' ? ' is-dir' : '') });
        row.appendChild(UI.el('span', { class: 'tree-caret', 'aria-hidden': 'true',
                                        text: entry.type === 'dir' ? '▸' : '' }));
        row.appendChild(UI.el('span', { class: 'tree-name', text: entry.name, title: entry.name }));
        row.addEventListener('click', function () {
          if (entry.type === 'dir') {
            renderLibrary(entry.path);
            return;
          }
          var callback = state.onOpen;
          close();
          if (callback) {
            callback(entry.path, true);
          }
        });
        list.appendChild(row);
      });
      hosts.body.appendChild(list);
    }).catch(function (error) {
      UI.clear(hosts.body);
      hosts.body.appendChild(UI.errorBox(UI.el('div'), I18N.errorText(error), function () {
        renderLibrary(path);
      }));
    });
  }

  /* The extension a name claims, lower-cased. A name with no dot, or one whose
     first character is the dot, has none and is refused by the caller: an
     extension is the only type signal a browser gives for a local file, and
     guessing from its absence is how a file becomes a note nobody can read. */
  function extensionOf(name) {
    var text = String(name || '');
    var dot = text.lastIndexOf('.');
    return dot > 0 ? text.slice(dot).toLowerCase() : '';
  }

  /* Importing means "make this a real note". Reading the file and posting it
     as a new note keeps the library the single place a note lives; trying to
     edit a local file in place would leave the application unable to promise
     where the user's writing actually is. */
  function importFile(file) {
    var name = (file && file.name) || '';
    // The MIME type is deliberately not consulted: a .md written on Windows
    // commonly reports text/plain or nothing at all, so a check against it
    // would refuse files this dialog exists to accept.
    if (LOCAL_TYPES.indexOf(extensionOf(name)) === -1) {
      UI.toast(I18N.t('picker.badType'), 'warn');
      return;
    }
    var reader = new global.FileReader();
    reader.onload = function () {
      attempt(name, reader.result, 1);
    };
    reader.onerror = function () {
      UI.toast(I18N.t('picker.readFailed'), 'bad');
    };
    reader.readAsText(file);
  }

  function attempt(name, content, round) {
    API.createNote({ path: name, content: content }).then(function (note) {
      var callback = state.onOpen;
      close();
      UI.toast(I18N.t('tree.created', { name: note.path }), 'ok');
      if (callback) {
        callback(note.path, true);
      }
    }).catch(function (error) {
      if (error && error.code === 3006 && round < 100) {
        // A name that is taken is not a failure, it is the next name.
        var split = name.lastIndexOf('.');
        var stem = split > 0 ? name.slice(0, split) : name;
        var ext = split > 0 ? name.slice(split) : '';
        attempt(stem + '-' + round + ext, content, round + 1);
        return;
      }
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  function open(onOpen) {
    if (!hosts.modal) {
      cacheHosts();
    }
    if (!hosts.modal) {
      return;
    }
    // A one-off callback may override the default, which is stored by init():
    // every caller in the application asks for the dialog with no arguments, so
    // a callback that only exists when one is passed would mean nothing was ever
    // opened after an import.
    if (typeof onOpen === 'function') {
      state.onOpen = onOpen;
    }
    state.open = true;
    lastFocus = document.activeElement;
    hosts.modal.hidden = false;
    document.addEventListener('keydown', onKeydown);
    setTab('library');
    if (hosts.close) {
      hosts.close.focus();
    }
  }

  /* Focus is returned to whatever held it, because the dialog is opened from a
     button and a keyboard user who closes it should be back where they were.
     There is no focus trap: Tab can leave the panel and reach the shell behind
     it, which is a real gap for the aria-modal promise in the markup. A trap
     would have to re-implement the browser's own sequential focus order over
     the rule that a hidden pane is skipped, and getting that wrong is worse
     than the gap - so the gap is recorded here rather than papered over. */
  function close() {
    if (!hosts.modal) {
      return;
    }
    state.open = false;
    hosts.modal.hidden = true;
    document.removeEventListener('keydown', onKeydown);
    if (lastFocus && typeof lastFocus.focus === 'function') {
      lastFocus.focus();
    }
  }

  function bind() {
    if (!hosts.modal || hosts.modal.getAttribute('data-bound')) {
      return;
    }
    hosts.modal.setAttribute('data-bound', '1');
    hosts.tabLibrary.addEventListener('click', function () { setTab('library'); });
    hosts.tabLocal.addEventListener('click', function () { setTab('local'); });
    hosts.close.addEventListener('click', close);
    hosts.browse.addEventListener('click', function () { hosts.file.click(); });
    hosts.file.addEventListener('change', function () {
      if (hosts.file.files && hosts.file.files.length) {
        importFile(hosts.file.files[0]);
      }
      // Cleared so that choosing the same file twice still fires a change.
      hosts.file.value = '';
    });
    // The veil carries the marker rather than the container, so a press on the
    // panel is not a press on the backdrop: only the backdrop closes.
    Array.prototype.forEach.call(
      hosts.modal.querySelectorAll('[data-picker-close]'),
      function (node) { node.addEventListener('click', close); }
    );
  }

  function init(options) {
    cacheHosts();
    // The default callback is the reason this dialog can open anything at all:
    // homepane and the menu both call open() with no arguments.
    state.onOpen = (options || {}).onOpen || null;
    bind();
  }

  global.FilePicker = {
    init: init,
    open: open,
    close: close,
    isOpen: function () { return state.open; }
  };
})(window);
