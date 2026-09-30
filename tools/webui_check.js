/* Static + dynamic cross-check of the MarkNest WebUI.
 *
 * Loads every script into a minimal DOM stub, then verifies that each
 * cross-module call site (`UI.foo(...)`, `I18N.foo(...)`, `API.foo(...)`,
 * `PrintPage.foo(...)`, ...) resolves to a property the target module actually
 * exports. A typo such as `UI.apply` when only `I18N.apply` exists is caught
 * here instead of surfacing as a blank page inside the TOS iframe.
 *
 * Usage: node tools/webui_check.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.dirname(__dirname);
const WEBUI = path.join(REPO_ROOT, 'webui');

// The page's own script order, less the editor bundle. The two are compared
// mechanically further down: this list drives what is loaded here, the page
// drives what is loaded in the browser, and a module added to one and not the
// other loads in exactly one of them.
const ORDER = [
  'js/i18n.js',
  'js/ui.js',
  'js/mdcmd.js',
  'js/api.js',
  'js/toshost.js',
  'js/formatbar.js',
  'js/homepane.js',
  'js/treepane.js',
  'js/editorpane.js',
  'js/previewpane.js',
  'js/searchpane.js',
  'js/app.js'
];

// The editor bundle is deliberately NOT in ORDER. It is a third-party build
// that reaches for MutationObserver, ResizeObserver, getComputedStyle and
// requestAnimationFrame, none of which the DOM stub provides, so loading it
// here would fail for reasons that have nothing to do with this application.
// Its surface is declared instead and checked against the built file below.
const VENDOR = 'js/vendor.editor.js';
const VENDOR_SURFACE = ['create', 'render', 'applyEdit'];

/* --------------------------------------------------------------- DOM stub */

function makeElement(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    nodeType: 1,
    children: [],
    childNodes: [],
    attributes: {},
    style: {},
    dataset: {},
    className: '',
    textContent: '',
    innerHTML: '',
    hidden: false,
    value: '',
    checked: false,
    disabled: false,
    files: [],
    parentNode: null,
    firstChild: null,
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k); },
    removeAttribute(k) { delete this.attributes[k]; },
    appendChild(child) {
      this.children.push(child);
      this.childNodes.push(child);
      this.firstChild = this.childNodes[0] || null;
      if (child) { child.parentNode = this; }
      return child;
    },
    insertBefore(child) { return this.appendChild(child); },
    removeChild(child) {
      const i = this.childNodes.indexOf(child);
      if (i >= 0) { this.childNodes.splice(i, 1); this.children.splice(i, 1); }
      this.firstChild = this.childNodes[0] || null;
      return child;
    },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    focus() {},
    blur() {},
    click() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest() { return null; },
    contains() { return false; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
  };
  return el;
}

const documentStub = {
  readyState: 'complete',
  documentElement: makeElement('html'),
  body: makeElement('body'),
  hidden: false,
  createElement: makeElement,
  createTextNode(text) { return { nodeType: 3, textContent: String(text), parentNode: null }; },
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  removeEventListener() {}
};

const storage = {};
const localStorageStub = {
  getItem(k) { return Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null; },
  setItem(k, v) { storage[k] = String(v); },
  removeItem(k) { delete storage[k]; }
};

