/* MarkNest for TOS - the editor pane.

   Holds the loaded note's revision, which is what makes saving safe. The
   revision is the content hash the server handed out when the note was opened;
   sending it back with the save lets the server notice that somebody else wrote
   the file in the meantime - over SMB, from the File Manager, in another tab -
   and refuse to overwrite their work instead of silently discarding it. */

(function (global) {
  'use strict';

  var state = {
    editor: null,
    path: '',
    rev: '',
    eol: 'lf',
    dirty: false,
    saving: false,
    writable: false,
    onDirty: null,
    onSaved: null,
    onLoaded: null
  };

  var hosts = {};

  function cacheHosts() {
    hosts.host = document.getElementById('editor-host');
    hosts.footer = document.getElementById('editor-footer');
    hosts.title = document.getElementById('editor-title');
  }

  function setFooter(text, kind) {
    if (!hosts.footer) {
      return;
    }
    hosts.footer.textContent = text || '';
    hosts.footer.className = 'pane-foot' + (kind ? ' is-' + kind : '');
  }

  function clearBanner() {
    var existing = document.getElementById('editor-banner');
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  function banner(message, actions) {
    clearBanner();
    if (!hosts.host || !hosts.host.parentNode) {
      return;
    }
    var row = UI.el('div', { class: 'error-box', id: 'editor-banner' }, [
      UI.el('div', { class: 'error-box-body' }, [UI.el('span', { text: message })])
    ]);
    (actions || []).forEach(function (action) {
      row.appendChild(UI.el('button', {
        type: 'button',
        class: 'btn btn-sm',
        text: action.label,
        onclick: action.onClick
      }));
    });
    hosts.host.parentNode.insertBefore(row, hosts.host);
  }

  function markDirty(flag) {
    if (state.dirty === flag) {
      return;
    }
    state.dirty = flag;
    if (typeof state.onDirty === 'function') {
      state.onDirty(flag);
    }
    setFooter(flag ? I18N.t('editor.dirty') : I18N.t('editor.saved'));
  }

  function build() {
    if (state.editor || !hosts.host || !global.MDEditor) {
      return;
    }
    state.editor = global.MDEditor.create(hosts.host, {
      value: '',
      onChange: function () {
        markDirty(true);
        if (global.PreviewPane) {
          global.PreviewPane.schedule(state.editor.getValue());
        }
      },
      onSave: function () {
        save();
      }
    });
  }

  /* ------------------------------------------------------------------ open */

  function open(path) {
    build();
    clearBanner();
    if (!path) {
      state.path = '';
      state.rev = '';
      if (state.editor) {
        state.editor.setValue('');
        state.editor.setReadOnly(true);
      }
      markDirty(false);
      setFooter('');
      return Promise.resolve();
    }
    return API.getNote(path).then(function (note) {
      state.path = note.path;
      state.rev = note.rev;
      state.eol = note.eol || 'lf';
      state.writable = note.writable !== false;
      if (state.editor) {
        state.editor.setValue(note.content);
        state.editor.setReadOnly(!state.writable);
      }
      markDirty(false);
      if (!state.writable) {
        setFooter(I18N.t('editor.readOnly'), 'is-warn');
      }
      if (global.PreviewPane) {
        global.PreviewPane.render(note.content);
      }
      if (typeof state.onLoaded === 'function') {
        state.onLoaded(note);
      }
    }).catch(function (error) {
      UI.toast(I18N.errorText(error), 'bad');
      if (state.editor) {
        state.editor.setValue('');
        state.editor.setReadOnly(true);
      }
      setFooter(I18N.errorText(error), 'is-bad');
    });
  }

  /* ------------------------------------------------------------------ save */

  function applyServerNote(note) {
    state.path = note.path;
    state.rev = note.rev;
    state.eol = note.eol || state.eol;
    markDirty(false);
    setFooter(I18N.t('editor.saved'));
  }

  function save(force) {
    if (!state.editor || !state.path || state.saving) {
      return Promise.resolve();
    }
    if (!state.writable) {
      UI.toast(I18N.t('editor.readOnly'), 'warn');
      return Promise.resolve();
    }
    state.saving = true;
    setFooter(I18N.t('editor.saving'));
    return API.saveNote({
      path: state.path,
      content: state.editor.getValue(),
      base_rev: state.rev,
      eol: state.eol,
      force: !!force
    }).then(function (note) {
      state.saving = false;
      clearBanner();
      applyServerNote(note);
      if (typeof state.onSaved === 'function') {
        state.onSaved(note);
      }
    }).catch(function (error) {
      state.saving = false;
      if (error && error.code === 3007) {
        // Somebody else wrote the file. Offer the three answers that are
        // actually available, rather than picking one on the person's behalf.
        setFooter(I18N.t('editor.conflict'), 'is-warn');
        banner(I18N.t('editor.conflict'), [
          {
            label: I18N.t('editor.overwrite'),
            onClick: function () {
              clearBanner();
              save(true);
            }
          },
          {
            label: I18N.t('editor.reload'),
            onClick: function () {
              clearBanner();
              open(state.path);
            }
          },
          {
            label: I18N.t('editor.saveCopy'),
            onClick: function () {
              clearBanner();
              var copy = state.path.replace(/(\.[^./]+)$/, '-副本$1');
              API.createNote({ path: copy, content: state.editor.getValue() })
                .then(function () {
                  UI.toast(I18N.t('tree.created', { name: copy }), 'ok');
                })
                .catch(function (inner) {
                  UI.toast(I18N.errorText(inner), 'bad');
                });
            }
          }
        ]);
        return;
      }
      setFooter(I18N.errorText(error), 'is-bad');
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  function init(options) {
    cacheHosts();
    var opts = options || {};
    state.onDirty = opts.onDirty;
    state.onSaved = opts.onSaved;
    state.onLoaded = opts.onLoaded;
    build();
  }

  global.EditorPane = {
    init: init,
    open: open,
    save: save,
    isDirty: function () { return state.dirty; },
    currentPath: function () { return state.path; },
    path: function () { return state.path; },
    setFooter: setFooter,
    // The preview needs the editor's scroll position to synchronise against,
    // so the controller is reachable rather than duplicated.
    editor: function () { return state.editor; }
  };
})(window);
