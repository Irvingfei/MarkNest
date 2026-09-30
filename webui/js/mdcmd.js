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
 * Offsets are absolute positions in `doc`. Every command takes that one context
 * object and nothing else, with a single exception: link also needs the URL,
 * and the optional display text, as `link(ctx, url, label)`.
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
    // A fenced block has to sit on its own lines; joining the surrounding text
    // to the fence would silently change the paragraph it belongs to. The
    // no-selection branch needs the guard as much as the selection branch: with
    // the fence glued to the text before it, the opening fence is inline text
    // and the closing one opens a block that swallows the rest of the note.
    var lead = ctx.from > 0 && ctx.doc[ctx.from - 1] !== '\n' ? '\n' : '';
    if (ctx.selected) {
      var body = ctx.selected;
      var tail = ctx.to < ctx.doc.length && ctx.doc[ctx.to] !== '\n' ? '\n' : '';
      return replace(ctx.from, ctx.to, lead + '```\n' + body + '\n```' + tail,
        { anchor: ctx.from + lead.length + 4, head: ctx.from + lead.length + 4 + body.length });
    }
    return replace(ctx.from, ctx.to, lead + fence, { anchor: ctx.from + lead.length + 4 });
  }

  /* -------------------------------------------------------------- block */

  /* Line-start commands act on the lines the selection touches, not on the
     selection as one string: selecting a paragraph and pressing the quote
     button is how a paragraph gets quoted. The range is widened to whole line
     boundaries first, so a selection ending mid-line still transforms that
     line in full. */
  function blockRange(doc, from, to) {
    // from === 0 is checked rather than left to lastIndexOf, because a negative
    // fromIndex is clamped to 0: on a document whose first character is a
    // newline that would match the newline at index 0 and start the block one
    // character in, skipping the empty first line. With `from` here the search
    // is only ever reached with a non-negative index.
    var start = from === 0 ? 0 : doc.lastIndexOf('\n', from - 1) + 1;
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

  function allBlank(lines) {
    for (var i = 0; i < lines.length; i += 1) {
      if (!isBlank(lines[i])) {
        return false;
      }
    }
    return true;
  }

  /* Whether a blank line takes the marker anyway. An all-blank block is where a
     construct gets started - the cursor is on the empty line and the button is
     meant to put the marker there - so its first line takes it. A blank line
     *inside* a block is a different thing: a marker on it is a dangling item or
     trailing whitespace, so it keeps clear. Both the line commands and the
     headings ask this, which is why it has one home. */
  function marksBlank(index, empty) {
    return index === 0 && empty;
  }

  /* Where the two endpoints land after the edit.
   *
   * A single block-wide delta is wrong for anything past the first line: adding
   * a marker to two lines grows the block by two prefixes, and shifting both
   * endpoints by that total moves the start forward by the growth of lines that
   * begin *before* it, so the selection collapses onto the tail of the block
   * instead of covering it. Each endpoint is therefore shifted by the growth of
   * the lines that start strictly before it.
   *
   * A caret is the exception. `from === to` is a point, and a point at the
   * start of a line would be shifted by nothing and left sitting in front of
   * the marker it just caused; the uniform delta is exactly the growth of the
   * one line a caret can be on, which is what puts the cursor after an inserted
   * prefix rather than before it. */
  function blockResult(range, ctx, text) {
    var lines = text.split('\n');
    var growth = [];
    var at = 0;
    for (var i = 0; i < range.lines.length; i += 1) {
      growth.push({ at: range.start + at, by: lines[i].length - range.lines[i].length });
      at += range.lines[i].length + 1;
    }
    var uniform = text.length - (range.end - range.start);
    var shift = function (endpoint) {
      if (ctx.from === ctx.to) {
        return Math.max(range.start, endpoint + uniform);
      }
      var delta = 0;
      for (var j = 0; j < growth.length; j += 1) {
        if (growth[j].at < endpoint) {
          delta += growth[j].by;
        }
      }
      return Math.max(range.start, endpoint + delta);
    };
    return {
      changes: { from: range.start, to: range.end, insert: text },
      selection: { anchor: shift(ctx.from), head: shift(ctx.to) }
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
    var empty = allBlank(range.lines);
    var text = range.lines.map(function (line, index) {
      var prefix = matched(line);
      if (removing) {
        return prefix ? line.slice(prefix.length) : line;
      }
      if (!isBlank(line)) {
        return prefix ? line : apply(line);
      }
      return marksBlank(index, empty) ? apply(line) : line;
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
    var empty = allBlank(range.lines);
    var text = range.lines.map(function (line, index) {
      if (!isBlank(line)) {
        // Stripping whatever level is present before applying this one is what
        // makes pressing H2 on an H3 line replace the level rather than stack a
        // second set of hashes.
        var bare = line.replace(HEADING, '');
        return removing ? bare : hashes + bare;
      }
      return marksBlank(index, empty) ? hashes + line : line;
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
    // Without the trailing newline, a caret mid-word glues whatever follows it
    // onto the table's last row.
    var tail = ctx.to < ctx.doc.length && ctx.doc[ctx.to] !== '\n' ? '\n' : '';
    // The cursor lands in the first header cell so the next keystroke types a
    // column name rather than having to be preceded by navigating there.
    return replace(ctx.from, ctx.to, lead + skeleton + tail,
      { anchor: ctx.from + lead.length + 2 });
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
