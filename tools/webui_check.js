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

const ORDER = [
  'js/i18n.js',
  'js/ui.js',
  'js/api.js',
  'js/toshost.js',
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
for (const name of ['UI', 'I18N', 'API', 'TreePane', 'EditorPane', 'PreviewPane',
                    'SearchPane', 'App', 'TosHost']) {
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
  'UI', 'I18N', 'API', 'TreePane', 'EditorPane', 'PreviewPane', 'SearchPane',
  'App', 'TosHost', 'MDEditor',
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
        'createNote', 'renameNote', 'deleteNote', 'search', 'indexStatus',
        'indexScan'],
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

/* --------------------------------------------------------- vendor bundle */

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
    // The minifier emits one of three shapes depending on how the literal
    // survives: an object-literal property (`{ render: fn }`), an assignment
    // (`X.render = fn`), or a method in an object literal
    // (`applyEdit(command) { ... }`). All three are accepted rather than
    // pinning one, because which one appears is a property of the bundler
    // version and not of the application.
    //
    // The third shape is the only one an *instance* method can take. `create`
    // and `render` reach the module namespace and so are emitted as
    // assignments, but `applyEdit` is returned from `create()` and never
    // leaves the object literal. Requiring the brace after the parameter list
    // is what keeps this from being satisfied by a mere call site such as
    // `view.applyEdit(state)`.
    const exported = new RegExp(
      '[.\\s{;,]' + member + '\\s*[:=]' +
      '|[.\\s{;,]' + member + '\\s*\\([^)]*\\)\\s*\\{'
    );
    if (!exported.test(bundle)) {
      vendorProblems.push(`${VENDOR} does not appear to export ${member}`);
    }
  }
  if (!/MDEditor/.test(bundle)) {
    vendorProblems.push(`${VENDOR} does not define the MDEditor global`);
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
console.log('i18n key parity:');
for (const item of i18nProblems) { console.log('  [ERROR] ' + item); }
if (!i18nProblems.length) { console.log('  ok   every dictionary defines the same keys'); }

console.log('');
console.log('editor bundle:');
for (const item of vendorProblems) { console.log('  [ERROR] ' + item); }
if (!vendorProblems.length) { console.log('  ok   built, and exports its declared surface'); }

const errorCount =
  loadErrors.length + problems.length + missingRequired.length + i18nProblems.length +
  vendorProblems.length;
console.log('');
console.log('-'.repeat(62));
console.log('errors: ' + errorCount);
console.log(errorCount === 0
  ? 'RESULT: PASSED - every cross-module reference resolves.'
  : 'RESULT: FAILED');

process.exit(errorCount === 0 ? 0 : 1);
