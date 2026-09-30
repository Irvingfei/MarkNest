/* MarkNest for TOS - the Markdown editing commands.
 *
 * Every command is a pure function: a document and a selection go in, a change
 * and a new selection come out. Nothing here touches the DOM or an editor
 * instance, which is what lets tools/webui_check.js assert every one of them
 * without a browser - and the fiddly parts of this file (what happens with no
 * selection, and whether a second press undoes the first) are exactly the parts
 * that would otherwise only be checked by accident.
 *
 * The contract with the caller:
 *
 *   command({doc, from, to, selected}) -> {changes: {from, to, insert}, selection}
 *
 * Offsets are absolute positions in `doc`.
 */

(function (global) {
  'use strict';

  function sliceLine(doc, from, to) {
    var start = doc.lastIndexOf('\n', from - 1) + 1;
    var end = doc.indexOf('\n', to);
    if (end === -1) {
      end = doc.length;
    }
    return { start: start, end: end, text: doc.slice(start, end) };
  }

  function replace(from, to, insert, selection) {
    return {
      changes: { from: from, to: to, insert: insert },
      selection: selection || { anchor: from + insert.length }
    };
  }

  /* ------------------------------------------------------------- inline */

  /* Wrapping commands share one shape: if the selection already carries the
     markers, take them off; otherwise put them on and keep the text selected
     so a second press undoes it. */
  function wrap(ctx, marker) {
    var doc = ctx.doc;
    var from = ctx.from;
    var to = ctx.to;
    var selected = ctx.selected;
    var size = marker.length;

    if (selected.length >= size * 2 &&
        selected.slice(0, size) === marker &&
        selected.slice(-size) === marker) {
      var inner = selected.slice(size, selected.length - size);
      return replace(from, to, inner, { anchor: from, head: from + inner.length });
    }

    if (from >= size && doc.slice(from - size, from) === marker &&
        doc.slice(to, to + size) === marker) {
      return replace(from - size, to + size, selected,
        { anchor: from - size, head: from - size + selected.length });
    }

    if (!selected) {
      // No selection: insert the pair and leave the cursor between them, so
      // typing continues inside the emphasis rather than after it.
      return replace(from, to, marker + marker, { anchor: from + size });
    }

    return replace(from, to, marker + selected + marker,
      { anchor: from + size, head: from + size + selected.length });
  }

  function bold(ctx) { return wrap(ctx, '**'); }
  function italic(ctx) { return wrap(ctx, '*'); }
  function code(ctx) { return wrap(ctx, '`'); }

  function codeblock(ctx) {
    var fence = '```\n\n```';
    if (ctx.selected) {
      var body = ctx.selected;
      // A fenced block has to sit on its own lines; joining the surrounding
      // text to the fence would silently change the paragraph it belongs to.
      var lead = ctx.from > 0 && ctx.doc[ctx.from - 1] !== '\n' ? '\n' : '';
      var tail = ctx.to < ctx.doc.length && ctx.doc[ctx.to] !== '\n' ? '\n' : '';
      return replace(ctx.from, ctx.to, lead + '```\n' + body + '\n```' + tail,
        { anchor: ctx.from + lead.length + 4, head: ctx.from + lead.length + 4 + body.length });
    }
    return replace(ctx.from, ctx.to, fence, { anchor: ctx.from + 4 });
  }

  /* -------------------------------------------------------------- block */

  /* Line commands share one shape too: strip any prefix this command would
     apply, then apply it - which makes a second press a no-op instead of
     stacking prefixes. */
  function lineCommand(ctx, prefixes, apply) {
    var line = sliceLine(ctx.doc, ctx.from, ctx.to);
    var text = line.text;
    var stripped = text;
    var removed = false;

    for (var i = 0; i < prefixes.length; i += 1) {
      var prefix = prefixes[i];
      if (stripped.slice(0, prefix.length) === prefix) {
        stripped = stripped.slice(prefix.length);
        removed = true;
        break;
      }
    }

    var next = removed ? stripped : apply(stripped);
    var delta = next.length - text.length;
    return {
      changes: { from: line.start, to: line.end, insert: next },
      selection: {
        anchor: Math.max(line.start, ctx.from + delta),
        head: Math.max(line.start, ctx.to + delta)
      }
    };
  }

  var HEADING = /^#{1,6} /;

  function heading(ctx, level) {
    var hashes = new Array(level + 1).join('#') + ' ';
    var line = sliceLine(ctx.doc, ctx.from, ctx.to);
    var text = line.text;
    var stripped = text.replace(HEADING, '');
    // Pressing the same level again removes the heading; pressing a different
    // level replaces it rather than stacking a second set of hashes.
    var next = text.slice(0, hashes.length) === hashes ? stripped : hashes + stripped;
    var delta = next.length - text.length;
    return {
      changes: { from: line.start, to: line.end, insert: next },
      selection: {
        anchor: Math.max(line.start, ctx.from + delta),
        head: Math.max(line.start, ctx.to + delta)
      }
    };
  }

  function quote(ctx) { return lineCommand(ctx, ['> '], function (t) { return '> ' + t; }); }
  function h1(ctx) { return heading(ctx, 1); }
  function h2(ctx) { return heading(ctx, 2); }
  function h3(ctx) { return heading(ctx, 3); }

  /* --------------------------------------------------------------- list */

  function task(ctx) {
    return lineCommand(ctx, ['- [ ] ', '- [x] '], function (t) { return '- [ ] ' + t; });
  }
  function bullet(ctx) {
    return lineCommand(ctx, ['- ', '- [ ] ', '- [x] '], function (t) { return '- ' + t; });
  }
  function numbered(ctx) {
    return lineCommand(ctx, ['1. '], function (t) { return '1. ' + t; });
  }

  /* ------------------------------------------------------------- insert */

  function link(ctx, url, label) {
    var text = label || ctx.selected || '';
    var insert = '[' + text + '](' + url + ')';
    var urlStart = ctx.from + 1 + text.length + 2;
    return replace(ctx.from, ctx.to, insert,
      { anchor: urlStart, head: urlStart + url.length });
  }

  function table(ctx) {
    var skeleton = '|  |  |  |\n| --- | --- | --- |\n|  |  |  |';
    var lead = ctx.from > 0 && ctx.doc[ctx.from - 1] !== '\n' ? '\n' : '';
    // The cursor lands in the first header cell so the next keystroke types a
    // column name rather than having to be preceded by navigating there.
    return replace(ctx.from, ctx.to, lead + skeleton, { anchor: ctx.from + lead.length + 2 });
  }

  global.MDCmd = {
    commands: {
      bold: bold,
      italic: italic,
      code: code,
      codeblock: codeblock,
      quote: quote,
      h1: h1,
      h2: h2,
      h3: h3,
      task: task,
      bullet: bullet,
      numbered: numbered,
      link: link,
      table: table
    }
  };
})(window);
