/* MarkNest for TOS - bootstrap and shell wiring.

   Two conventions carried over from the platform work that preceded this app,
   both of which cost real debugging to learn:

   Every boot stage is wrapped so that one failing subsystem cannot leave the
   user looking at a blank frame. A missing element or a rejected promise used
   to abort the rest of startup, and "white screen with no explanation" is the
   least actionable failure an embedded application can produce.

   The open note is kept in the URL fragment. There is no address bar inside the
   iframe and the platform may reload the frame at any moment, so the fragment is
   the only place that survives - without it, a reload silently returns the user
   to an empty editor. */

(function (global) {
  'use strict';

  var HEALTH_INTERVAL = 20000;
  var healthTimer = null;
  var options = {};

  function step(label, fn) {
    try {
      return fn();
    } catch (error) {
      if (global.console && global.console.error) {
        global.console.error('[marknest] boot step failed: %s', label, error);
      }
      return null;
    }
  }

  function setStatus(text, kind) {
    var node = document.getElementById('status-text');
    if (!node) {
      return;
    }
    node.textContent = text || '';
    node.className = 'status' + (kind ? ' is-' + kind : '');
  }

  function setIndexStatus(text) {
    var node = document.getElementById('index-status');
    if (node) {
      node.textContent = text || '';
    }
  }

  function setDirty(flag) {
    var dot = document.getElementById('dirty-dot');
    var save = document.getElementById('btn-save');
    if (dot) {
      dot.hidden = !flag;
    }
    if (save) {
      save.disabled = !flag;
    }
  }

  function setTitle(path) {
    var node = document.getElementById('current-path');
    if (node) {
      node.textContent = path || I18N.t('editor.noNote');
    }
  }

  /* ----------------------------------------------------------------- health */

  function health() {
    return API.getHealth().then(function (payload) {
      var ready = payload && payload.library_ready;
      setStatus(ready ? I18N.t('status.libraryOk') : I18N.t('status.libraryDown'),
        ready ? '' : 'is-bad');
      var index = (payload && payload.index) || {};
      setIndexStatus(I18N.t('status.indexed', { n: index.notes || 0 }));
      return payload;
    }).catch(function (error) {
      setStatus(I18N.errorText(error), 'is-bad');
      setIndexStatus('');
      return null;
    });
  }

  function startHealthPolling() {
    health();
    if (healthTimer) {
      global.clearInterval(healthTimer);
    }
    healthTimer = global.setInterval(health, HEALTH_INTERVAL);
  }

  /* ----------------------------------------------------------------- layout */

  function applyWidth() {
    var workspace = document.getElementById('workspace');
    if (!workspace) {
      return;
    }
    var width = workspace.clientWidth;
    // Collapse progressively rather than squeezing three panes into a frame
    // that cannot hold them. Below 900px the preview goes; below 640px the
    // tree goes with it.
    workspace.classList.toggle('is-no-preview', width < 900 || !options.preview);
    workspace.classList.toggle('is-no-tree', width < 640);
  }

  function togglePreview() {
    options.preview = !options.preview;
    var button = document.getElementById('btn-preview-toggle');
    if (button) {
      button.setAttribute('aria-pressed', options.preview ? 'true' : 'false');
      button.classList.toggle('is-active', options.preview);
    }
    applyWidth();
  }

  /* ------------------------------------------------------------------ route */

  var view = { name: null };

  /* Two states, derived from whether a note is open rather than stored
     separately - a stored flag and an open note can disagree, and then the
     screen shows one thing and the hash says another. */
  function setView(name) {
    if (view.name === name) {
      return;
    }
    view.name = name;
    var home = document.getElementById('home');
    var workspace = document.getElementById('workspace');
    if (home) {
      home.hidden = name !== 'home';
    }
    if (workspace) {
      workspace.classList.toggle('is-home', name === 'home');
    }
    if (global.FormatBar) {
      global.FormatBar.setEnabled(name === 'note');
    }
    // Hiding the workspace takes it out of layout, so applyWidth() reads a
    // width of 0 while the home screen is up and records that as "collapse
    // every pane". The width is therefore re-read on every view change and not
    // only on resize - otherwise the workspace comes back with its tree and
    // preview still collapsed after any visit to the home screen.
    applyWidth();
  }

  function pageFromHash() {
    var raw = (global.location.hash || '').replace(/^#\/?/, '');
    var queryStart = raw.indexOf('?');
    var params = {};
    if (queryStart !== -1) {
      raw.slice(queryStart + 1).split('&').forEach(function (pair) {
        if (!pair) {
          return;
        }
        var split = pair.indexOf('=');
        var key = split === -1 ? pair : pair.slice(0, split);
        var value = split === -1 ? '' : pair.slice(split + 1);
        try {
          params[decodeURIComponent(key)] = decodeURIComponent(value);
        } catch (error) {
          params[key] = value;
        }
      });
      raw = raw.slice(0, queryStart);
    }
    return { page: raw || 'home', params: params };
  }

  function writeHash(path) {
    var next = path ? '#/notes?p=' + encodeURIComponent(path) : '#/home';
    if (global.location.hash !== next) {
      global.location.hash = next;
    }
  }

  function showHome(push) {
    setView('home');
    if (global.TreePane) {
      global.TreePane.setCurrent('');
    }
    setTitle('');
    if (push) {
      writeHash('');
    }
    if (global.HomePane) {
      global.HomePane.reload();
    }
  }

  function openNote(path, push) {
    if (!path) {
      showHome(push);
      return Promise.resolve();
    }
    setTitle(path);
    setView('note');
    if (global.TreePane) {
      global.TreePane.setCurrent(path);
    }
    if (push) {
      writeHash(path);
    }
    return global.EditorPane.open(path);
  }

  /* ------------------------------------------------------------------- boot */

  function bindShell() {
    var newButton = document.getElementById('btn-new-note');
    if (newButton) {
      newButton.addEventListener('click', function () {
        global.TreePane.newNote();
      });
    }

    var saveButton = document.getElementById('btn-save');
    if (saveButton) {
      saveButton.addEventListener('click', function () {
        global.EditorPane.save();
      });
    }

    var previewButton = document.getElementById('btn-preview-toggle');
    if (previewButton) {
      previewButton.addEventListener('click', togglePreview);
    }

    var refresh = document.getElementById('btn-refresh-tree');
    if (refresh) {
      refresh.addEventListener('click', function () {
        global.TreePane.reload();
      });
    }

    var langSelect = document.getElementById('lang-select');
    if (langSelect) {
      I18N.supported.forEach(function (tag) {
        var option = document.createElement('option');
        option.value = tag;
        option.textContent = tag;
        langSelect.appendChild(option);
      });
      langSelect.value = I18N.getLanguage();
      langSelect.addEventListener('change', function () {
        I18N.setLanguage(langSelect.value);
        // The panes render text themselves, so their current content has to be
        // produced again for the new language to appear in it.
        I18N.apply(document);
        if (global.TreePane) {
          global.TreePane.render();
        }
        if (global.EditorPane && global.EditorPane.editor()) {
          global.PreviewPane.render(global.EditorPane.editor().getValue());
        }
        health();
      });
    }

    applyWidth();
    global.addEventListener('resize', applyWidth);

    // A note with unsaved changes is the one thing a reload would silently
    // destroy, so the browser is asked to confirm.
    global.addEventListener('beforeunload', function (event) {
      if (global.EditorPane && global.EditorPane.isDirty()) {
        event.preventDefault();
        event.returnValue = '';
        return '';
      }
      return undefined;
    });

    global.addEventListener('hashchange', function () {
      var route = pageFromHash();
      // Both pages are routed, and the home branch checks the current view
      // first: boot normalises an empty fragment to #/home, and without that
      // guard the assignment would come straight back through here and reload
      // the home pane a second time.
      if (route.page === 'home') {
        if (view.name !== 'home') {
          showHome(false);
        }
        return;
      }
      if (route.params.p !== global.TreePane.current()) {
        openNote(route.params.p || '', false);
      }
    });
  }

  function boot() {
    options.preview = true;

    step('language', function () {
      I18N.setLanguage(I18N.getLanguage());
    });

    step('shell', bindShell);

    step('tree', function () {
      global.TreePane.init({
        onOpen: function (path) {
          openNote(path, true);
        }
      });
    });

    step('editor', function () {
      global.EditorPane.init({
        onDirty: setDirty,
        onSaved: function () {
          global.TreePane.refresh();
        }
      });
    });

    step('formatbar', function () {
      global.FormatBar.init();
    });

    step('home', function () {
      // HomePane does not exist yet; the guard is the same pattern the
      // neighbouring steps use, and it keeps this step from being the one that
      // aborts the rest of startup.
      if (global.HomePane) {
        global.HomePane.init({ onOpen: openNote });
      }
    });

    step('preview', function () {
      global.PreviewPane.init();
      var button = document.getElementById('btn-preview-toggle');
      if (button) {
        button.classList.add('is-active');
      }
    });

    step('search', function () {
      global.SearchPane.init({
        onOpen: function (path) {
          openNote(path, true);
        },
        onExit: function () {
          global.TreePane.render();
        }
      });
    });

    step('health', startHealthPolling);

    step('tree-load', function () {
      global.TreePane.reload().then(function () {
        var route = pageFromHash();
        if (route.params.p) {
          openNote(route.params.p, false);
        } else {
          // The spec's fragment is the only thing that survives a reload of
          // the iframe, so it has to name the view that is actually on screen
          // - an empty hash and a home screen disagree about where the user is.
          showHome(false);
          writeHash('');
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  global.App = {
    boot: boot,
    health: health,
    openNote: openNote,
    options: function () { return options; }
  };
})(window);
