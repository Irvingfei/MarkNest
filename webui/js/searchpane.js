/* MarkNest for TOS - search.

   Results replace the tree in the same pane rather than opening a third one: a
   note library is one axis of navigation at a time, and a permanent results
   column would cost width that the editor and preview need more.

   The snippet the backend returns is plain text with no markup in it, and it is
   escaped here before the matched terms are wrapped. Escaping then marking is
   the only order that cannot be talked into rendering a note's content as
   markup. */

(function (global) {
  'use strict';

  var state = {
    active: false,
    query: '',
    hits: [],
    timer: null,
    onOpen: null,
    onExit: null
  };

  var hosts = {};

  function cacheHosts() {
    hosts.box = document.getElementById('search-box');
    hosts.body = document.getElementById('tree-body');
    hosts.footer = document.getElementById('tree-footer');
  }

  function markSnippet(snippet, query) {
    var escaped = UI.escapeHtml(snippet || '');
    var terms = String(query || '').split(/\s+/).filter(function (t) { return t; });
    terms.forEach(function (term) {
      var safe = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      escaped = escaped.replace(new RegExp('(' + safe + ')', 'gi'), '<mark>$1</mark>');
    });
    return escaped;
  }

  function render() {
    if (!hosts.body) {
      return;
    }
    UI.clear(hosts.body);
    if (!state.active) {
      return;
    }
    if (!state.hits.length) {
      hosts.body.appendChild(
        UI.el('div', { class: 'empty', text: I18N.t('search.none') })
      );
      return;
    }
    state.hits.forEach(function (hit) {
      var node = UI.el('button', { type: 'button', class: 'hit', title: hit.path });
      node.appendChild(UI.el('div', { class: 'hit-title', text: hit.title || hit.path }));
      node.appendChild(UI.el('div', { class: 'hit-path', text: hit.path }));
      if (hit.snippet) {
        var snippet = UI.el('div', { class: 'hit-snippet' });
        snippet.innerHTML = markSnippet(hit.snippet, state.query);
        node.appendChild(snippet);
      }
      node.addEventListener('click', function () {
        if (typeof state.onOpen === 'function') {
          state.onOpen(hit.path);
        }
        exit();
      });
      hosts.body.appendChild(node);
    });
  }

  function run() {
    var query = hosts.box ? hosts.box.value.trim() : '';
    state.query = query;
    if (!query) {
      exit();
      return;
    }
    state.active = true;
    UI.loading(hosts.body, I18N.t('common.loading'));
    API.search(query).then(function (payload) {
      state.hits = (payload && payload.hits) || [];
      render();
      if (hosts.footer) {
        hosts.footer.textContent = I18N.t('search.results', { n: state.hits.length }) +
          ' · ' + (payload && payload.engine === 'fts5'
            ? I18N.t('search.engineFts')
            : I18N.t('search.engineScan'));
        hosts.footer.className = 'pane-foot';
      }
    }).catch(function (error) {
      UI.clear(hosts.body);
      hosts.body.appendChild(
        UI.errorBox(UI.el('div'), I18N.errorText(error), run)
      );
    });
  }

  function exit() {
    if (!state.active) {
      return;
    }
    state.active = false;
    state.hits = [];
    if (typeof state.onExit === 'function') {
      state.onExit();
    }
  }

  function onInput() {
    if (state.timer) {
      global.clearTimeout(state.timer);
    }
    state.timer = global.setTimeout(run, 220);
  }

  function init(options) {
    cacheHosts();
    var opts = options || {};
    state.onOpen = opts.onOpen;
    state.onExit = opts.onExit;
    if (hosts.box) {
      hosts.box.addEventListener('input', onInput);
      hosts.box.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          hosts.box.value = '';
          exit();
        }
      });
    }
  }

  global.SearchPane = {
    init: init,
    run: run,
    exit: exit,
    isActive: function () { return state.active; }
  };
})(window);
