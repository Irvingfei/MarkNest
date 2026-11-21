/* MarkNest for TOS - client state.

   Two things live here and nothing else: the operator's appearance/behaviour
   settings, kept in localStorage so they survive a reload, and the handful of
   server documents every page reads (health, identity, options, the library
   listing, counts). Pages ask for what they need; they do not each invent a
   fetch and a cache.

   Attachment object URLs are cached here too, keyed by library path, so that
   the reader and the editor's preview do not each download the same image. The
   HTTP cache is not available to them - the bytes are fetched with platform
   headers - so the cache is the object URL itself, and it is revoked when the
   app unloads. */

(function (global) {
  'use strict';

  var KEY = 'marknest.settings';

  var DEFAULTS = {
    theme: 'system',
    accent: 'forest',
    fontSize: 'md',
    readingWidth: 'md',
    language: '',
    defaultPage: 'library',
    autosave: true,
    view: 'grid',
    sort: 'updated',
    lastFolder: ''
  };

  var settings = read();

  function read() {
    var stored = {};
    try {
      stored = JSON.parse(global.localStorage.getItem(KEY) || '{}') || {};
    } catch (error) {
      stored = {};
    }
    var merged = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      merged[key] = stored[key] === undefined ? DEFAULTS[key] : stored[key];
    });
    return merged;
  }

  function save() {
    try {
      global.localStorage.setItem(KEY, JSON.stringify(settings));
    } catch (error) {
      /* a full or blocked localStorage must not break the page */
    }
  }

  function get(key) {
    return settings[key];
  }

  function set(key, value) {
    settings[key] = value;
    save();
    if (key === 'theme' || key === 'accent' || key === 'fontSize' || key === 'readingWidth') {
      applyAppearance();
    }
  }

  function patch(values) {
    Object.keys(values || {}).forEach(function (key) {
      settings[key] = values[key];
    });
    save();
    applyAppearance();
  }

  function resetSettings() {
    settings = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      settings[key] = DEFAULTS[key];
    });
    save();
    applyAppearance();
  }

  /* theme-boot.js already applied these before the first paint; this keeps the
     attributes in step when settings change without a reload. */
  function applyAppearance() {
    var root = global.document.documentElement;
    var theme = settings.theme;
    if (theme === 'system') {
      var dark = !!(global.matchMedia && global.matchMedia('(prefers-color-scheme: dark)').matches);
      theme = dark ? 'dark' : 'light';
    }
    root.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
    root.setAttribute('data-accent', settings.accent || 'forest');
    root.setAttribute('data-font', settings.fontSize || 'md');
    root.setAttribute('data-width', settings.readingWidth || 'md');
  }

  /* ------------------------------------------------------------- server data */

  var state = {
    health: null,
    me: null,
    options: null,
    library: null,
    stats: null,
    folders: null,
    loaded: false,
    libraryError: null
  };

  function loadCore() {
    return Promise.all([API.getHealth(), API.getMe(), API.getOptions()]).then(function (values) {
      state.health = values[0];
      state.me = values[1];
      state.options = values[2];
      return state;
    });
  }

  function loadLibrary() {
    return API.getLibrary().then(function (view) {
      state.library = view;
      state.folders = view.folders || [];
      state.libraryError = null;
      state.loaded = true;
      return view;
    });
  }

  function loadStats() {
    return API.getStats().then(function (stats) {
      state.stats = stats;
      return stats;
    });
  }

  /* The library page needs both; the shell only needs the counts. Failures are
     surfaced by the caller rather than swallowed, but the counts are optional -
     a failed /stats must not blank a library that loaded fine. */
  function loadLibraryAndStats() {
    return loadLibrary().then(function (view) {
      return loadStats().catch(function () {
        return null;
      }).then(function () {
        return view;
      });
    });
  }

  function noteByPath(path) {
    if (!state.library) {
      return null;
    }
    var notes = state.library.notes || [];
    for (var i = 0; i < notes.length; i += 1) {
      if (notes[i].path === path) {
        return notes[i];
      }
    }
    return null;
  }

  function folderCount(path) {
    if (!state.folders) {
      return 0;
    }
    for (var i = 0; i < state.folders.length; i += 1) {
      if (state.folders[i].path === path) {
        return state.folders[i].count || 0;
      }
    }
    return 0;
  }

  /* ------------------------------------------------------------ asset cache */

  var assets = {};

  function assetUrl(path, force) {
    if (!path) {
      return Promise.resolve('');
    }
    if (!force && assets[path]) {
      return Promise.resolve(assets[path]);
    }
    return API.attachmentBlob(path).then(function (blob) {
      if (assets[path]) {
        global.URL.revokeObjectURL(assets[path]);
      }
      assets[path] = global.URL.createObjectURL(blob);
      return assets[path];
    });
  }

  function releaseAssets() {
    Object.keys(assets).forEach(function (path) {
      try {
        global.URL.revokeObjectURL(assets[path]);
      } catch (error) {
        /* already revoked */
      }
      delete assets[path];
    });
  }

  global.Store = {
    settings: {
      get: get,
      set: set,
      patch: patch,
      reset: resetSettings,
      all: function () { return settings; }
    },
    applyAppearance: applyAppearance,
    state: state,
    loadCore: loadCore,
    loadLibrary: loadLibrary,
    loadStats: loadStats,
    loadLibraryAndStats: loadLibraryAndStats,
    noteByPath: noteByPath,
    folderCount: folderCount,
    assetUrl: assetUrl,
    releaseAssets: releaseAssets
  };
})(window);
