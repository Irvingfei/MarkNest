/* MarkNest for TOS - application entry point.

   Boot order matters in one respect: the shell paints before the first
   request. The sidebar and the topbar are useful even while /library is still
   loading, and a failed library read is then reported in the view that needs
   it rather than as a blank frame.

   Pages are plain objects registered with the router. A page owns the DOM
   inside #view and nothing outside it. */

(function (global) {
  'use strict';

  var started = false;

  /* A language the operator picked wins; otherwise the interface follows the
     TOS desktop, including a change made while this page is open. */
  function explicitLanguage() {
    var saved = Store.settings.get('language');
    if (saved && I18N.tables[saved]) {
      return saved;
    }
    return I18N.storedLanguage();
  }

  function applyLanguagePreference() {
    var saved = explicitLanguage();
    if (saved) {
      I18N.setLanguage(saved, false);
    } else {
      I18N.follow();
    }
  }

  function followTosLanguage() {
    function resync() {
      if (explicitLanguage()) {
        return;
      }
      if (I18N.systemLanguage() === I18N.getLanguage()) {
        return;
      }
      Shell.applyLanguage('');
      var route = global.Router.current();
      if (route && route.name !== 'read' && route.name !== 'edit') {
        global.Router.refresh();
      }
    }

    try {
      global.addEventListener('storage', function (event) {
        if (event && event.key && event.key.indexOf('marknest.') !== 0 &&
            /lang|locale/i.test(event.key)) {
          resync();
        }
      });
    } catch (error) {
      /* no storage events available */
    }

    try {
      var parentDoc = global.parent && global.parent !== global ? global.parent.document : null;
      if (parentDoc && global.MutationObserver) {
        new global.MutationObserver(resync).observe(parentDoc.documentElement, {
          attributes: true,
          attributeFilter: ['lang', 'xml:lang']
        });
      }
    } catch (error) {
      /* not embedded, or the parent is another origin */
    }

    global.addEventListener('focus', resync);
  }

  function boot() {
    if (started) {
      return;
    }
    started = true;

    applyLanguagePreference();

    Shell.init();
    followTosLanguage();

    var routes = {
      library: Pages.library,
      read: Pages.reader,
      edit: Pages.editor,
      import: Pages.importer,
      settings: Pages.settings
    };

    Store.loadCore().then(function () {
      var version = Store.state.health && Store.state.health.version;
      var badge = global.document.getElementById('app-version');
      if (badge && version) {
        badge.textContent = 'v' + version;
      }
      Shell.sync();
      return Store.loadLibraryAndStats().then(function () {
        Shell.sync();
      }, function () {
        // The library page owns the error surface; the shell still works.
        Shell.sync();
      });
    }).catch(function (error) {
      Shell.sync();
      UI.toast((error && error.message) || I18N.t('err.network'), 'bad');
    }).then(function () {
      if (!global.location.hash) {
        var preferred = Store.settings.get('defaultPage') || 'library';
        if (!routes[preferred]) {
          preferred = 'library';
        }
        try {
          global.location.replace(Router.href(preferred, {}));
        } catch (error) {
          global.location.hash = Router.href(preferred, {});
        }
      }
      Router.start(routes, global.document.getElementById('view'));
    });

    global.addEventListener('unhandledrejection', function (event) {
      var reason = event.reason;
      if (reason && reason.name === 'ApiError') {
        return;
      }
      if (global.console) {
        global.console.error(reason);
      }
    });
  }

  function health() {
    return Store.state.health;
  }

  function openNote(path) {
    if (!path) {
      Router.navigate('library');
      return;
    }
    Router.navigate('read', { p: path });
  }

  global.App = {
    boot: boot,
    health: health,
    openNote: openNote
  };

  if (global.document.readyState === 'loading') {
    global.document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);
