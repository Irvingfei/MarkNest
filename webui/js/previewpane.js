/* MarkNest for TOS - the preview pane, and the scroll link to the editor.

   Scroll synchronisation is done by line number rather than by proportion. The
   rendered markup carries `data-line` on every block element - put there by the
   editor bundle, which knows which source line each block came from - so the
   link is "find the last block at or above this line", which stays correct when
   a paragraph renders into three lines of text or an image loads and changes
   the height. A percentage-based link drifts as soon as anything is not the
   height it was when the mapping was computed.

   Both directions can fire while a scroll is being applied, so each side is
   guarded and the result is applied on the next animation frame. */

(function (global) {
  'use strict';

  var state = {
    pending: null,
    timer: null,
    suppress: false,
    rafId: null,
    syncEnabled: true
  };

  var hosts = {};

  function cacheHosts() {
    hosts.body = document.getElementById('preview-body');
  }

  function render(source) {
    if (!hosts.body || !global.MDEditor) {
      return;
    }
    if (!source) {
      hosts.body.innerHTML = '';
      hosts.body.appendChild(
        UI.el('div', { class: 'empty', text: I18N.t('preview.empty') })
      );
      return;
    }
    hosts.body.innerHTML = global.MDEditor.render(source);
  }

  /* Typing fires on every keystroke; rendering on every one would make the
     editor feel heavy on a long note, so the render is deferred. */
  function schedule(source) {
    state.pending = source;
    if (state.timer) {
      global.clearTimeout(state.timer);
    }
    state.timer = global.setTimeout(function () {
      state.timer = null;
      render(state.pending);
    }, 150);
  }

  /* --------------------------------------------------------- scroll linking */

  function blocks() {
    return hosts.body ? hosts.body.querySelectorAll('[data-line]') : [];
  }

  function lineFromScroll() {
    var nodes = blocks();
    if (!nodes.length) {
      return 0;
    }
    var top = hosts.body.scrollTop;
    var line = 0;
    for (var i = 0; i < nodes.length; i += 1) {
      var value = parseInt(nodes[i].getAttribute('data-line'), 10);
      if (!isNaN(value) && nodes[i].offsetTop <= top + 1) {
        line = value;
      } else if (line) {
        break;
      }
    }
    return line;
  }

  function scrollPreviewToLine(line) {
    var nodes = blocks();
    if (!nodes.length || !line) {
      return;
    }
    var target = null;
    for (var i = 0; i < nodes.length; i += 1) {
      var value = parseInt(nodes[i].getAttribute('data-line'), 10);
      if (!isNaN(value) && value <= line) {
        target = nodes[i];
      } else {
        break;
      }
    }
    if (target) {
      hosts.body.scrollTop = target.offsetTop;
    }
  }

  function guarded(fn) {
    if (state.suppress) {
      return;
    }
    state.suppress = true;
    fn();
    // Release on the next frame: this scroll will itself raise a scroll event,
    // and without the guard the two panes push each other back and forth.
    if (state.rafId) {
      global.cancelAnimationFrame(state.rafId);
    }
    state.rafId = global.requestAnimationFrame(function () {
      state.rafId = global.requestAnimationFrame(function () {
        state.suppress = false;
      });
    });
  }

  function onEditorScroll() {
    if (!state.syncEnabled) {
      return;
    }
    var editor = global.EditorPane && global.EditorPane.editor();
    if (!editor) {
      return;
    }
    var line = editor.getTopLine();
    guarded(function () {
      scrollPreviewToLine(line);
    });
  }

  function onPreviewScroll() {
    if (!state.syncEnabled) {
      return;
    }
    var editor = global.EditorPane && global.EditorPane.editor();
    if (!editor) {
      return;
    }
    var line = lineFromScroll();
    if (!line) {
      return;
    }
    guarded(function () {
      editor.scrollToLine(line);
    });
  }

  function bind() {
    if (hosts.body) {
      hosts.body.addEventListener('scroll', onPreviewScroll);
    }
    var editor = global.EditorPane && global.EditorPane.editor();
    if (editor && editor.scrollDOM) {
      editor.scrollDOM.addEventListener('scroll', onEditorScroll);
    }
  }

  function init() {
    cacheHosts();
    render('');
    bind();
  }

  global.PreviewPane = {
    init: init,
    render: render,
    schedule: schedule,
    setEnabled: function (flag) {
      state.syncEnabled = !!flag;
    }
  };
})(window);
