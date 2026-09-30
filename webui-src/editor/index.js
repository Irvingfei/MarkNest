// The MarkNest editor bundle.
//
// Everything third-party lives here and nowhere else, so the rest of the WebUI
// stays plain scripts with no build step. The bundle exposes a single global,
// `window.MDEditor`, and is loaded like any other script in index.html.
//
// Two decisions are worth stating because they are easy to undo by accident:
//
//   * The preview is rendered from markdown-it with `html: false` and then
//     passed through DOMPurify. Note content is untrusted input - it can arrive
//     over SMB from anywhere - so raw HTML in a note is not markup, and the
//     sanitiser is a second layer rather than the only one.
//
//   * Every block element carries `data-line`, which is what makes scroll
//     synchronisation possible without a per-element diff. markdown-it counts
//     lines from zero and CodeMirror counts from one, so the conversion happens
//     once, here.

import { EditorState, Compartment } from '@codemirror/state';
import {
  EditorView,
  keymap,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  lineNumbers,
  rectangularSelection,
  crosshairCursor
} from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import {
  syntaxHighlighting,
  defaultHighlightStyle,
  bracketMatching,
  indentOnInput
} from '@codemirror/language';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import MarkdownIt from 'markdown-it';
import markdownItAnchor from 'markdown-it-anchor';
import markdownItTaskLists from 'markdown-it-task-lists';
import markdownItFootnote from 'markdown-it-footnote';
import DOMPurify from 'dompurify';

/* ------------------------------------------------------------------ render */

const md = new MarkdownIt({
  // Raw HTML in a note is not markup. A note is untrusted input - it can be
  // written over SMB by anything on the network - so the parser is told to
  // treat it as text, and DOMPurify is the second layer behind that.
  html: false,
  linkify: true,
  breaks: false,
  typographer: false
});

md.use(markdownItAnchor, { permalink: false });
md.use(markdownItTaskLists, { enabled: true, label: true });
md.use(markdownItFootnote);

// Every block token gets the source line it came from.
md.core.ruler.push('marknest_data_line', (state) => {
  for (const token of state.tokens) {
    if (!token.map || token.nesting === -1) {
      continue;
    }
    token.attrSet('data-line', String(token.map[0] + 1));
  }
  return true;
});

// `fence` and `hr` render their own markup rather than going through
// renderToken, so their attribute never lands. They are patched individually.
for (const rule of ['fence', 'hr', 'code_block']) {
  const original = md.renderer.rules[rule];
  md.renderer.rules[rule] = function (tokens, idx, options, env, self) {
    const html = original
      ? original(tokens, idx, options, env, self)
      : self.renderToken(tokens, idx, options);
    const token = tokens[idx];
    if (!token.map) {
      return html;
    }
    const line = token.map[0] + 1;
    if (html.startsWith('<pre>')) {
      return '<pre data-line="' + line + '">' + html.slice(5);
    }
    if (html.startsWith('<hr')) {
      return html.replace('<hr', '<hr data-line="' + line + '"');
    }
    return html;
  };
}

// Wiki links, rendered as spans rather than anchors so that the click handler
// can decide whether the target exists.
const WIKI = /\[\[([^\[\]\n|]{1,200})(?:\|([^\[\]\n]{1,200}))?\]\]/g;
md.inline.ruler.before('link', 'marknest_wikilink', (state, silent) => {
  const start = state.pos;
  if (state.src.charCodeAt(start) !== 0x5b || state.src.charCodeAt(start + 1) !== 0x5b) {
    return false;
  }
  const slice = state.src.slice(start);
  WIKI.lastIndex = 0;
  const match = WIKI.exec(slice);
  if (!match || match.index !== 0) {
    return false;
  }
  if (!silent) {
    const token = state.push('marknest_wikilink', '', 0);
    token.content = match[1].trim();
    token.meta = { alias: (match[2] || '').trim() };
  }
  state.pos = start + match[0].length;
  return true;
});

md.renderer.rules.marknest_wikilink = (tokens, idx) => {
  const token = tokens[idx];
  const target = md.utils.escapeHtml(token.content);
  const label = md.utils.escapeHtml(token.meta.alias || token.content);
  return '<a class="wikilink" data-target="' + target + '" href="#">' + label + '</a>';
};

export function render(source) {
  // The sanitiser runs on the produced markup, not on the input, so it sees
  // exactly what would have been inserted into the page.
  return DOMPurify.sanitize(md.render(source || ''), {
    ADD_ATTR: ['data-line', 'data-target'],
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'style']
  });
}

/* ------------------------------------------------------------------ editor */

// Read-only is reconfigured rather than rebuilt: rebuilding the editor would
// discard the undo history, which is exactly the moment a person is most likely
// to want it - a note they have just discovered they cannot write to.
const readOnlyCompartment = new Compartment();

function buildExtensions(options) {
  const settings = options || {};
  const extensions = [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightActiveLine(),
    history(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    rectangularSelection(),
    crosshairCursor(),
    highlightSelectionMatches(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    markdown({ base: markdownLanguage }),
    EditorView.lineWrapping,
    readOnlyCompartment.of(EditorState.readOnly.of(!!settings.readOnly)),
    keymap.of([
      {
        key: 'Mod-s',
        preventDefault: true,
        run: () => {
          if (typeof settings.onSave === 'function') {
            settings.onSave();
          }
          return true;
        }
      },
      indentWithTab,
      ...searchKeymap,
      ...defaultKeymap,
      ...historyKeymap
    ]),
    EditorView.updateListener.of((update) => {
      if (update.docChanged && typeof settings.onChange === 'function') {
        settings.onChange(update.state.doc.toString());
      }
    })
  ];
  return extensions;
}

export function create(parent, options) {
  const settings = options || {};
  let saveHandler = settings.onSave;

  const state = EditorState.create({
    doc: settings.value || '',
    extensions: buildExtensions({
      onChange: settings.onChange,
      readOnly: settings.readOnly,
      onSave: () => {
        if (typeof saveHandler === 'function') {
          saveHandler();
        }
      }
    })
  });

  const view = new EditorView({ state, parent });

  return {
    view,

    getValue() {
      return view.state.doc.toString();
    },

    setValue(text, opts) {
      const keepScroll = opts && opts.preserveScroll;
      const top = keepScroll ? view.scrollDOM.scrollTop : 0;
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: text || '' },
        // Putting the cursor at the top keeps a restored note from scrolling
        // itself to wherever the previous one was last edited.
        selection: { anchor: 0 }
      });
      if (keepScroll) {
        view.scrollDOM.scrollTop = top;
      }
    },

    setReadOnly(flag) {
      view.dispatch({
        effects: readOnlyCompartment.reconfigure(EditorState.readOnly.of(!!flag))
      });
      view.dom.classList.toggle('is-readonly', !!flag);
    },

    setSaveHandler(fn) {
      saveHandler = fn;
    },

    focus() {
      view.focus();
    },

    destroy() {
      view.destroy();
    },

    scrollDOM: view.scrollDOM,

    /** The document line currently at the top of the viewport, 1-based. */
    getTopLine() {
      const block = view.lineBlockAtHeight(view.scrollDOM.scrollTop);
      return view.state.doc.lineAt(block.from).number;
    },

    /** Scroll so that a document line is at the top of the viewport. */
    scrollToLine(line) {
      const total = view.state.doc.lines;
      const target = Math.max(1, Math.min(line, total));
      const info = view.state.doc.line(target);
      const block = view.lineBlockAt(info.from);
      view.scrollDOM.scrollTop = block.top;
    }
  };
}
