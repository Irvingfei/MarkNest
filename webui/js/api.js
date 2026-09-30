/* MarkNest for TOS - API access layer.

   Every request goes through /v2/proxy/marknest/ and carries the platform
   credentials described in the TOS 7 specification:

     X-Csrf-Token: <token read from document.cookie>
     Cookie:       TMSESSNAME=<session>; X-Csrf-Token=<token>;

   The custom "Cookie" header exists because browsers forbid JavaScript from
   writing the standard Cookie header; the name is fixed by the platform.

   Two endpoints answer without a resolved user - /health and /options - because
   they describe the installation rather than anybody's notes. Everything else
   needs the TOS user, which the backend reads from a cookie it treats as
   untrusted input. */

(function (global) {
  'use strict';

  var BASE = '/v2/proxy/marknest';
  var SESSION_COOKIE = 'TMSESSNAME';
  var CSRF_COOKIE = 'X-Csrf-Token';

  /* The TOS user is sent as an explicit header rather than left to the platform
     cookie. Measured on TOS 7: the browser holds `tos_current_username`, the
     session and CSRF cookies reach the application (authentication would fail
     otherwise), and this one does not - a request through the platform proxy
     arrives without it while the identical request against the application's
     own socket carries it fine. The backend still reads the cookie as a
     fallback, because it is the platform's convention and costs nothing. */
  var USER_COOKIE = 'tos_current_username';
  var USER_HEADER = 'X-MarkNest-User';

  function getCookie(name) {
    var prefix = encodeURIComponent(name) + '=';
    var parts = (document.cookie || '').split(';');
    for (var i = 0; i < parts.length; i += 1) {
      var item = parts[i].trim();
      if (item.indexOf(prefix) === 0) {
        try {
          return decodeURIComponent(item.slice(prefix.length));
        } catch (error) {
          return item.slice(prefix.length);
        }
      }
    }
    return '';
  }

  function fromGlobals(names) {
    var hosts = [global.TM, global.TOS, global.tos];
    for (var i = 0; i < hosts.length; i += 1) {
      var host = hosts[i];
      if (!host) {
        continue;
      }
      for (var j = 0; j < names.length; j += 1) {
        var direct = host[names[j]];
        if (typeof direct === 'string' && direct) {
          return direct;
        }
        var user = host.user;
        if (user && typeof user[names[j]] === 'string' && user[names[j]]) {
          return user[names[j]];
        }
      }
    }
    return '';
  }

  function csrfToken() {
    return getCookie(CSRF_COOKIE) || fromGlobals(['csrfToken', 'csrf_token', 'token']);
  }

  function sessionToken() {
    return getCookie(SESSION_COOKIE) || fromGlobals(['session', 'sessionId', 'sid']);
  }

  function authHeaders(extra) {
    var headers = {};
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        headers[key] = extra[key];
      });
    }
    var user = getCookie(USER_COOKIE);
    if (user) {
      headers[USER_HEADER] = user;
    }
    var token = csrfToken();
    if (token) {
      headers['X-Csrf-Token'] = token;
      var session = sessionToken();
      var jar = [];
      if (session) {
        jar.push(SESSION_COOKIE + '=' + session);
      }
      jar.push(CSRF_COOKIE + '=' + token);
      headers.Cookie = jar.join('; ') + ';';
    }
    return headers;
  }

  function withTimeout(seconds) {
    if (typeof global.AbortController === 'undefined') {
      return { signal: undefined, cancel: function () {} };
    }
    var controller = new global.AbortController();
    var timer = global.setTimeout(function () {
      controller.abort();
    }, seconds * 1000);
    return {
      signal: controller.signal,
      cancel: function () {
        global.clearTimeout(timer);
      }
    };
  }

  function ApiError(message, options) {
    var opts = options || {};
    var error = Error.call(this, message);
    this.name = 'ApiError';
    this.message = message || 'request failed';
    this.status = opts.status || 0;
    this.code = opts.code || 0;
    this.kind = opts.kind || 'api';
    this.retryable = opts.retryable !== false;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ApiError);
    } else {
      this.stack = error.stack;
    }
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  function redirectToLogin() {
    global.setTimeout(function () {
      global.location.href = '/';
    }, 1200);
  }

  function handleStatus(status, payload) {
    if (status === 401) {
      // The platform owns the session, so there is nothing to refresh here.
      try {
        UI.toast(I18N.t('err.session'), 'warn');
      } catch (error) {
        /* the shell may not be up yet */
      }
      redirectToLogin();
      throw new ApiError(I18N.t('err.session'), {
        status: status, code: 1401, kind: 'auth', retryable: false
      });
    }
    if (payload && typeof payload.code === 'number' && payload.code !== 0) {
      throw new ApiError(I18N.errorText({ code: payload.code, message: payload.message }), {
        status: status, code: payload.code
      });
    }
    if (status >= 400) {
      throw new ApiError(I18N.t('err.http', { status: status }), { status: status });
    }
    return payload;
  }

  function request(path, options) {
    var opts = options || {};
    var guard = withTimeout(opts.timeout || 30);
    return fetch(BASE + path, {
      method: opts.method || 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: authHeaders(opts.headers),
      body: opts.body,
      signal: guard.signal
    }).then(function (response) {
      guard.cancel();
      return response.text().then(function (text) {
        var payload = null;
        try {
          payload = text ? JSON.parse(text) : null;
        } catch (error) {
          payload = null;
        }
        var checked = handleStatus(response.status, payload);
        if (checked && typeof checked === 'object' && 'data' in checked) {
          return checked.data;
        }
        return checked;
      });
    }, function (error) {
      guard.cancel();
      if (error instanceof ApiError) {
        throw error;
      }
      if (error && error.name === 'AbortError') {
        throw new ApiError(I18N.t('err.timeout'), { kind: 'timeout' });
      }
      throw new ApiError(I18N.t('err.network'), { kind: 'network' });
    });
  }

  function queryString(params) {
    var parts = [];
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === undefined || value === null || value === '') {
        return;
      }
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  function postJson(path, body) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
  }

  global.ApiError = ApiError;

  global.API = {
    base: BASE,
    getCookie: getCookie,
    csrfToken: csrfToken,
    sessionToken: sessionToken,
    authHeaders: authHeaders,

    getHealth: function () {
      return request('/health', { timeout: 12 });
    },

    getOptions: function () {
      return request('/options');
    },

    getMe: function () {
      return request('/me');
    },

    getTree: function (path) {
      return request('/tree' + queryString({ path: path }));
    },

    getNote: function (path) {
      return request('/notes' + queryString({ path: path }));
    },

    saveNote: function (payload) {
      return postJson('/notes/save', payload);
    },

    createNote: function (payload) {
      return postJson('/notes/new', payload);
    },

    renameNote: function (payload) {
      return postJson('/notes/rename', payload);
    },

    deleteNote: function (path) {
      return request('/notes' + queryString({ path: path }), { method: 'DELETE' });
    },

    getRecent: function (limit) {
      return request('/recent' + queryString({ limit: limit }));
    },

    search: function (q, limit) {
      return request('/search' + queryString({ q: q, limit: limit }));
    },

    indexStatus: function () {
      return request('/index/status');
    },

    indexScan: function () {
      return request('/index/scan', { method: 'POST', timeout: 60 });
    }
  };
})(window);