const sandbox = {
  console,
  document: documentStub,
  navigator: { languages: ['zh-CN', 'en-US'], language: 'zh-CN', userAgent: 'node' },
  localStorage: localStorageStub,
  location: {
    hash: '',
    href: 'http://localhost/marknest/',
    origin: 'http://localhost',
    protocol: 'http:',
    host: 'localhost',
    pathname: '/marknest/',
    search: '',
    replace() {},
    assign() {}
  },
  setTimeout,
  clearTimeout,
  setInterval() { return 1; },
  clearInterval() {},
  Promise,
  Object,
  Array,
  String,
  Number,
  Boolean,
  Math,
  JSON,
  Date,
  RegExp,
  Error,
  TypeError,
  isNaN,
  parseInt,
  parseFloat,
  encodeURIComponent,
  decodeURIComponent,
  XMLHttpRequest: function XMLHttpRequestStub() {
    this.upload = { addEventListener() {} };
    this.open = function () {};
    this.setRequestHeader = function () {};
    this.send = function () {};
    this.abort = function () {};
    this.addEventListener = function () {};
  },
  FormData: function FormDataStub() { this.append = function () {}; },
  URL: { createObjectURL() { return 'blob:x'; }, revokeObjectURL() {} },
  Blob: function BlobStub() {},
  alert() {},
  confirm() { return true; }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

const context = vm.createContext(sandbox);

/* ------------------------------------------------------------- load files */

const loaded = [];
const loadErrors = [];

for (const rel of ORDER) {
  const file = path.join(WEBUI, rel);
  if (!fs.existsSync(file)) {
    loadErrors.push(`${rel}: file missing`);
    continue;
  }
  const code = fs.readFileSync(file, 'utf8');
  try {
    vm.runInContext(code, context, { filename: rel });
    loaded.push(rel);
  } catch (error) {
    loadErrors.push(`${rel}: ${error.message}`);
  }
}

/* -------------------------------------------------------- collect exports */

const MODULES = {};
for (const name of ['UI', 'I18N', 'MDCmd', 'FormatBar', 'HomePane', 'API',
                    'TreePane', 'EditorPane', 'PreviewPane', 'SearchPane', 'App',
                    'TosHost']) {
  const value = sandbox[name];
  if (value && (typeof value === 'object' || typeof value === 'function')) {
    MODULES[name] = new Set(Object.keys(value));
  }
}
// Declared rather than observed, because the bundle is not executed here.
MODULES.MDEditor = new Set(VENDOR_SURFACE);

/* -------------------------------------------------- i18n key set parity */

/* A key present in one dictionary but missing in another does not fail loudly:
 * translate() falls back to the default language, so an English sentence simply
 * appears inside the Chinese interface. That is exactly the reported
 * "cups-client is not installed" leak, and a near miss of it was produced while
 * adding the CUPS remedy line - so the key sets are compared mechanically
 * instead of by eye. */
const i18nProblems = [];
const i18nTables = (sandbox.I18N && sandbox.I18N.tables) || null;
if (!i18nTables) {
  i18nProblems.push('I18N.tables is not exposed - key parity cannot be verified');
} else {
  const languages = Object.keys(i18nTables);
  const union = new Set();
  for (const lang of languages) {
    for (const key of Object.keys(i18nTables[lang] || {})) { union.add(key); }
  }
  for (const lang of languages) {
    const table = i18nTables[lang] || {};
    const missing = [...union].filter((key) => !(key in table));
    if (missing.length) {
      i18nProblems.push(
        `${lang} is missing ${missing.length} key(s): ` +
        missing.slice(0, 8).join(', ') + (missing.length > 8 ? ' ...' : '')
      );
    }
  }
  if (!i18nProblems.length) {
    console.log(`i18n key parity: ${languages.length} dictionaries x ${union.size} keys - identical`);
  }
}

/* ------------------------------------------------- scan call sites for typos */

const ALLOWED_GLOBALS = new Set([
  'UI', 'I18N', 'MDCmd', 'FormatBar', 'HomePane', 'API', 'TreePane', 'EditorPane',
  'PreviewPane', 'SearchPane', 'App', 'TosHost', 'MDEditor',
  'window', 'document', 'navigator', 'localStorage', 'console', 'Math', 'JSON',
  'Object', 'Array', 'String', 'Number', 'Boolean', 'Date', 'RegExp', 'Promise',
  'Error', 'TypeError', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'XMLHttpRequest', 'FormData', 'URL', 'Blob'
]);

const callPattern = /\b([A-Z][A-Za-z0-9_]*)\.([A-Za-z_$][A-Za-z0-9_$]*)\s*\(/g;
const propertyPattern = /\b([A-Z][A-Za-z0-9_]*)\.([A-Za-z_$][A-Za-z0-9_$]*)\b(?!\s*\()/g;

const problems = [];
const seen = new Set();

for (const rel of loaded) {
  const code = fs.readFileSync(path.join(WEBUI, rel), 'utf8');
  const lines = code.split('\n');
  lines.forEach((line, index) => {
    // Ignore comment-only lines so prose mentioning UI.foo does not warn.
    const trimmed = line.trim();
    if (trimmed.startsWith('*') || trimmed.startsWith('//') || trimmed.startsWith('/*')) {
      return;
    }
    let match;
    const scan = (pattern) => {
      pattern.lastIndex = 0;
      while ((match = pattern.exec(line)) !== null) {
        const [, moduleName, member] = match;
        if (!ALLOWED_GLOBALS.has(moduleName)) { continue; }
        if (!MODULES[moduleName]) { continue; }
        const key = `${moduleName}.${member}`;
        if (seen.has(key)) { continue; }
        seen.add(key);
        if (!MODULES[moduleName].has(member)) {
          problems.push(`${rel}:${index + 1}  ${moduleName}.${member} is not exported  ->  ${trimmed}`);
        }
      }
    };
    scan(callPattern);
    scan(propertyPattern);
  });
}

/* --------------------------------------------------- required member audit */

/* The names below mirror the surface each module really exports. Keep them in
 * sync with the `global.<Module> = {...}` literals at the bottom of each file:
 * a list that is guessed rather than read produces false failures such as
 * `API.print`, which never existed (the frontend wrapper is `submitPrint`)
 * and `API.getJobStats`, which never existed (statistics arrive inside the
 * `stats` field of `GET /jobs`). */
const REQUIRED = {
  UI: ['el', 'clear', 'show', 'hide', 'toast', 'loading', 'empty', 'errorBox',
       'hintNode', 'skeleton', 'badge', 'statusBadge', 'formatBytes',
       'formatDateTime', 'escapeHtml', 'debounce'],
  I18N: ['t', 'errorText', 'apply', 'setLanguage', 'getLanguage', 'detect',
         'supported'],
  API: ['getHealth', 'getOptions', 'getMe', 'getTree', 'getNote', 'saveNote',
        'createNote', 'renameNote', 'deleteNote', 'getRecent', 'search',
        'indexStatus', 'indexScan'],
  FormatBar: ['init', 'render', 'setEnabled'],
  HomePane: ['init', 'reload', 'render'],
  TreePane: ['init', 'reload', 'refresh', 'newNote', 'setCurrent', 'render',
             'current'],
  EditorPane: ['init', 'open', 'save', 'isDirty', 'currentPath', 'editor'],
  PreviewPane: ['init', 'render', 'schedule', 'setEnabled'],
  SearchPane: ['init', 'run', 'exit', 'isActive'],
  TosHost: ['canOpenSharedFolders', 'openSharedFolders'],
  App: ['boot', 'health', 'openNote']
};

const missingRequired = [];
for (const [moduleName, members] of Object.entries(REQUIRED)) {
  if (!MODULES[moduleName]) {
    missingRequired.push(`${moduleName}: module not exposed on window`);
    continue;
  }
  for (const member of members) {
    if (!MODULES[moduleName].has(member)) {
      missingRequired.push(`${moduleName}.${member} missing`);
    }
  }
}

/* ------------------------------------- ORDER and index.html must agree */

/* The two lists have to be identical, item for item, and until now nothing
 * said so. A module added to one and not the other fails quietly in exactly
 * one of the two places that matter: it loads in this harness - which is driven
 * by ORDER - and never reaches the browser, or it loads in the browser and is
 * never cross-checked here. That is the "committed artefact is quietly stale"
 * failure this repository has already been bitten by, so the comparison is
 * mechanical rather than a sentence in a plan document.
 *
 * The editor bundle is dropped from the page's list for the same reason it is
 * absent from ORDER (see the note above): it is a third-party build this
 * sandbox cannot execute. Every other tag must match by position, and the
 * first divergence is reported by index and by name.
 *
 * Comments are stripped before scanning. A commented-out tag is still a tag to
 * a regex, so `<!-- <script src="js/mdcmd.js"></script> -->` would satisfy a
 * check whose whole purpose is to notice a script that does not load - the
 * one silent way this can be wrong. A single-quoted attribute is the other,
 * and it is left alone deliberately: it fails loudly at position 0, which is
 * the safe direction. */
const orderProblems = [];
const INDEX_HTML = path.join(WEBUI, 'index.html');
if (!fs.existsSync(INDEX_HTML)) {
  orderProblems.push('webui/index.html is missing - the script order cannot be verified');
} else {
  const raw = fs.readFileSync(INDEX_HTML, 'utf8');
  const html = raw.replace(/<!--[\s\S]*?-->/g, '');
  const fromPage = [];
  const tagPattern = /<script\b[^>]*\bsrc="([^"]+)"/g;
  let tag;
  while ((tag = tagPattern.exec(html)) !== null) {
    // The ?v= cache buster is a release-time literal, not part of the path.
    const src = tag[1].split('?')[0];
    if (src !== VENDOR) {
      fromPage.push(src);
    }
  }
  const positions = Math.max(fromPage.length, ORDER.length);
  for (let i = 0; i < positions; i += 1) {
    if (fromPage[i] !== ORDER[i]) {
      orderProblems.push(
        `position ${i}: index.html loads ${JSON.stringify(fromPage[i] || null)}, ` +
        `ORDER has ${JSON.stringify(ORDER[i] || null)}`);
      break;
    }
  }
}

/* ------------------------------------------------- markdown command audit */

/* The commands are pure functions, so their output can be asserted here rather
 * than in a browser - which matters because the fiddly parts (toggle-off,
 * where the cursor lands with no selection) are exactly the parts a browser
 * test would exercise only by accident. */
const cmdProblems = [];
const CMD = sandbox.MDCmd;
if (!CMD) {
  cmdProblems.push('MDCmd is not exposed on window');
} else {
  const cases = [
    // [label, command, ctx, expected substring in the inserted text,
    //  optional substring that must NOT appear]
    ['bold wraps a selection', 'bold',
      { doc: 'hello', from: 0, to: 5, selected: 'hello' }, '**hello**'],
    ['bold on bare cursor inserts the markers', 'bold',
      { doc: '', from: 0, to: 0, selected: '' }, '****'],
    ['italic wraps a selection', 'italic',
      { doc: 'hi', from: 0, to: 2, selected: 'hi' }, '*hi*'],
    // `wrap`'s unwrap branch - the selection itself already carries the markers.
    // The corrected toggle loop no longer reaches it, because its second press
    // hands over the inner text rather than the wrapped result, so the direct
    // gesture is asserted here. The forbidden term is what makes it bite:
    // 'text' is also a substring of the '****text****' a missing branch returns.
    ['bold unwraps a selection that already has the markers', 'bold',
      { doc: '**text**', from: 0, to: 8, selected: '**text**' }, 'text', '**'],
    ['inline code wraps a selection', 'code',
      { doc: 'x', from: 0, to: 1, selected: 'x' }, '`x`'],
    ['a code block gets a fenced body', 'codeblock',
      { doc: '', from: 0, to: 0, selected: '' }, '```\n\n```'],
    ['a quote prefixes the line', 'quote',
      { doc: 'line', from: 0, to: 0, selected: '' }, '> line'],
    ['h1 prefixes the line', 'h1',
      { doc: 'line', from: 0, to: 0, selected: '' }, '# line'],
    ['h2 prefixes the line', 'h2',
      { doc: 'line', from: 0, to: 0, selected: '' }, '## line'],
    ['h3 prefixes the line', 'h3',
      { doc: 'line', from: 0, to: 0, selected: '' }, '### line'],
    ['a task item prefixes the line', 'task',
      { doc: 'todo', from: 0, to: 0, selected: '' }, '- [ ] todo'],
    ['a bullet prefixes the line', 'bullet',
      { doc: 'item', from: 0, to: 0, selected: '' }, '- item'],
    ['a numbered item prefixes the line', 'numbered',
      { doc: 'item', from: 0, to: 0, selected: '' }, '1. item'],
    ['a table is three columns wide', 'table',
      { doc: '', from: 0, to: 0, selected: '' }, '| --- | --- | --- |'],
    // Multi-line: a line-start command covers every line the selection
    // touches, not just the first. Asserting only a single-line line would
    // pass for an implementation that prefixed the block once.
    ['quote covers every selected line', 'quote',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '> a\n> b'],
    ['h1 covers every selected line', 'h1',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '# a\n# b'],
    ['h2 covers every selected line', 'h2',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '## a\n## b'],
    ['h3 covers every selected line', 'h3',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '### a\n### b'],
    ['task covers every selected line', 'task',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '- [ ] a\n- [ ] b'],
    ['bullet covers every selected line', 'bullet',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '- a\n- b'],
    ['numbered covers every selected line', 'numbered',
      { doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' }, '1. a\n1. b'],
    // A block where only some lines carry the marker is the case where the
    // all-or-nothing rule and a treat-the-block-as-one-line implementation
    // actually disagree: the latter sees the block begin with the marker,
    // concludes it is already quoted, and strips instead of adding.
    ['quote adds to the lines that lack it', 'quote',
      { doc: '> a\nb', from: 0, to: 5, selected: '> a\nb' }, '> a\n> b'],
    // A blank line is skipped inside a block, but an all-blank block is the
    // place someone starts a construct: the cursor is there, and pressing the
    // button has to do something.
    ['a quote starts on an empty line', 'quote',
      { doc: '', from: 0, to: 0, selected: '' }, '> '],
    // The other direction, so the blank-line rule cannot quietly disappear.
    ['a blank line inside the block is left alone', 'bullet',
      { doc: 'a\n\nb', from: 0, to: 4, selected: 'a\n\nb' }, '- a\n\n- b'],
    // The heading transform has its own copy of the all-blank rule, so an
    // assertion on quote alone would not notice if this one were dropped.
    ['a heading starts on an empty line', 'h1',
      { doc: '', from: 0, to: 0, selected: '' }, '# '],
    // A fenced block has to start on its own line, or the opening fence is
    // inline text and the closing one opens a block that swallows the note.
    ['a code block starts on its own line', 'codeblock',
      { doc: 'abc', from: 3, to: 3, selected: '' }, '\n```\n\n```'],
    // The with-selection branch, whole insertion compared so the leading and
    // trailing newlines are both pinned - the same reason the table case does.
    ['a code block around a selection is fenced on its own lines', 'codeblock',
      { doc: 'xwordy', from: 1, to: 5, selected: 'word' }, '\n```\nword\n```\n'],
    // A table has to end its own line for the same reason a fence does: the
    // text after the caret would otherwise glue onto the last row. The caret is
    // mid-word on purpose - at the end of the document the tail is empty and
    // the insertion is byte-identical with or without it, so an assertion there
    // would pin the lead and never the tail. The whole insertion is compared.
    ['a table starts and ends on its own line', 'table',
      { doc: 'abc', from: 1, to: 1, selected: '' },
      '\n|  |  |  |\n| --- | --- | --- |\n|  |  |  |\n'],
    // The checked marker is a distinct prefix: without it a checked item is not
    // recognised as a task at all, and comes back as '- [ ] - [x] done'.
    ['a task item removes a checked marker', 'task',
      { doc: '- [x] done', from: 0, to: 10, selected: '' }, 'done', '[x]'],
    // bullet must recognise a task item as an unordered item and remove the
    // whole marker. A substring check alone cannot see this: 'buy milk' IS a
    // substring of the broken '[ ] buy milk', so the case needs a forbidden
    // term as well.
    ['bullet removes a whole task marker', 'bullet',
      { doc: '- [ ] buy milk', from: 0, to: 14, selected: '' }, 'buy milk', '[ ]']
  ];
  for (const [label, name, ctx, expected, forbidden] of cases) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { cmdProblems.push(`${label}: MDCmd.commands.${name} is not a function`); continue; }
    const result = fn(ctx);
    const text = result && result.changes && typeof result.changes.insert === 'string'
      ? result.changes.insert : '';
    if (text.indexOf(expected) === -1) {
      cmdProblems.push(`${label}: expected ${JSON.stringify(expected)} inside ${JSON.stringify(text)}`);
    } else if (forbidden && text.indexOf(forbidden) !== -1) {
      cmdProblems.push(`${label}: ${JSON.stringify(forbidden)} should not appear in ${JSON.stringify(text)}`);
    }
  }
  // Toggle-off: applying the same command twice must return the document to
  // where it started. This is the rule that is easiest to implement for half
  // the buttons and forget for the other half.
  //
  // Ten of the thirteen commands are covered here. codeblock, link and table
  // are insert-only by design rather than by omission: the design spec's rows
  // for those three describe what they insert and never say the marker is
  // cancelled when it is already there, unlike the rows for quote, the headings
  // and the three list commands. Fence or link detection must not be added to
  // close that gap.
  for (const name of ['bold', 'italic', 'code', 'quote', 'h1', 'h2', 'h3', 'task', 'bullet', 'numbered']) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { continue; }
    const once = fn({ doc: 'text', from: 0, to: 4, selected: 'text' });
    const applied = once.changes.insert;
    // The second press must act on what the first press actually left selected:
    // that is the selection a person's cursor is sitting in. Re-selecting the
    // whole result by hand tests a round trip nobody performs, and passes even
    // when the command returns a garbage selection.
    const twice = fn({ doc: applied, from: once.selection.anchor, to: once.selection.head,
                       selected: applied.slice(once.selection.anchor, once.selection.head) });
    if (twice.changes.insert !== 'text') {
      cmdProblems.push(`toggle-off: ${name} produced ${JSON.stringify(twice.changes.insert)} on the second press`);
    }
  }
  // The same rule in the remove direction, over more than one line.
  for (const name of ['quote', 'h1', 'bullet', 'task']) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { continue; }
    const once = fn({ doc: 'a\nb', from: 0, to: 3, selected: 'a\nb' });
    const applied = once.changes.insert;
    // The second press acts on the selection the first press returned, for the
    // same reason as above - and here it is also what catches a block-wide
    // endpoint shift, which puts the selection on the tail of the block instead
    // of over all of it.
    const twice = fn({ doc: applied, from: once.selection.anchor, to: once.selection.head,
                       selected: applied.slice(once.selection.anchor, once.selection.head) });
    if (twice.changes.insert !== 'a\nb') {
      cmdProblems.push(`multi-line toggle-off: ${name} produced ${JSON.stringify(twice.changes.insert)} on the second press`);
    }
  }
  // The loop above only ever selects a whole block, so its second press starts
  // from a selection that already covers everything the first press wrote. A
  // person often selects part of a marked block instead, and that is where the
  // endpoint arithmetic was at its most fragile: an endpoint landing inside the
  // span its own line had just removed was counted that line's whole growth,
  // leaving the selection short, collapsed onto a caret, or - for `numbered`
  // over two ordered items - inverted. Pressing twice has to give the document
  // back whatever was selected the first time.
  const partials = [
    ['quote', '> a\n> b', 0, 5],
    ['quote', '> a\n> b', 1, 4],
    ['task', '- [ ] a\n- [ ] b', 0, 10],
    ['bullet', '- a\n- b', 1, 4],
    ['numbered', '1. a\n1. b', 4, 6]
  ];
  for (const [name, doc, from, to] of partials) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { continue; }
    const once = fn({ doc: doc, from: from, to: to, selected: doc.slice(from, to) });
    const applied = once.changes.insert;
    if (once.selection.anchor > once.selection.head) {
      cmdProblems.push(
        `partial-selection toggle: ${name} returned an inverted selection ${JSON.stringify(once.selection)}`);
      continue;
    }
    const twice = fn({ doc: applied, from: once.selection.anchor, to: once.selection.head,
                       selected: applied.slice(once.selection.anchor, once.selection.head) });
    const restored = applied.slice(0, twice.changes.from) + twice.changes.insert +
      applied.slice(twice.changes.to);
    if (restored !== doc) {
      cmdProblems.push(
        `partial-selection toggle: ${name} on ${JSON.stringify(doc)} ${from}..${to} became ` +
        `${JSON.stringify(restored)}`);
    }
  }
  // The all-blank block, in both directions. Neither toggle loop above can
  // reach it: both start from a document with text in it. Pressing quote on an
  // empty note has to put the marker where the cursor is, and pressing it again
  // has to take the marker away rather than leaving a stray '> ' behind.
  const emptyQuote = CMD.commands && CMD.commands.quote;
  if (typeof emptyQuote === 'function') {
    const opened = emptyQuote({ doc: '', from: 0, to: 0, selected: '' }).changes.insert;
    if (opened !== '> ') {
      cmdProblems.push(`quote on an empty document produced ${JSON.stringify(opened)} instead of '> '`);
    } else {
      const closed = emptyQuote({ doc: opened, from: opened.length, to: opened.length, selected: '' })
        .changes.insert;
      if (closed !== '') {
        cmdProblems.push(`quote on '> ' produced ${JSON.stringify(closed)} instead of ''`);
      }
    }
  }
  // The leading-newline inputs cannot be asserted through `cases`. For an
  // insertion at the cursor the inserted text is the marker alone - identical
  // both before and after the fix - so the substring check is blind to what
  // went wrong, which is where the change starts. `lastIndexOf('\n', -1)`
  // clamps its negative index to 0 in JavaScript, so a document whose first
  // character is a newline matched that newline and began the block one
  // character in: the empty first line was skipped, and with the cursor at
  // offset 0 the range came back inverted, which CodeMirror rejects outright.
  // The resulting document and the range are asserted directly instead.
  const blockFn = CMD.commands && CMD.commands.quote;
  if (typeof blockFn === 'function') {
    const leading = [
      ['a leading newline does not shift the block', '\nx'],
      ['an all-newline document still gets a marker', '\n\n']
    ];
    for (const [label, doc] of leading) {
      const change = blockFn({ doc: doc, from: 0, to: 0, selected: '' }).changes;
      if (change.from > change.to) {
        cmdProblems.push(`${label}: inverted range, from ${change.from} to ${change.to}`);
        continue;
      }
      const result = doc.slice(0, change.from) + change.insert + doc.slice(change.to);
      if (result !== '> ' + doc) {
        cmdProblems.push(
          `${label}: document became ${JSON.stringify(result)} instead of ${JSON.stringify('> ' + doc)}`);
      }
    }
  }
  // A caret is the one case where both endpoints still shift by the whole block
  // delta rather than per line, so the cursor lands after the marker it just
  // inserted instead of in front of it. Nothing else here covers it: both toggle
  // loops start from a selection, and the round-trip above reads insert only.
  const caretQuote = CMD.commands && CMD.commands.quote;
  if (typeof caretQuote === 'function') {
    const caret = caretQuote({ doc: 'line', from: 0, to: 0, selected: '' });
    if (caret.changes.insert !== '> line') {
      cmdProblems.push(`quote with a caret inserted ${JSON.stringify(caret.changes.insert)}`);
    } else if (caret.selection.anchor !== 2 || caret.selection.head !== 2) {
      cmdProblems.push(
        `quote with a caret left it at ${caret.selection.anchor}, not after the inserted marker`);
    }
  }
  // link is the one command that takes arguments beyond ctx, so it is asserted
  // separately. The design requires the URL portion to come back selected, so
  // the person can retype the address without selecting it by hand - a
  // behaviour nothing else here would notice going missing.
  const linkFn = CMD.commands && CMD.commands.link;
  if (typeof linkFn !== 'function') {
    cmdProblems.push('link is not a function');
  } else {
    const url = 'https://x';
    const wrapped = linkFn({ doc: 'abc', from: 0, to: 3, selected: 'abc' }, url);
    const inserted = wrapped.changes.insert;
    if (inserted !== '[abc](' + url + ')') {
      cmdProblems.push(`link with a selection inserted ${JSON.stringify(inserted)}`);
    } else {
      // Slicing the inserted text by the returned selection is the assertion:
      // it fails unless the selection really spans the URL.
      const picked = inserted.slice(wrapped.selection.anchor, wrapped.selection.head);
      if (picked !== url) {
        cmdProblems.push(
          `link did not select the URL: ${JSON.stringify(wrapped.selection)} picks ${JSON.stringify(picked)}`);
      }
    }
    const labelled = linkFn({ doc: '', from: 0, to: 0, selected: '' }, url, 'Text');
    const labelledInsert = labelled.changes.insert;
    if (labelledInsert !== '[Text](' + url + ')') {
      cmdProblems.push(`link without a selection inserted ${JSON.stringify(labelledInsert)}`);
    } else {
      // Asserted here too, not only in the with-selection case above: both
      // callers are promised a URL they can retype without selecting it.
      const labelledPicked = labelledInsert.slice(labelled.selection.anchor, labelled.selection.head);
      if (labelledPicked !== url) {
        cmdProblems.push(
          `link without a selection did not select the URL: ` +
          `${JSON.stringify(labelled.selection)} picks ${JSON.stringify(labelledPicked)}`);
      }
    }
  }
}

