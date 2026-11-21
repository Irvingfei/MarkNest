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

  function boot() {
    if (started) {
      return;
    }
    started = true;

    if (Store.settings.get('language')) {
      I18N.setLanguage(Store.settings.get('language'));
    } else {
      Store.settings.set('language', I18N.getLanguage());
    }

    Shell.init();

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
