/* MarkNest for TOS - hash routing.

   The application runs inside a host iframe, so the URL is the hash and
   nothing else: the path is owned by the platform. Four routes exist and the
   fifth is a redirect:

     #/library                 document list / file management
     #/read?p=<path>           reading view
     #/edit?p=<path>           editing view
     #/import                  upload and import
     #/settings                personal centre and settings

   A page registers `mount(host, params)` and may register `unmount()`. The
   router guarantees that unmount runs before the next mount, so an editor can
   tear down its CodeMirror instance and release object URLs on the way out.

   Leaving the editor with unsaved work is guarded by `setGuard`. The guard runs
   before a route mounts; resolving false restores the previous hash without
   remounting it. This is the only place a navigation can be cancelled, and it
   is deliberately route-agnostic. */

(function (global) {
  'use strict';

  var routes = {};
  var host = null;
  var listeners = [];
  var current = null;
  var guard = null;
  var restoring = false;

  function safeDecode(text) {
    try {
      return decodeURIComponent(text.replace(/\+/g, ' '));
    } catch (error) {
      return text;
    }
  }

  function parse(hash) {
    var raw = String(hash || '').replace(/^#\/?/, '');
    var queryIndex = raw.indexOf('?');
    var name = queryIndex === -1 ? raw : raw.slice(0, queryIndex);
    var query = queryIndex === -1 ? '' : raw.slice(queryIndex + 1);
    var params = {};
    query.split('&').forEach(function (pair) {
      if (!pair) {
        return;
      }
      var eq = pair.indexOf('=');
      var key = eq === -1 ? pair : pair.slice(0, eq);
      var value = eq === -1 ? '' : pair.slice(eq + 1);
      params[safeDecode(key)] = safeDecode(value);
    });
    if (!name || !routes[name]) {
      return { name: 'library', params: {} };
    }
    return { name: name, params: params };
  }

  function serialise(name, params) {
    var pairs = [];
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === undefined || value === null || value === '') {
        return;
      }
      pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
    });
    return '#/' + name + (pairs.length ? '?' + pairs.join('&') : '');
  }

  function href(name, params) {
    return serialise(name, params);
  }

  function notify() {
    listeners.forEach(function (listener) {
      try {
        listener(current);
      } catch (error) {
        if (global.console) {
          global.console.error(error);
        }
      }
    });
  }

  function mount(route) {
    var page = routes[route.name];
    if (current && current.page && typeof current.page.unmount === 'function') {
      try {
        current.page.unmount();
      } catch (error) {
        if (global.console) {
          global.console.error(error);
        }
      }
    }
    if (host) {
      while (host.firstChild) {
        host.removeChild(host.firstChild);
      }
      host.scrollTop = 0;
    }
    current = { name: route.name, params: route.params, page: page };
    try {
      if (typeof page.setDocumentTitle === 'function') {
        page.setDocumentTitle(route.params);
      }
    } catch (error) {
      /* a title is never worth failing a mount over */
    }
    notify();
    if (page && typeof page.mount === 'function') {
      page.mount(host, route.params);
    }
  }

  function restore() {
    if (!current) {
      return;
    }
    restoring = true;
    global.location.replace(serialise(current.name, current.params));
  }

  function handleHash() {
    var route = parse(global.location.hash);
    if (restoring) {
      restoring = false;
      return;
    }
    if (typeof guard === 'function') {
      var decision = guard(route);
      if (decision && typeof decision.then === 'function') {
        decision.then(function (allowed) {
          if (allowed === false) {
            restore();
          } else {
            mount(route);
          }
        }, function () {
          mount(route);
        });
        return;
      }
      if (decision === false) {
        restore();
        return;
      }
    }
    mount(route);
  }

  function navigate(name, params) {
    var target = serialise(name, params);
    if (global.location.hash === target) {
      handleHash();
      return Promise.resolve(true);
    }
    global.location.hash = target;
    return Promise.resolve(true);
  }

  function start(map, hostNode) {
    routes = map || {};
    host = hostNode;
    global.addEventListener('hashchange', handleHash);
    if (!global.location.hash) {
      try {
        global.location.replace(serialise('library', {}));
      } catch (error) {
        /* about:blank and data: contexts refuse replace; the hash below still works */
      }
    }
    handleHash();
  }

  global.Router = {
    start: start,
    parse: parse,
    href: href,
    navigate: navigate,
    refresh: handleHash,
    current: function () { return current; },
    setGuard: function (fn) { guard = fn; },
    clearGuard: function () { guard = null; },
    onChange: function (fn) {
      listeners.push(fn);
      return function () {
        var index = listeners.indexOf(fn);
        if (index >= 0) {
          listeners.splice(index, 1);
        }
      };
    }
  };
})(window);