/* --------------------------------------------------------- vendor bundle */

/* The matcher is built here, once, and the decoy assertions below call this
 * function rather than restating the pattern. A copy would let the tests keep
 * passing while the checker they describe had drifted - which is the failure
 * they exist to rule out. */
function exportedNamePattern(member) {
  // The minifier emits one of three shapes depending on how the literal
  // survives: an object-literal property (`{ render: fn }`), an assignment
  // (`X.render = fn`), or a method in an object literal
  // (`applyEdit(command) { ... }`). All three are accepted rather than pinning
  // one, because which one appears is a property of the bundler version and
  // not of the application.
  //
  // The third shape is the only one an *instance* method can take. `create`
  // and `render` reach the module namespace and so are emitted as assignments,
  // but `applyEdit` is returned from `create()` and never leaves the object
  // literal. Its leading character is pinned to `{` or `,` - the two that can
  // precede an object-literal method in the emitted bundle - because a `\s`
  // there would also admit a call site followed by a block, a standalone
  // function declaration, or a comment. The brace after the parameter list is
  // required for the same reason: a bare call must not satisfy the check.
  //
  // Two limitations are known and accepted. The `{` lead still admits a class
  // method (`class Foo{applyEdit(a){}}`), and it cannot be dropped, because an
  // object literal whose first member is the method begins `return{applyEdit(o){`.
  // And this is a text-presence test even for the module exports: deleting
  // `Ur.create=jP` alone would still pass, since unrelated `.create=`
  // occurrences satisfy the first alternative. Pinning the minified emission
  // line would be more fragile than the gap it closes.
  return new RegExp(
    '[.\\s{;,]' + member + '\\s*[:=]' +
    '|[{,]' + member + '\\s*\\([^)]*\\)\\s*\\{'
  );
}

