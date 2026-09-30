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

  /* Line-start commands act on the lines the selection touches, not on the
     selection as one string: selecting a paragraph and pressing the quote
     button is how a paragraph gets quoted. The range is widened to whole line
     boundaries first, so a selection ending mid-line still transforms that
     line in full. */
  function blockRange(doc, from, to) {
    var start = doc.lastIndexOf('\n', from - 1) + 1;
    var end = doc.indexOf('\n', to);
    if (end === -1) {
      end = doc.length;
    }
    return { start: start, end: end, lines: doc.slice(start, end).split('\n') };
  }

  function isBlank(line) {
    return line.trim() === '';
  }

  /* Whether the whole block loses its markers or gains them is decided once
     for the block, not per line. Deciding per line would flip some lines up
     while others flipped down inside the same mixed selection, which is not
     something one press of one button asked for. A block with nothing but
     blank lines toggles nothing rather than counting as "all marked". */
  function allMarked(lines, carries) {
    var marked = false;
    for (var i = 0; i < lines.length; i += 1) {
      if (isBlank(lines[i])) {
        continue;
      }
      if (!carries(lines[i])) {
        return false;
      }
      marked = true;
    }
    return marked;
  }

  function blockResult(range, ctx, text) {
    var delta = text.length - (range.end - range.start);
    return {
      changes: { from: range.start, to: range.end, insert: text },
      selection: {
        anchor: Math.max(range.start, ctx.from + delta),
        head: Math.max(range.start, ctx.to + delta)
      }
    };
  }

  function lineCommand(ctx, prefixes, apply) {
    var range = blockRange(ctx.doc, ctx.from, ctx.to);
    var matched = function (line) {
      for (var i = 0; i < prefixes.length; i += 1) {
        if (line.slice(0, prefixes[i].length) === prefixes[i]) {
          return prefixes[i];
        }
      }
      return '';
    };
    var removing = allMarked(range.lines, function (line) { return matched(line) !== ''; });
    var text = range.lines.map(function (line) {
      // A marker on an otherwise empty line is either a dangling list item or
      // trailing whitespace; neither is what someone selecting a paragraph
      // asked for, so blank lines never gain one.
      if (isBlank(line)) {
        return line;
      }
      var prefix = matched(line);
      if (removing) {
        return prefix ? line.slice(prefix.length) : line;
      }
      return prefix ? line : apply(line);
    }).join('\n');
    return blockResult(range, ctx, text);
  }

  var HEADING = /^#{1,6} /;

  function heading(ctx, level) {
    var hashes = new Array(level + 1).join('#') + ' ';
    var range = blockRange(ctx.doc, ctx.from, ctx.to);
    var removing = allMarked(range.lines, function (line) {
      // "Already at this level" means exactly this many hashes; a line at
      // another level is not a reason to remove.
      return line.slice(0, hashes.length) === hashes;
    });
    var text = range.lines.map(function (line) {
      if (isBlank(line)) {
        return line;
      }
      // Stripping whatever level is present before applying this one is what
      // makes pressing H2 on an H3 line replace the level rather than stack a
      // second set of hashes.
      var bare = line.replace(HEADING, '');
      return removing ? bare : hashes + bare;
    }).join('\n');
    return blockResult(range, ctx, text);
  }

  function quote(ctx) { return lineCommand(ctx, ['> '], function (t) { return '> ' + t; }); }
  function h1(ctx) { return heading(ctx, 1); }
  function h2(ctx) { return heading(ctx, 2); }
  function h3(ctx) { return heading(ctx, 3); }

  /* --------------------------------------------------------------- list */

  function task(ctx) {
    return lineCommand(ctx, ['- [ ] ', '- [x] '], function (t) { return '- [ ] ' + t; });
  }

  /* Longest marker first. With `- ` ahead of the task markers, `- [ ] ` could
     never match - the shorter prefix always won - and the unordered-list
     button on a task item left the orphaned `[ ] ` behind, which is not a list
     item in any renderer. The two task entries are here precisely so that a
     task item counts as an unordered item and loses its whole marker. */
  function bullet(ctx) {
    return lineCommand(ctx, ['- [ ] ', '- [x] ', '- '], function (t) { return '- ' + t; });
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
