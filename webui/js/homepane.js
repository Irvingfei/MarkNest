/* MarkNest for TOS - the home screen.
 *
 * Shown whenever no note is open. It answers the two questions a person has
 * when they arrive: how do I get a note open, and what was I working on. The
 * list is the index ordered by file modification time, so a note edited over
 * SMB appears here after the next scan without this module tracking anything. */

(function (global) {
  'use strict';

  var RECENT_LIMIT = 12;
  var state = { onOpen: null };

  var hosts = {};

  function cacheHosts() {
    hosts.recent = document.getElementById('home-recent');
    hosts.open = document.getElementById('home-open');
    hosts.create = document.getElementById('home-new');
  }

  /* Relative time, computed here rather than on the server: the server would
     have to send a rendering decision down with the data, and the answer goes
     stale while the page is open. */
  function relativeTime(ns) {
    if (!ns) {
      return '';
    }
    var then = ns / 1e6;
    var seconds = Math.max(0, (Date.now() - then) / 1000);
    if (seconds < 60) {
      return I18N.t('home.timeJustNow');
    }
    if (seconds < 3600) {
      return I18N.t('home.timeMinutes', { n: Math.floor(seconds / 60) });
    }
    if (seconds < 86400) {
      return I18N.t('home.timeHours', { n: Math.floor(seconds / 3600) });
    }
    if (seconds < 172800) {
      return I18N.t('home.timeYesterday');
    }
    if (seconds < 604800) {
      return I18N.t('home.timeDays', { n: Math.floor(seconds / 86400) });
    }
    var date = new Date(then);
    return date.getFullYear() + '-' +
      String(date.getMonth() + 1).padStart(2, '0') + '-' +
      String(date.getDate()).padStart(2, '0');
  }

  function render(rows) {
    if (!hosts.recent) {
      return;
    }
    UI.clear(hosts.recent);
    hosts.recent.appendChild(
      UI.el('div', { class: 'home-recent-title', 'data-i18n': 'home.recent',
                     text: I18N.t('home.recent') })
    );
    if (!rows.length) {
      hosts.recent.appendChild(
        UI.el('div', { class: 'empty', text: I18N.t('home.noRecent') })
      );
      return;
    }
    var list = UI.el('div', { class: 'home-recent-list' });
    rows.forEach(function (row) {
      var item = UI.el('button', { type: 'button', class: 'home-recent-item',
                                   title: row.path });
      item.appendChild(UI.el('span', { class: 'home-recent-name',
                                       text: row.title || row.path }));
      item.appendChild(UI.el('span', { class: 'home-recent-time',
                                       text: relativeTime(row.mtime_ns) }));
      item.addEventListener('click', function () {
        if (typeof state.onOpen === 'function') {
          state.onOpen(row.path, true);
        }
      });
      list.appendChild(item);
    });
    hosts.recent.appendChild(list);
  }

  function reload() {
    if (!hosts.recent) {
      cacheHosts();
    }
    return API.getRecent(RECENT_LIMIT).then(function (payload) {
      render((payload && payload.recent) || []);
    }).catch(function (error) {
      if (!hosts.recent) {
        return;
      }
      UI.clear(hosts.recent);
      hosts.recent.appendChild(UI.errorBox(UI.el('div'), I18N.errorText(error), reload));
    });
  }

  function init(options) {
    cacheHosts();
    state.onOpen = (options || {}).onOpen || null;
    if (hosts.open) {
      hosts.open.addEventListener('click', function () {
        if (global.FilePicker) {
          global.FilePicker.open();
        }
      });
    }
    if (hosts.create) {
      hosts.create.addEventListener('click', function () {
        if (global.TreePane) {
          global.TreePane.newNote();
        }
      });
    }
  }

  global.HomePane = { init: init, reload: reload, render: render };
})(window);