/* The editor bundle is a committed build artefact, so the two ways it can be
 * wrong are "not built" and "built from older sources". The second is caught by
 * the source hash in tools/webui_build.py; this catches the first, and checks
 * that the surface the rest of the WebUI calls actually exists. */
const vendorProblems = [];
const vendorPath = path.join(WEBUI, VENDOR);
if (!fs.existsSync(vendorPath)) {
  vendorProblems.push(`${VENDOR} is missing - run: python tools/webui_build.py`);
} else {
  const bundle = fs.readFileSync(vendorPath, 'utf8');
  for (const member of VENDOR_SURFACE) {
    if (!exportedNamePattern(member).test(bundle)) {
      vendorProblems.push(`${VENDOR} does not appear to export ${member}`);
    }
  }
  if (!/MDEditor/.test(bundle)) {
    vendorProblems.push(`${VENDOR} does not define the MDEditor global`);
  }

  /* Every assertion above runs against the real bundle, which contains the
   * real export - so a matcher that accepts everything passes all of them.
   * The widened object-literal form was exactly that loose once, and a person
   * reading the regex found it while nothing here did. These cases pin the
   * discrimination itself, in both directions: a matcher that rejects
   * everything fails the last one. */
  const DECOYS = [
    'view.applyEdit(s)\n{}',
    'function applyEdit(a){}',
    '/* obj.applyEdit(x){ */',
    '// obj.applyEdit(x){',
    '"obj.applyEdit(x){"'
  ];
  for (const decoy of DECOYS) {
    if (exportedNamePattern('applyEdit').test(decoy)) {
      vendorProblems.push(
        `the surface matcher accepts a decoy: ${JSON.stringify(decoy)}`
      );
    }
  }
  if (!exportedNamePattern('applyEdit').test('return{view:s,applyEdit(o){c}')) {
    vendorProblems.push('the surface matcher rejects the real emission shape');
  }
}

