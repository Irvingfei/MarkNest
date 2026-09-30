/* MarkNest for TOS - the Markdown format toolbar.
 *
 * This module is only wiring: it turns a button press into a pure command from
 * MDCmd and hands it to the editor. The commands themselves are tested without
 * a browser (see tools/webui_check.js), so a bug here can only be about which
 * button calls which command.
 *
 * The link button is the one that needs an answer before it can act, so it asks
 * for a URL first and then runs the same command shape as the rest. */

(function (global) {
  'use strict';

  var GROUPS = [
    [
      { id: 'bold', label: 'B', title: 'format.bold', command: 'bold', style: 'is-bold' },
      { id: 'italic', label: 'I', title: 'format.italic', command: 'italic', style: 'is-italic' },
      { id: 'code', label: '<>', title: 'format.code', command: 'code', style: 'is-mono' }
    ],
    [
      { id: 'codeblock', label: '```', title: 'format.codeblock', command: 'codeblock', style: 'is-mono' },
      { id: 'quote', label: '“', title: 'format.quote', command: 'quote' },
      { id: 'h1', label: 'H1', title: 'format.h1', command: 'h1' },
      { id: 'h2', label: 'H2', title: 'format.h2', command: 'h2' },
      { id: 'h3', label: 'H3', title: 'format.h3', command: 'h3' }
    ],
    [
      { id: 'task', label: '☐', title: 'format.task', command: 'task' },
      { id: 'bullet', label: '•', title: 'format.bullet', command: 'bullet' },
      { id: 'numbered', label: '1.', title: 'format.numbered', command: 'numbered' }
    ],
    [
      { id: 'link', label: '\u{1F517}', title: 'format.link', command: 'link' },
      { id: 'table', label: '▦', title: 'format.table', command: 'table' }
    ]
  ];

  var hosts = {};
  var enabled = false;

  function onPress(item) {
    if (!enabled) {
      return;
    }
    if (item.command === 'link') {
      global.EditorPane.applyCommand(function (ctx) {
        // Asked here rather than before applyCommand so that a read-only note -
        // which applyEdit refuses before ever calling us - cannot raise two
        // dialogs and then discard the answer. A null return abandons the edit.
        var label = ctx.selected;
        if (!label) {
          label = global.prompt(I18N.t('format.linkTextPrompt'), '');
          if (label === null) {
            return null;
          }
        }
        // window.prompt returns null immediately inside an iframe that has not
        // been granted allow-modals, which would make this button a silent
        // no-op on the real TOS desktop while working here, where the page is
        // loaded unsandboxed. The device check at deployment is what settles
        // it; do not replace the prompt with a custom dialog on the strength of
        // a suspicion.
        var url = global.prompt(I18N.t('format.linkPrompt'), 'https://');
        if (!url) {
          return null;
        }
        return MDCmd.commands.link(ctx, url, label);
      });
      return;
    }
    global.EditorPane.applyCommand(MDCmd.commands[item.command]);
  }

  function render() {
    if (!hosts.bar) {
      return;
    }
    UI.clear(hosts.bar);
    GROUPS.forEach(function (group, index) {
      if (index > 0) {
        hosts.bar.appendChild(UI.el('span', { class: 'format-sep', 'aria-hidden': 'true' }));
      }
      group.forEach(function (item) {
        hosts.bar.appendChild(
          UI.el('button', {
            type: 'button',
            class: 'format-btn' + (item.style ? ' ' + item.style : ''),
            id: 'fmt-' + item.id,
            text: item.label,
            'data-i18n-title': item.title,
            title: item.title,
            onclick: function () { onPress(item); }
          })
        );
      });
    });
    // The buttons did not exist when boot applied the translations, and the
    // only other apply() runs from the language selector - so without this the
    // title attribute stays the raw key and the tooltip reads "format.bold".
    // Rendering is the one place that knows the buttons are new.
    I18N.apply(hosts.bar);
  }

  function setEnabled(flag) {
    enabled = !!flag;
    if (hosts.bar) {
      hosts.bar.hidden = !enabled;
    }
  }

  function init() {
    hosts.bar = document.getElementById('format-bar');
    render();
    setEnabled(false);
  }

  global.FormatBar = { init: init, render: render, setEnabled: setEnabled };
})(window);
