/* MarkNest for TOS - the document actions shared by the reader and the editor.

   Export, share and version history mean the same thing in both views, so they
   are written once. The reader and the editor differ only in which surface they
   put them on: the reader has a toolbar under the title, the editor has a menu
   in its header.

   Sharing is a deep link plus the note itself, not a public link. A library is
   per-user and sits behind the platform session, so a token that worked for
   everybody would be a permission system this application does not have. What
   can be shared honestly is the Markdown, the rendered text, the HTML file, and
   the address of the note for somebody already signed in. */

(function (global) {
  'use strict';

  function filename(note, extension) {
    var stem = Render.stemOf(note.path) || 'note';
    return stem.replace(/[\\/:*?"<>|]/g, '-') + '.' + extension;
  }

  function exportMarkdown(note) {
    if (UI.download(filename(note, 'md'), note.content, 'text/markdown;charset=utf-8')) {
      UI.toast(I18N.t('reader.exportMarkdown'), 'ok');
    } else {
      UI.toast(I18N.t('err.unknown'), 'bad');
    }
  }

  function exportHtml(note, options) {
    var opts = options || {};
    UI.toast(I18N.t('common.loading'));
    return Render.exportHtml(note, opts).then(function (html) {
      if (UI.download(filename(note, 'html'), html, 'text/html;charset=utf-8')) {
        UI.toast(I18N.t('editor.exportHtmlDone'), 'ok');
      } else {
        UI.toast(I18N.t('err.unknown'), 'bad');
      }
    }).catch(function (error) {
      UI.toast((error && error.message) || I18N.t('err.unknown'), 'bad');
    });
  }

  function noteLink(note) {
    var base = global.location.href.split('#')[0];
    return base + Router.href('read', { p: note.path });
  }

  function copyLink(note) {
    UI.copyText(noteLink(note)).then(function (ok) {
      UI.toast(ok ? I18N.t('editor.copied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
    });
  }

  function copyMarkdown(note) {
    UI.copyText(note.content).then(function (ok) {
      UI.toast(ok ? I18N.t('editor.copied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
    });
  }

  /* Rich copy goes through the async clipboard with two flavours. The plain
     text is the Markdown source, so a paste into a terminal or a code editor is
     still the note rather than a flattened rendering. */
  function copyRich(note) {
    if (!global.navigator.clipboard || typeof global.ClipboardItem === 'undefined') {
      copyMarkdown(note);
      return;
    }
    Render.inlineHtml(note).then(function (html) {
      var item = new global.ClipboardItem({
        'text/html': new global.Blob([html], { type: 'text/html' }),
        'text/plain': new global.Blob([note.content], { type: 'text/plain' })
      });
      return global.navigator.clipboard.write([item]);
    }).then(function () {
      UI.toast(I18N.t('editor.copied'), 'ok');
    }).catch(function () {
      copyMarkdown(note);
    });
  }

  function itemMenu(anchor, note, items) {
    UI.menu(anchor, items);
  }

  function exportMenu(anchor, note) {
    itemMenu(anchor, note, [
      { label: I18N.t('editor.exportMd'), icon: 'download', onClick: function () { exportMarkdown(note); } },
      { label: I18N.t('editor.exportHtml'), icon: 'file-text', onClick: function () { exportHtml(note); } }
    ]);
  }

  function shareMenu(anchor, note) {
    itemMenu(anchor, note, [
      { label: I18N.t('editor.copyLink'), icon: 'link', onClick: function () { copyLink(note); } },
      { label: I18N.t('editor.copyRich'), icon: 'copy', onClick: function () { copyRich(note); } },
      { label: I18N.t('editor.copyMarkdown'), icon: 'code', onClick: function () { copyMarkdown(note); } },
      { divider: true },
      { label: I18N.t('editor.exportMd'), icon: 'download', onClick: function () { exportMarkdown(note); } },
      { label: I18N.t('editor.exportHtml'), icon: 'file-text', onClick: function () { exportHtml(note); } },
      { label: I18N.t('reader.print'), icon: 'file', onClick: function () { global.print(); } }
    ]);
  }

  /* ------------------------------------------------------------ versions */

  function versions(note, onRestore) {
    var host = UI.el('div', { class: 'version-list' });
    var dialog = UI.modal({
      title: I18N.t('editor.versionHistory'),
      subtitle: note.path,
      body: host,
      width: 'wide'
    });

    function load() {
      UI.clear(host);
      UI.skeleton(host, 3);
      API.getVersions(note.path).then(function (payload) {
        UI.clear(host);
        var list = (payload && payload.versions) || [];
        if (!list.length) {
          host.appendChild(UI.emptyState({
            icon: 'clock',
            title: I18N.t('editor.versionEmpty'),
            body: I18N.t('editor.versionEmptyBody')
          }));
          return;
        }
        var table = UI.el('div', { class: 'version-table' });
        list.forEach(function (version, index) {
          table.appendChild(UI.el('div', { class: 'version-row' }, [
            UI.el('div', { class: 'version-when' }, [
              UI.el('div', { class: 'version-time', text: UI.formatDateTime(version.created_at) }),
              UI.el('div', { class: 'version-ago', text: UI.formatTimeAgo(version.created_ns || version.created_at) })
            ]),
            UI.el('div', { class: 'version-size', text: UI.formatBytes(version.size) }),
            index === 0 ? UI.badge('accent', I18N.t('time.justNow')) : null,
            UI.el('button', {
              type: 'button',
              class: 'btn btn-sm',
              text: I18N.t('editor.versionRestore'),
              onclick: function () { restore(version); }
            })
          ]));
        });
        host.appendChild(table);
      }, function (error) {
        UI.errorBox(host, (error && error.message) || I18N.t('editor.versionLoadFail'),
          load, '');
      });
    }

    function restore(version) {
      UI.confirm({
        title: I18N.t('editor.versionRestore'),
        message: I18N.t('editor.versionRestoreConfirm', { time: UI.formatDateTime(version.created_at) }),
        confirmLabel: I18N.t('common.restore')
      }).then(function (ok) {
        if (!ok) {
          return null;
        }
        return API.restoreVersion(note.path, version.id).then(function (restored) {
          UI.toast(I18N.t('editor.versionRestored'), 'ok');
          dialog.close(true);
          if (typeof onRestore === 'function') {
            onRestore(restored);
          }
          return restored;
        });
      }).catch(function (error) {
        UI.toast((error && error.message) || I18N.t('err.unknown'), 'bad');
      });
    }

    load();
    return dialog;
  }

  global.Pages = global.Pages || {};
  global.Pages.doc = {
    exportMarkdown: exportMarkdown,
    exportHtml: exportHtml,
    copyLink: copyLink,
    copyMarkdown: copyMarkdown,
    copyRich: copyRich,
    exportMenu: exportMenu,
    shareMenu: shareMenu,
    versions: versions,
    filename: filename,
    noteLink: noteLink
  };
})(window);
