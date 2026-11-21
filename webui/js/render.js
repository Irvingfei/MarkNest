/* MarkNest for TOS - Markdown rendering and reading helpers.

   The parser lives in the editor bundle (markdown-it with html:false and
   DOMPurify behind it); this module is the thin seam the reader, the editor
   preview and the export paths share, so all three produce the same markup and
   resolve attachment paths the same way.

   Images in a note are relative to the note's own folder:

       ![chart](.assets/chart-1a2b3c4d.png)

   The bytes sit behind an authenticated proxy, so a plain <img src> cannot load
   them. `hydrateImages` fetches them with the platform headers, keeps the
   resulting object URL in the Store's cache, and swaps it in. The same routine
   is used by both views, which is why a two-pane preview and a full reader
   never disagree about what an image is. */

(function (global) {
  'use strict';

  function ensureRenderer() {
    if (!global.MDEditor || typeof global.MDEditor.render !== 'function') {
      throw new Error('the Markdown renderer is not loaded');
    }
  }

  function markdown(source) {
    ensureRenderer();
    return global.MDEditor.render(source || '');
  }

  /* ------------------------------------------------------------- note paths */

  function folderOf(path) {
    var text = String(path || '');
    var index = text.lastIndexOf('/');
    return index === -1 ? '' : text.slice(0, index);
  }

  function baseName(path) {
    var text = String(path || '');
    var index = text.lastIndexOf('/');
    return index === -1 ? text : text.slice(index + 1);
  }

  function stemOf(path) {
    var name = baseName(path);
    var dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(0, dot) : name;
  }

  /* Only library-relative attachment references resolve. Anything absolute,
     protocol-relative or already a data/blob URL is left to the browser - it is
     either markup the sanitiser already vetted or an image the note cannot
     reach. */
  function resolveAsset(notePath, src) {
    var value = String(src || '').trim();
    if (!value) {
      return '';
    }
    if (/^(?:[a-z][a-z0-9+.-]*:|\/\/|\/|#)/i.test(value)) {
      return '';
    }
    value = value.replace(/^\.\//, '');
    if (value.indexOf('../') === 0) {
      return '';
    }
    if (value.indexOf('.assets/') !== 0) {
      return '';
    }
    var dir = folderOf(notePath);
    return dir ? dir + '/' + value : value;
  }

  /* ----------------------------------------------------------------- images */

  function imagesIn(container) {
    if (!container || !container.querySelectorAll) {
      return [];
    }
    return Array.prototype.slice.call(container.querySelectorAll('img'));
  }

  function hydrateImages(container, notePath) {
    var jobs = imagesIn(container).map(function (img) {
      var raw = img.getAttribute('src') || '';
      var assetPath = resolveAsset(notePath, raw);
      if (!assetPath) {
        return Promise.resolve();
      }
      img.classList.add('is-loading');
      img.dataset.asset = assetPath;
      return Store.assetUrl(assetPath).then(function (url) {
        img.src = url;
        img.classList.remove('is-loading');
        img.classList.add('is-loaded');
      }, function () {
        img.classList.remove('is-loading');
        img.classList.add('is-missing');
        img.alt = img.alt || I18N.t('editor.imageFailed');
      });
    });
    return Promise.all(jobs);
  }

  /* ----------------------------------------------------------------- outline */

  function stripInline(text) {
    return String(text || '')
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/[*_~`]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function outline(source) {
    var lines = String(source || '').split(/\r?\n/);
    var items = [];
    var fence = null;
    lines.forEach(function (line, index) {
      var marker = line.match(/^\s*(`{3,}|~{3,})/);
      if (marker) {
        if (!fence) {
          fence = marker[1].charAt(0);
        } else if (marker[1].charAt(0) === fence) {
          fence = null;
        }
        return;
      }
      if (fence) {
        return;
      }
      var match = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (match) {
        items.push({
          level: match[1].length,
          text: stripInline(match[2]),
          line: index + 1
        });
      }
    });
    return items;
  }

  /* The first H1 is the note's title, but a note that starts with one is the
     exception rather than the rule. Falling back to the file stem keeps the
     library list legible without rewriting anybody's file. */
  function titleOf(content, path) {
    var items = outline(content);
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].level === 1) {
        return items[i].text;
      }
    }
    return stemOf(path) || I18N.t('common.untitled');
  }

  /* ------------------------------------------------------------ measurement */

  var CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/g;

  /* Words as a reader counts them: a CJK character is a word, and runs of
     Latin letters/digits are words. Counting whitespace-separated tokens makes
     a Chinese note look ten times shorter than it is. */
  function countWords(source) {
    var text = String(source || '');
    var cjk = (text.match(CJK) || []).length;
    var rest = text.replace(CJK, ' ');
    var latin = (rest.match(/[A-Za-z0-9][A-Za-z0-9'’_-]*/g) || []).length;
    return cjk + latin;
  }

  function readingMinutes(words) {
    return Math.max(1, Math.round((words || 0) / 280));
  }

  /* ----------------------------------------------------------------- export */

  function dataUrlOf(blobUrl) {
    return fetch(blobUrl).then(function (response) {
      if (!response.ok) {
        throw new Error('image fetch failed');
      }
      return response.blob();
    }).then(function (blob) {
      return new Promise(function (resolve, reject) {
        var reader = new global.FileReader();
        reader.onload = function () { resolve(reader.result); };
        reader.onerror = function () { reject(reader.error); };
        reader.readAsDataURL(blob);
      });
    });
  }

  function inlineHtml(note) {
    var holder = global.document.createElement('div');
    holder.innerHTML = markdown(note.content);
    var jobs = imagesIn(holder).map(function (img) {
      var assetPath = resolveAsset(note.path, img.getAttribute('src') || '');
      if (!assetPath) {
        return Promise.resolve();
      }
      return Store.assetUrl(assetPath)
        .then(dataUrlOf)
        .then(function (dataUrl) {
          img.setAttribute('src', dataUrl);
        }, function () {
          /* a missing image must not abort the export */
        });
    });
    return Promise.all(jobs).then(function () {
      return holder.innerHTML;
    });
  }

  /* A standalone HTML file with the images embedded. A reader who is handed the
     file may have no access to the NAS at all, so remote references would be
     broken images; inlining is the only export that actually travels. */
  function exportHtml(note, options) {
    var opts = options || {};
    var title = opts.title || titleOf(note.content, note.path);
    return inlineHtml(note).then(function (body) {
      return '<!DOCTYPE html>\n<html lang="' + (opts.lang || 'zh-cn') + '">\n<head>\n' +
        '<meta charset="utf-8">\n' +
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
        '<title>' + UI.escapeHtml(title) + '</title>\n' +
        '<style>\n' + EXPORT_CSS + '\n</style>\n</head>\n<body>\n<article class="markdown-body">\n' +
        body +
        '\n</article>\n</body>\n</html>\n';
    });
  }

  var EXPORT_CSS = [
    ':root{color-scheme:light dark}',
    'body{margin:0;background:#f4f1e8;color:#26221b;font:17px/1.75 "Iowan Old Style","Palatino Linotype","Songti SC",Georgia,serif}',
    '.markdown-body{max-width:740px;margin:0 auto;padding:56px 24px 96px;background:#fffdf8;box-shadow:0 1px 3px rgba(38,34,27,.08)}',
    'h1,h2,h3,h4{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.3;margin:1.5em 0 .6em}',
    'h1{font-size:2em;border-bottom:1px solid #e2dccd;padding-bottom:.3em}',
    'h2{font-size:1.5em}',
    'a{color:#2f6b57}',
    'code,pre{font-family:"Cascadia Mono",Consolas,monospace;font-size:.9em}',
    'code{background:#f3efe4;border:1px solid #e2dccd;border-radius:4px;padding:.1em .35em}',
    'pre{background:#f7f4ec;border:1px solid #e2dccd;border-radius:8px;padding:14px 16px;overflow:auto}',
    'pre code{background:none;border:0;padding:0}',
    'blockquote{margin:1em 0;padding:.2em 0 .2em 1.1em;border-left:3px solid #cdc4ae;color:#5d574b}',
    'img{max-width:100%;border-radius:8px}',
    'table{border-collapse:collapse;margin:1em 0;font-family:"Segoe UI","PingFang SC",sans-serif;font-size:.92em}',
    'th,td{border:1px solid #e2dccd;padding:6px 12px}',
    'th{background:#f7f4ec}',
    'hr{border:0;border-top:1px solid #e2dccd;margin:2em 0}',
    '@media (prefers-color-scheme:dark){body{background:#141513;color:#ece7db}.markdown-body{background:#1b1d1a;box-shadow:none}code,pre,th{background:#23261f;border-color:#34382f}h1{border-color:#34382f}a{color:#7ebaa1}blockquote{border-color:#454a3e;color:#a8a293}th,td{border-color:#34382f}}',
    '@media print{body{background:#fff}.markdown-body{box-shadow:none;max-width:none;padding:0}}'
  ].join('\n');

  global.Render = {
    markdown: markdown,
    outline: outline,
    titleOf: titleOf,
    folderOf: folderOf,
    baseName: baseName,
    stemOf: stemOf,
    resolveAsset: resolveAsset,
    hydrateImages: hydrateImages,
    countWords: countWords,
    readingMinutes: readingMinutes,
    inlineHtml: inlineHtml,
    exportHtml: exportHtml
  };
})(window);
