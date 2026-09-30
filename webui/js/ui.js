/* MarkNest for TOS - shared DOM helpers, toasts and error surfaces.
   Every asynchronous view uses errorBox()/loading()/empty() so that a failed
   request never leaves the page stuck in a loading state without a way out. */

(function (global) {
  'use strict';

  var toastHost = null;

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === undefined || value === null || value === false) {
          return;
        }
        if (key === 'text') {
          node.textContent = value;
        } else if (key === 'html') {
          node.innerHTML = value;
        } else if (key === 'class') {
          node.className = value;
        } else if (key.indexOf('on') === 0 && typeof value === 'function') {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else if (value === true) {
          node.setAttribute(key, '');
        } else {
          node.setAttribute(key, value);
        }
      });
    }
    if (children) {
      var list = Array.isArray(children) ? children : [children];
      list.forEach(function (child) {
        if (child === null || child === undefined || child === false) {
          return;
        }
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
      });
    }
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
    return node;
  }

  function show(node) {
    if (node) {
      node.hidden = false;
    }
    return node;
  }

  function hide(node) {
    if (node) {
      node.hidden = true;
    }
    return node;
  }

  function toast(message, kind, timeout) {
    if (!toastHost) {
      toastHost = document.getElementById('toast-host');
    }
    if (!toastHost) {
      return null;
    }
    var node = el('div', { class: 'toast' + (kind ? ' is-' + kind : ''), text: message });
    toastHost.appendChild(node);
    global.setTimeout(function () {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    }, timeout || 4000);
    return node;
  }

  function loading(host, message) {
    clear(host);
    host.appendChild(el('div', { class: 'loading', text: message || I18N.t('common.loading') }));
  }

  function empty(host, message) {
    clear(host);
    host.appendChild(el('div', { class: 'empty', text: message || I18N.t('common.empty') }));
  }

  /* Second line of an error surface: what the operator can actually do about
     it. Kept separate from the message so the translated failure reason is never
     diluted by instructions, and so callers can attach it only when the failure
     has a known remedy. */
  function hintNode(text) {
    return el('span', { class: 'error-hint', text: text });
  }

  /* A recoverable error surface. The retry handler is mandatory by design so
     that no failure can render a dead end. `action` is an optional second way
     out - a jump to wherever the failure is actually fixed - and is offered
     only by callers that know such a place exists. */
  function errorBox(host, message, onRetry, hint, action) {
    clear(host);
    var body = el('div', { class: 'error-box-body' }, [el('span', { text: message })]);
    if (hint) {
      body.appendChild(hintNode(hint));
    }
    if (action) {
      body.appendChild(
        el('button', {
          type: 'button',
          class: 'inline-action',
          text: action.label,
          title: action.title,
          onclick: action.onClick
        })
      );
    }
    var box = el('div', { class: 'error-box' }, [
      body,
      el('button', {
        class: 'btn btn-sm',
        text: I18N.t('common.retryAction'),
        onclick: function () {
          if (typeof onRetry === 'function') {
            onRetry();
          }
        }
      })
    ]);
    host.appendChild(box);
    return box;
  }

  function skeleton(host, count) {
    clear(host);
    for (var i = 0; i < (count || 3); i += 1) {
      host.appendChild(el('div', { class: 'skeleton' }));
    }
  }

  function badge(kind, text) {
    return el('span', { class: 'badge badge-' + kind, text: text });
  }

  function statusBadge(status) {
    var map = {
      success: ['ok', I18N.t('jobs.statusSuccess')],
      failed: ['bad', I18N.t('jobs.statusFailed')],
      printing: ['run', I18N.t('jobs.statusPrinting')],
      pending: ['idle', I18N.t('jobs.statusPending')]
    };
    var entry = map[status] || ['idle', status || I18N.t('common.unknown')];
    return badge(entry[0], entry[1]);
  }

  function formatBytes(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024) {
      return value + ' B';
    }
    if (value < 1024 * 1024) {
      return (value / 1024).toFixed(1) + ' KB';
    }
    if (value < 1024 * 1024 * 1024) {
      return (value / (1024 * 1024)).toFixed(1) + ' MB';
    }
    return (value / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function formatDateTime(value) {
    if (!value) {
      return '';
    }
    /* The backend emits "YYYY-MM-DD HH:MM:SS" in local time. */
    return String(value).replace('T', ' ').slice(0, 19);
  }

  function escapeHtml(text) {
    return String(text === undefined || text === null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      global.clearTimeout(timer);
      timer = global.setTimeout(function () {
        fn.apply(self, args);
      }, wait);
    };
  }

  global.UI = {
    el: el,
    clear: clear,
    show: show,
    hide: hide,
    toast: toast,
    loading: loading,
    empty: empty,
    errorBox: errorBox,
    hintNode: hintNode,
    skeleton: skeleton,
    badge: badge,
    statusBadge: statusBadge,
    formatBytes: formatBytes,
    formatDateTime: formatDateTime,
    escapeHtml: escapeHtml,
    debounce: debounce
  };
})(window);
