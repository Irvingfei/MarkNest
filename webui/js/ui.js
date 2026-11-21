/* MarkNest for TOS - shared DOM helpers, overlays, menus and toasts.

   Every asynchronous view uses errorBox()/loading()/empty() so that a failed
   request never leaves the page stuck in a loading state without a way out.
   Everything here is plain DOM: the application has no runtime framework and
   no build step. */

(function (global) {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var toastHost = null;
  var openModals = 0;

  /* ------------------------------------------------------------- elements */

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
        } else if (key === 'style' && typeof value === 'object') {
          Object.keys(value).forEach(function (property) {
            node.style[property] = value[property];
          });
        } else if (key === 'dataset' && typeof value === 'object') {
          Object.keys(value).forEach(function (property) {
            node.dataset[property] = value[property];
          });
        } else if (key.indexOf('on') === 0 && typeof value === 'function') {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else if (value === true) {
          node.setAttribute(key, '');
        } else {
          node.setAttribute(key, value);
        }
      });
    }
    if (children !== undefined && children !== null) {
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

  function icon(name, extra) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'icon' + (extra ? ' ' + extra : ''));
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    var use = document.createElementNS(SVG_NS, 'use');
    use.setAttribute('href', '#i-' + name);
    svg.appendChild(use);
    return svg;
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

  /* ---------------------------------------------------------------- toasts */

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
    }, timeout || 3600);
    return node;
  }

  /* ---------------------------------------------------------- async states */

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

  function emptyState(options) {
    var opts = options || {};
    var art = el('div', { class: 'empty-art' }, [icon(opts.icon || 'file-text', 'icon-lg')]);
    var children = [art, el('div', { class: 'empty-title', text: opts.title || I18N.t('common.empty') })];
    if (opts.body) {
      children.push(el('div', { class: 'empty-body', text: opts.body }));
    }
    if (opts.actions && opts.actions.length) {
      children.push(el('div', { class: 'empty-actions' }, opts.actions));
    }
    return el('div', { class: 'empty-state' }, children);
  }

  /* ---------------------------------------------------------------- badges */

  function badge(kind, text) {
    return el('span', { class: 'badge badge-' + kind, text: text });
  }

  function statusBadge(status) {
    var map = {
      success: ['ok', I18N.t('common.done')],
      failed: ['bad', I18N.t('common.failed')],
      created: ['ok', I18N.t('import.statusCreated')],
      skipped: ['warn', I18N.t('import.statusSkipped')],
      pending: ['neutral', I18N.t('import.statusPending')],
      uploading: ['accent', I18N.t('import.statusUploading')]
    };
    var entry = map[status] || ['neutral', status || I18N.t('common.unknown')];
    return badge(entry[0], entry[1]);
  }

  /* ---------------------------------------------------------------- modals */

  function overlayHost() {
    return document.getElementById('overlay-root') || document.body;
  }

  function focusables(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll('button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])')
    ).filter(function (node) {
      return !node.disabled && node.offsetParent !== null;
    });
  }

  function modal(options) {
    var opts = options || {};
    var previousFocus = document.activeElement;
    var closed = false;

    var titleNode = el('div', { class: 'modal-title', text: opts.title || '' });
    var subNode = opts.subtitle ? el('div', { class: 'modal-sub', text: opts.subtitle }) : null;
    var headText = el('div', null, [titleNode, subNode]);
    var closeBtn = el('button', {
      type: 'button',
      class: 'icon-btn modal-close',
      'aria-label': I18N.t('common.close'),
      title: I18N.t('common.close'),
      onclick: function () { close(false); }
    }, [icon('x')]);
    var head = el('div', { class: 'modal-head' }, [headText, closeBtn]);

    var body = el('div', { class: 'modal-body' });
    if (typeof opts.body === 'string') {
      body.appendChild(el('div', { text: opts.body }));
    } else if (opts.body) {
      body.appendChild(opts.body);
    }

    var foot = null;
    if (opts.actions && opts.actions.length) {
      foot = el('div', { class: 'modal-foot' });
      opts.actions.forEach(function (action) {
        if (action.spacer) {
          foot.appendChild(el('span', { class: 'spacer' }));
          return;
        }
        foot.appendChild(
          el('button', {
            type: 'button',
            class: 'btn' + (action.kind ? ' btn-' + action.kind : ''),
            text: action.label,
            disabled: !!action.disabled,
            onclick: function () {
              if (typeof action.onClick === 'function') {
                var result = action.onClick();
                if (action.close !== false) {
                  if (result && typeof result.then === 'function') {
                    result.then(function () { close(true); }, function () {});
                  } else {
                    close(true);
                  }
                }
              } else {
                close(true);
              }
            }
          })
        );
      });
    }

    var modalNode = el('div', {
      class: 'modal' + (opts.width ? ' modal-' + opts.width : '') + (opts.className ? ' ' + opts.className : ''),
      role: 'dialog',
      'aria-modal': 'true'
    }, [head, body, foot]);

    var backdrop = el('div', { class: 'modal-backdrop' }, [modalNode]);

    function onKey(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(false);
        return;
      }
      if (event.key !== 'Tab') {
        return;
      }
      var nodes = focusables(modalNode);
      if (!nodes.length) {
        return;
      }
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function close(result) {
      if (closed) {
        return;
      }
      closed = true;
      document.removeEventListener('keydown', onKey, true);
      openModals = Math.max(0, openModals - 1);
      if (!openModals) {
        document.body.classList.remove('has-modal');
      }
      if (backdrop.parentNode) {
        backdrop.parentNode.removeChild(backdrop);
      }
      if (previousFocus && previousFocus.focus) {
        previousFocus.focus();
      }
      if (typeof opts.onClose === 'function') {
        opts.onClose(result);
      }
    }

    backdrop.addEventListener('mousedown', function (event) {
      if (event.target === backdrop && opts.dismissible !== false) {
        close(false);
      }
    });
    document.addEventListener('keydown', onKey, true);

    overlayHost().appendChild(backdrop);
    openModals += 1;
    document.body.classList.add('has-modal');

    global.setTimeout(function () {
      var target = opts.autoFocus === false ? null : focusables(modalNode)[0];
      if (target) {
        target.focus();
      }
    }, 20);

    return {
      el: modalNode,
      body: body,
      close: close,
      setTitle: function (text) { titleNode.textContent = text; }
    };
  }

  function confirm(options) {
    var opts = options || {};
    return new Promise(function (resolve) {
      var settled = false;
      var dialog = modal({
        title: opts.title || I18N.t('common.confirm'),
        subtitle: opts.subtitle,
        body: opts.message ? el('p', { class: 'page-sub', text: opts.message }) : null,
        dismissible: true,
        onClose: function (result) {
          if (!settled) {
            settled = true;
            resolve(!!result);
          }
        },
        actions: [
          { label: opts.cancelLabel || I18N.t('common.cancel'), close: true },
          {
            label: opts.confirmLabel || I18N.t('common.confirm'),
            kind: opts.danger ? 'danger' : 'primary',
            onClick: function () {
              settled = true;
              resolve(true);
            }
          }
        ]
      });
      return dialog;
    });
  }

  function promptDialog(options) {
    var opts = options || {};
    return new Promise(function (resolve) {
      var settled = false;
      var input = el('input', {
        class: 'input',
        type: 'text',
        value: opts.value || '',
        placeholder: opts.placeholder || '',
        autocomplete: 'off',
        spellcheck: 'false'
      });
      var field = el('label', { class: 'field' }, [
        el('span', { class: 'field-label', text: opts.label || '' }),
        input,
        opts.hint ? el('span', { class: 'field-hint', text: opts.hint }) : null
      ]);
      function settle(value) {
        if (settled) {
          return;
        }
        settled = true;
        resolve(value);
      }
      var dialog = modal({
        title: opts.title || I18N.t('common.new'),
        body: field,
        onClose: function () { settle(null); },
        actions: [
          {
            label: I18N.t('common.cancel'),
            close: true,
            onClick: function () { settle(null); }
          },
          {
            label: opts.confirmLabel || I18N.t('common.confirm'),
            kind: 'primary',
            onClick: function () {
              var value = input.value.trim();
              settle(value || null);
            }
          }
        ]
      });
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          var value = input.value.trim();
          settle(value || null);
          dialog.close(true);
        }
      });
      global.setTimeout(function () {
        input.focus();
        input.select();
      }, 30);
    });
  }

  /* ----------------------------------------------------------------- menus */

  function menu(anchor, items, options) {
    var opts = options || {};
    var backdrop = null;
    var node = el('div', { class: 'menu', role: 'menu' });

    function close() {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
      if (backdrop && backdrop.parentNode) {
        backdrop.parentNode.removeChild(backdrop);
      }
      document.removeEventListener('mousedown', onOutside, true);
      document.removeEventListener('keydown', onKey, true);
      global.removeEventListener('resize', close);
    }

    function onOutside(event) {
      if (!node.contains(event.target) && anchor && !anchor.contains(event.target)) {
        close();
      }
    }

    function onKey(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        if (anchor && anchor.focus) {
          anchor.focus();
        }
      }
    }

    items.forEach(function (item) {
      if (item.divider) {
        node.appendChild(el('div', { class: 'menu-sep' }));
        return;
      }
      node.appendChild(
        el('button', {
          type: 'button',
          class: 'menu-item' + (item.danger ? ' is-danger' : ''),
          role: 'menuitem',
          disabled: !!item.disabled,
          onclick: function () {
            close();
            if (typeof item.onClick === 'function') {
              item.onClick();
            }
          }
        }, [item.icon ? icon(item.icon) : null, el('span', { text: item.label })])
      );
    });

    if (opts.backdrop) {
      backdrop = el('div', { class: 'scrim', style: { background: 'transparent', backdropFilter: 'none' } });
      backdrop.addEventListener('mousedown', close);
      overlayHost().appendChild(backdrop);
    }

    overlayHost().appendChild(node);

    var rect = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: 12, top: 60, bottom: 60, right: 12 };
    var width = node.offsetWidth || 200;
    var height = node.offsetHeight || 120;
    var left = opts.align === 'left' ? rect.left : rect.right - width;
    left = Math.max(8, Math.min(left, global.innerWidth - width - 8));
    var top = rect.bottom + 6;
    if (top + height > global.innerHeight - 12) {
      top = Math.max(8, rect.top - height - 6);
    }
    node.style.left = left + 'px';
    node.style.top = top + 'px';

    global.setTimeout(function () {
      document.addEventListener('mousedown', onOutside, true);
      document.addEventListener('keydown', onKey, true);
      global.addEventListener('resize', close);
    }, 0);

    return { el: node, close: close };
  }

  /* ------------------------------------------------------------ clipboard */

  function copyText(text) {
    var value = String(text === undefined || text === null ? '' : text);
    if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
      return global.navigator.clipboard.writeText(value).then(function () {
        return true;
      }, function () {
        return fallbackCopy(value);
      });
    }
    return Promise.resolve(fallbackCopy(value));
  }

  function fallbackCopy(value) {
    try {
      var area = el('textarea', { style: { position: 'fixed', top: '-1000px', opacity: '0' } });
      area.value = value;
      document.body.appendChild(area);
      area.focus();
      area.select();
      var ok = document.execCommand && document.execCommand('copy');
      document.body.removeChild(area);
      return !!ok;
    } catch (error) {
      return false;
    }
  }

  function download(filename, content, mime) {
    try {
      var blob = content instanceof global.Blob ? content : new global.Blob([content], { type: mime || 'text/plain;charset=utf-8' });
      var url = global.URL.createObjectURL(blob);
      var link = el('a', { href: url, download: filename, style: { display: 'none' } });
      document.body.appendChild(link);
      link.click();
      global.setTimeout(function () {
        if (link.parentNode) {
          link.parentNode.removeChild(link);
        }
        global.URL.revokeObjectURL(url);
      }, 1200);
      return true;
    } catch (error) {
      return false;
    }
  }

  /* ------------------------------------------------------------- formatting */

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

  function toMillis(value) {
    if (typeof value === 'string' && value && isNaN(Number(value))) {
      var parsed = Date.parse(value);
      return isNaN(parsed) ? 0 : parsed;
    }
    var number = Number(value) || 0;
    if (!number) {
      return 0;
    }
    // File timestamps arrive in nanoseconds; JavaScript counts milliseconds.
    return number > 1e14 ? Math.round(number / 1e6) : number;
  }

  function formatDateTime(value) {
    var ms = toMillis(value);
    if (!ms) {
      return '';
    }
    var date = new Date(ms);
    if (isNaN(date.getTime())) {
      return '';
    }
    var locale = I18N.getLanguage();
    try {
      return date.toLocaleString(locale, {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false
      });
    } catch (error) {
      return date.toISOString().slice(0, 16).replace('T', ' ');
    }
  }

  function formatDate(value) {
    var ms = toMillis(value);
    if (!ms) {
      return '';
    }
    var date = new Date(ms);
    if (isNaN(date.getTime())) {
      return '';
    }
    try {
      return date.toLocaleDateString(I18N.getLanguage(), { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (error) {
      return date.toISOString().slice(0, 10);
    }
  }

  function formatTimeAgo(value) {
    var ms = toMillis(value);
    if (!ms) {
      return I18N.t('common.never');
    }
    var diff = Date.now() - ms;
    if (diff < 0) {
      diff = 0;
    }
    var minutes = Math.floor(diff / 60000);
    if (minutes < 1) {
      return I18N.t('time.justNow');
    }
    if (minutes < 60) {
      return I18N.t('time.minutesAgo', { n: minutes });
    }
    var hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return I18N.t('time.hoursAgo', { n: hours });
    }
    var days = Math.floor(hours / 24);
    if (days < 30) {
      return I18N.t('time.daysAgo', { n: days });
    }
    return formatDate(ms);
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

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  global.UI = {
    el: el,
    icon: icon,
    clear: clear,
    show: show,
    hide: hide,
    toast: toast,
    loading: loading,
    empty: empty,
    emptyState: emptyState,
    errorBox: errorBox,
    hintNode: hintNode,
    skeleton: skeleton,
    badge: badge,
    statusBadge: statusBadge,
    modal: modal,
    confirm: confirm,
    promptDialog: promptDialog,
    menu: menu,
    copyText: copyText,
    download: download,
    formatBytes: formatBytes,
    formatDateTime: formatDateTime,
    formatDate: formatDate,
    formatTimeAgo: formatTimeAgo,
    escapeHtml: escapeHtml,
    debounce: debounce,
    clamp: clamp
  };
})(window);