/* ------------------------------------------------------------------ report */

console.log('WebUI cross-module check');
console.log('='.repeat(62));
console.log('scripts loaded : ' + loaded.length + '/' + ORDER.length);
for (const rel of loaded) { console.log('  ok   ' + rel); }
for (const item of loadErrors) { console.log('  FAIL ' + item); }

console.log('');
console.log('modules exposed: ' + Object.keys(MODULES).join(', '));

console.log('');
console.log('cross-module call sites checked: ' + seen.size);
for (const item of problems) { console.log('  [ERROR] ' + item); }

console.log('');
console.log('required API surface:');
for (const item of missingRequired) { console.log('  [ERROR] ' + item); }

console.log('');
console.log('script order (ORDER vs index.html):');
for (const item of orderProblems) { console.log('  [ERROR] ' + item); }
if (!orderProblems.length) { console.log('  ok   index.html loads the same scripts, in the same order, as ORDER'); }

console.log('');
console.log('i18n key parity:');
for (const item of i18nProblems) { console.log('  [ERROR] ' + item); }
if (!i18nProblems.length) { console.log('  ok   every dictionary defines the same keys'); }

console.log('');
console.log('markdown commands:');
for (const item of cmdProblems) { console.log('  [ERROR] ' + item); }
if (!cmdProblems.length) { console.log('  ok   every command produces the expected markdown; the ten toggleable ones toggle off'); }

console.log('');
console.log('editor bundle:');
for (const item of vendorProblems) { console.log('  [ERROR] ' + item); }
if (!vendorProblems.length) { console.log('  ok   built, and exports its declared surface'); }

const errorCount =
  loadErrors.length + problems.length + missingRequired.length + i18nProblems.length +
  vendorProblems.length + cmdProblems.length + orderProblems.length;
console.log('');
console.log('-'.repeat(62));
console.log('errors: ' + errorCount);
console.log(errorCount === 0
  ? 'RESULT: PASSED - every cross-module reference resolves.'
  : 'RESULT: FAILED');

process.exit(errorCount === 0 ? 0 : 1);
