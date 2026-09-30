# MarkNest 主页与格式工具栏 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 MarkNest 加一个起始页（打开文件 / 新建文件 / 最近文件），给编辑器加一条 13 个按钮的 Markdown 格式工具栏。

**Architecture:** 视图从一个「三栏」变成两个状态（`home` / `note`），由「有没有打开笔记」推出，不额外存状态。格式工具栏的 Markdown 改写逻辑做成**纯函数**（输入 文档+选区，输出 变更+新选区），放在 `FormatBar.commands` 上，因此可以在 `webui_check.js` 里静态断言而不用起浏览器；按钮只是把这些纯函数接到 CodeMirror 的 transaction 上。后端只新增一个 `GET /recent`，复用现有索引表。

**Tech Stack:** Python 3.10 标准库（后端）、原生 JS IIFE 模块（前端）、CodeMirror 6（经 Vite 预构建为 `webui/js/vendor.editor.js`）、Playwright（浏览器验证）。

**规格来源：** `docs/superpowers/specs/2026-09-30-marknest-home-and-format-toolbar-design.md`

**约定的工作目录：** 下文所有路径相对仓库根 `2-AI 开发应用/marknest/`。

---

## 文件结构

| 文件 | 职责 | 状态 |
|---|---|---|
| `usr/local/marknest/lib/db.py` | 加 `IndexStore.recent()` —— 一条 SQL | 改 |
| `usr/local/marknest/lib/api.py` | 加 `GET /recent` 路由 | 改 |
| `webui-src/editor/index.js` | 编辑器控制器加 `applyEdit()` —— 唯一能安全改文档的入口 | 改 |
| `webui/js/vendor.editor.js` | 由上者重新构建 | 产物 |
| `webui/js/mdcmd.js` | **纯函数**：13 个 Markdown 改写命令，无 DOM 无编辑器依赖 | 新 |
| `webui/js/homepane.js` | 主页渲染 + 最近文件列表 | 新 |
| `webui/js/formatbar.js` | 把 `mdcmd` 的命令接到编辑器上，渲染按钮 | 新 |
| `webui/js/filepicker.js` | 「打开文件」弹层：两个页签（笔记库 / 本机文件） | 新 |
| `webui/js/editorpane.js` | 暴露 `applyCommand()` 给格式栏 | 改 |
| `webui/js/app.js` | 视图状态机、☰ 菜单、路由、导入流程 | 改 |
| `webui/index.html` | ☰、主页容器、格式工具栏容器、文件选择弹层 | 改 |
| `webui/css/style.css` | 上述样式 | 改 |
| `webui/js/api.js` | `getRecent()` | 改 |
| `webui/js/i18n.js` | 新增文案（三语言） | 改 |
| `tools/webui_check.js` | 注册新模块 + 断言 Markdown 命令 | 改 |
| `tools/verify_editor.py` | 主页、菜单、导入的端到端断言 | 改 |
| `tools/measure_topbar.py` | 新控件纳入零相交扫描 | 改 |

**为什么 `mdcmd.js` 与 `formatbar.js` 分开：** 命令是纯函数（字符串进、变更出），能脱离浏览器直接断言；按钮连接需要编辑器实例。混在一起就只能起浏览器才能测，而这一版最容易出错的地方恰恰是命令本身（切换语义、无选区时的光标位置）。

## 脚本加载顺序（唯一约定，改任何一处都要同步另一处）

`webui/index.html` 的 `<script>` 顺序与 `tools/webui_check.js` 的 `ORDER` 数组**必须逐项一致**——后者是把前者加载进 DOM stub 做静态校验的，顺序分叉会让校验结果失去意义。后者不含 `vendor.editor.js`（那是个不执行的第三方 bundle）。

**本计划完成后的最终顺序：**

```
i18n · ui · mdcmd · api · toshost · [vendor.editor] · formatbar · homepane
     · filepicker · treepane · editorpane · previewpane · searchpane · app
```

新增的四个模块都插在 `toshost` 与 `treepane` 之间（`mdcmd` 插在 `ui` 之后），四个任务各加一个，互不冲突。

---

## Task 1: 后端 —— `IndexStore.recent()`

**Files:**
- Modify: `usr/local/marknest/lib/db.py`
- Test: `tools/selftest.py`

- [ ] **Step 1: 写失败的断言**

在 `tools/selftest.py` 的 `test_index_freshness()` 之后加一个新函数：

```python
def test_recent():
    print("\n8b. Recent notes come from the index, newest first, own user only")
    library.create_note(USER, "r/old.md", "# Old\n")
    index.scan(USER, force=True)
    # mtime granularity can be coarse; nudge the clock so the order is real.
    time.sleep(0.02)
    library.create_note(USER, "r/new.md", "# New\n")
    index.scan(USER, force=True)
    library.create_note(OTHER, "r/other.md", "# Other\n")
    index.scan(OTHER, force=True)

    rows = db.store.recent(USER, 10)
    paths = [row["path"] for row in rows]
    check("the newest note comes first", paths and paths[0] == "r/new.md", paths)
    check("an older note follows", "r/old.md" in paths, paths)
    # Isolation is asserted by naming the other user's note, not by a prefix
    # test: `all(p.startswith("r/"))` is true for bob's "r/other.md" as well, so
    # it would pass even with the `user = ?` filter removed. Bob's note is also
    # created last, so a missing filter puts it first and this catches it.
    check("another user's note never appears", "r/other.md" not in paths, paths)
    check("rows carry what the home screen shows",
          all(set(("path", "title", "mtime_ns", "size")) <= set(row) for row in rows), rows[:1])
    check("the limit is honoured", len(db.store.recent(USER, 1)) == 1)
```

> 注意：`test_recent()` 与先前的测试**共用同一个库**，所以 `recent(USER, 10)` 会包含 Ali 早先建的笔记（`s/other.md` 等）。断言必须容忍这一点——这也是上面不能用前缀判断的原因之一。

并在 `main()` 的调用序列里，把 `test_identity_validation()` 之前插入 `test_recent()`：

```python
        test_index_freshness()
        test_recent()
        test_identity_validation()
```

同时在文件顶部加 `import time`——`tools/selftest.py` 原本**没有**这个 import，`test_recent` 需要它。

- [ ] **Step 2: 运行，确认失败**

```bash
python tools/selftest.py
```

预期：`AttributeError: 'IndexStore' object has no attribute 'recent'`

- [ ] **Step 3: 实现**

在 `usr/local/marknest/lib/db.py` 的 `IndexStore` 里，`get()` 方法之后加：

```python
    def recent(self, user, limit=12):
        """The user's notes, most recently modified first.

        There is no "recently opened" bookkeeping and deliberately so: this is
        the same table the search index maintains, ordered by the file's own
        modification time. That means an edit made over SMB shows up here
        immediately after the next scan, which is what a person means by
        "recent" anyway - and it costs no state to keep in step.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT rel_path, title, mtime_ns, size_bytes FROM notes "
                "WHERE user = ? ORDER BY mtime_ns DESC, rel_path LIMIT ?",
                (user, int(limit)),
            ).fetchall()
        except sqlite3.Error as exc:
            log.warning("cannot list recent notes for %s: %s", user, exc)
            raise IndexUnavailable("the search index could not be read")
        return [
            {
                "path": row["rel_path"],
                "title": row["title"] or row["rel_path"],
                "mtime_ns": int(row["mtime_ns"]),
                "size": int(row["size_bytes"]),
            }
            for row in rows
        ]
```

- [ ] **Step 4: 运行，确认通过**

```bash
python tools/selftest.py
```

预期：`passed: 56 failed: 0`（原 51 项 + 新增 5 项）

- [ ] **Step 5: 提交**

```bash
git add usr/local/marknest/lib/db.py tools/selftest.py
git commit -m "feat(index): list a user's notes by modification time"
```

---

## Task 2: 后端 —— `GET /recent`

**Files:**
- Modify: `usr/local/marknest/lib/api.py`
- Test: `tools/selftest.py`

- [ ] **Step 1: 写失败的断言**

在 `tools/selftest.py` 的 `test_recent()` 末尾追加（同一个函数里，因为它复用刚才建立的库）：

```python
    # The endpoint, through the dispatcher, so the route and the envelope are
    # exercised rather than just the query.
    status, payload = request("GET", "/v2/proxy/marknest/recent?limit=2")
    data = payload.get("data") or {}
    check("GET /recent answers", status == 200 and payload.get("code") == 0, payload)
    check("it returns at most the requested number",
          len(data.get("recent") or []) <= 2, data)
    check("the entries carry a path and a time",
          all("path" in item and "mtime_ns" in item for item in data.get("recent") or []),
          data.get("recent"))

    status, payload = request("GET", "/v2/proxy/marknest/recent?limit=9999")
    check("an absurd limit is clamped rather than refused", status == 200, payload)
    check("and clamped to the documented ceiling",
          len((payload.get("data") or {}).get("recent") or []) <= 50, payload)
```

> `request()` 是 `selftest.py` 里既有的辅助函数，签名 `request(method, path, body=None, headers=None) -> (status, payload)`。

- [ ] **Step 2: 运行，确认失败**

```bash
python tools/selftest.py
```

预期：`GET /recent answers` FAIL，状态 404（`no such endpoint: /recent`）

- [ ] **Step 3: 实现**

在 `usr/local/marknest/lib/api.py` 的 `Api` 类里，`get_search` 之后加：

```python
    # ----------------------------------------------------------------- recent

    def get_recent(self, request):
        """The notes the home screen lists, most recently modified first.

        Deliberately not paginated: this is a starting point, not a browser.
        The ceiling exists so a client cannot ask for the whole library and
        make the socket proxy carry it.
        """
        limit = _as_int(request.param("limit"), "limit", default=12, minimum=1)
        limit = min(limit, 50)
        indexer.maybe_scan(request.user)
        rows = store.recent(request.user, limit)
        return {"recent": rows, "count": len(rows), "limit": limit}
```

在 `dispatch()` 的 `GET` 分支里，`/search` 之后加：

```python
            if path == "/recent":
                return 200, self.get_recent(request)
```

- [ ] **Step 4: 运行，确认通过**

```bash
python tools/selftest.py
```

预期：`passed: 61 failed: 0`

- [ ] **Step 5: 提交**

```bash
git add usr/local/marknest/lib/api.py tools/selftest.py
git commit -m "feat(api): GET /recent for the home screen"
```

---

## Task 3: 编辑器 —— `applyEdit()`，唯一能安全改文档的入口

**为什么需要它：** 格式按钮要改文档。若从外部直接改 DOM，CodeMirror 的 state 不知道，于是**撤销栈、脏标记、预览刷新会同时坏掉**。把变更统一走一个 transaction 入口，三者自然同步。

**Files:**
- Modify: `webui-src/editor/index.js`
- Test: `tools/verify_editor.py`（Task 5 会用上；本任务先只验证它存在）

- [ ] **Step 1: 写失败的断言**

在 `tools/verify_editor.py` 的第 1 节（`the application boots`）之后，插入：

```python
            print("\n1b. the editor exposes a single safe way to change the document")
            check("the controller offers applyEdit", app_note_open(page) and page.evaluate(
                "() => typeof window.MDEditor.create === 'function'"))
```

> 本步骤只断言 bundle 的导出面；真正的行为断言在第 5 节（Task 5 会替换掉这一节）。

同时在 `tools/webui_check.js` 的 `VENDOR_SURFACE` 里加 `'applyEdit'`：

```js
const VENDOR_SURFACE = ['create', 'render', 'applyEdit'];
```

- [ ] **Step 2: 运行，确认失败**

```bash
node tools/webui_check.js
```

预期：`[ERROR] js/vendor.editor.js does not appear to export applyEdit` → `RESULT: FAILED`

- [ ] **Step 3: 实现**

在 `webui-src/editor/index.js` 的 `create()` 返回对象里，`getValue()` 之前插入：

```js
    /**
     * Apply a change produced by a pure command function.
     *
     * Everything that edits the document goes through here, and that is the
     * point: a change dispatched as a CodeMirror transaction lands in the undo
     * history, notifies the update listener that drives the dirty flag and the
     * preview, and cannot leave the view and the state disagreeing. Writing to
     * the DOM instead would break all three at once.
     */
    applyEdit(command) {
      const main = view.state.selection.main;
      const result = command({
        doc: view.state.doc.toString(),
        from: main.from,
        to: main.to,
        selected: view.state.sliceDoc(main.from, main.to)
      });
      if (!result || !result.changes) {
        return;
      }
      view.dispatch({
        changes: result.changes,
        selection: result.selection || { anchor: main.from }
      });
      view.focus();
    },
```

- [ ] **Step 4: 重新构建 bundle 并验证**

```bash
python tools/webui_build.py
python tools/webui_build.py --check
node tools/webui_check.js
```

预期：`webui_build.py` 输出新的 bundle sha256；`--check` 输出 `OK`；`webui_check.js` 输出 `errors: 0` / `RESULT: PASSED`

- [ ] **Step 5: 提交**

```bash
git add webui-src/editor/index.js webui/js/vendor.editor.js webui/js/vendor.editor.js.sha256 tools/webui_check.js tools/verify_editor.py
git commit -m "feat(editor): one transaction entry point for programmatic edits"
```

---

## Task 4: `mdcmd.js` —— 13 个纯函数

**Files:**
- Create: `webui/js/mdcmd.js`
- Test: `tools/webui_check.js`

**接口（全模块唯一约定）：**

```js
command(ctx) -> { changes: {from, to, insert}, selection: {anchor, head} }
```

`ctx` = `{doc, from, to, selected}`。`changes.from/to` 是**文档中的绝对偏移**。纯函数：不改入参、不碰 DOM、不读全局。

- [ ] **Step 1: 写失败的断言**

在 `tools/webui_check.js` 的 `ORDER` 里，`js/ui.js` 之后加 `'js/mdcmd.js'`；在 `MODULES` 与 `ALLOWED_GLOBALS` 里加 `'MDCmd'`。

然后在 `REQUIRED` 之后新增一段（放在 `/* ---- vendor bundle ---- */` 之前）：

```js
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
    // [label, command, ctx, expected substring in the inserted text]
    ['bold wraps a selection', 'bold',
      { doc: 'hello', from: 0, to: 5, selected: 'hello' }, '**hello**'],
    ['bold on bare cursor inserts the markers', 'bold',
      { doc: '', from: 0, to: 0, selected: '' }, '****'],
    ['italic wraps a selection', 'italic',
      { doc: 'hi', from: 0, to: 2, selected: 'hi' }, '*hi*'],
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
      { doc: '', from: 0, to: 0, selected: '' }, '| --- | --- | --- |']
  ];
  for (const [label, name, ctx, expected] of cases) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { cmdProblems.push(`${label}: MDCmd.commands.${name} is not a function`); continue; }
    const result = fn(ctx);
    const text = result && result.changes && typeof result.changes.insert === 'string'
      ? result.changes.insert : '';
    if (text.indexOf(expected) === -1) {
      cmdProblems.push(`${label}: expected ${JSON.stringify(expected)} inside ${JSON.stringify(text)}`);
    }
  }
  // Toggle-off: applying the same command twice must return the document to
  // where it started. This is the rule that is easiest to implement for half
  // the buttons and forget for the other half.
  for (const name of ['bold', 'italic', 'code', 'quote', 'h1', 'task', 'bullet', 'numbered']) {
    const fn = CMD.commands && CMD.commands[name];
    if (typeof fn !== 'function') { continue; }
    const once = fn({ doc: 'text', from: 0, to: 4, selected: 'text' });
    const applied = once.changes.insert;
    const twice = fn({ doc: applied, from: 0, to: applied.length, selected: applied });
    if (twice.changes.insert !== 'text') {
      cmdProblems.push(`toggle-off: ${name} produced ${JSON.stringify(twice.changes.insert)} on the second press`);
    }
  }
}
```

并在 `errorCount` 里加上 `+ cmdProblems.length`，在报告里加：

```js
console.log('');
console.log('markdown commands:');
for (const item of cmdProblems) { console.log('  [ERROR] ' + item); }
if (!cmdProblems.length) { console.log('  ok   every command produces the expected markdown, and toggles off'); }
```

- [ ] **Step 2: 运行，确认失败**

```bash
node tools/webui_check.js
```

预期：`[ERROR] js/mdcmd.js: file missing` 以及 `MDCmd is not exposed on window`

- [ ] **Step 3: 实现**

创建 `webui/js/mdcmd.js`：

```js
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
```

- [ ] **Step 4: 运行，确认通过**

```bash
node tools/webui_check.js
```

预期：`markdown commands: ok   every command produces the expected markdown, and toggles off`，`errors: 0`

- [ ] **Step 5: 提交**

```bash
git add webui/js/mdcmd.js tools/webui_check.js
git commit -m "feat(editor): pure markdown commands, asserted without a browser"
```

---

## Task 5: `formatbar.js` —— 按钮接到命令上

**Files:**
- Create: `webui/js/formatbar.js`
- Modify: `webui/js/editorpane.js`、`webui/index.html`、`webui/css/style.css`、`tools/webui_check.js`

- [ ] **Step 1: 写失败的断言**

在 `tools/webui_check.js` 的 `ORDER` 里 `js/mdcmd.js` 之后加 `'js/formatbar.js'`；`MODULES`/`ALLOWED_GLOBALS` 加 `'FormatBar'`；`REQUIRED` 加：

```js
  FormatBar: ['init', 'render', 'setEnabled'],
```

- [ ] **Step 2: 运行，确认失败**

```bash
node tools/webui_check.js
```

预期：`[ERROR] js/formatbar.js: file missing`、`FormatBar: module not exposed on window`

- [ ] **Step 3: 实现**

在 `webui/js/editorpane.js` 的导出对象里加一行（给格式栏一个执行入口）：

```js
    // The format bar edits through the editor rather than around it, so that
    // undo, the dirty flag and the preview all stay in step.
    applyCommand: function (command) {
      if (state.editor && state.editor.applyEdit) {
        state.editor.applyEdit(command);
      }
    },
```

创建 `webui/js/formatbar.js`：

```js
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
      { id: 'link', label: '⚭', title: 'format.link', command: 'link' },
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
      var url = global.prompt(I18N.t('format.linkPrompt'), 'https://');
      if (!url) {
        return;
      }
      global.EditorPane.applyCommand(function (ctx) {
        return MDCmd.commands.link(ctx, url);
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
            onclick: function () {
              onPress(item);
            }
          })
        );
      });
    });
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

  global.FormatBar = {
    init: init,
    render: render,
    setEnabled: setEnabled
  };
})(window);
```

在 `webui/index.html` 的应用工具栏之后、`.workspace` 之前插入：

```html
  <div class="format-bar" id="format-bar" role="toolbar" hidden
       data-i18n-aria-label="format.ariaLabel" aria-label="Formatting"></div>
```

在 `webui/index.html` 的脚本区，`js/ui.js` 之后插入：

```html
<script src="js/mdcmd.js?v=1.0.3"></script>
```

并在 `js/toshost.js` 之后、`js/index` 之前的位置（即 `vendor.editor.js` 与 `treepane.js` 之间）插入：

```html
<script src="js/formatbar.js?v=1.0.3"></script>
```

> 顺序见「脚本加载顺序」一节：`mdcmd` 紧跟 `ui`，`formatbar` 紧随 `vendor.editor`。

在 `webui/css/style.css` 的 `.statusbar` 规则之前插入：

```css
/* ------------------------------------------------------- format toolbar */

.format-bar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px 16px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  /* Horizontal scroll rather than wrap: wrapping changes the bar's height and
     makes the editor below jump every time the frame is resized through a
     breakpoint. */
  overflow-x: auto;
  scrollbar-width: none;
}
.format-bar[hidden] { display: none; }
.format-bar::-webkit-scrollbar { display: none; }

.format-btn {
  flex: 0 0 auto;
  min-width: 30px;
  height: 26px;
  padding: 0 7px;
  font: inherit;
  font-size: 12.5px;
  line-height: 1;
  color: var(--text);
  background: none;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
}
.format-btn:hover { background: var(--surface); border-color: var(--border); }
.format-btn:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; }
.format-btn.is-bold { font-weight: 700; }
.format-btn.is-italic { font-style: italic; }
.format-btn.is-mono { font-family: var(--mono); font-size: 11.5px; }

.format-sep {
  flex: 0 0 auto;
  width: 1px;
  height: 16px;
  margin: 0 5px;
  background: var(--border-strong);
}
```

- [ ] **Step 4: 运行，确认通过**

```bash
node tools/webui_check.js
python tools/validate.py
```

预期：`webui_check.js` → `errors: 0`；`validate.py` → 仍 PASS（`.lang` 未动，长度不受影响）

- [ ] **Step 5: 加一条浏览器断言——格式按钮必须让脏标记亮起**

这条是**规格 §11 第 7 条**，也是「所有改动走 transaction API」这个要求的唯一行为证据：如果某个按钮绕过编辑器直接改 DOM，撤销栈、脏标记、预览会同时坏掉，而这三者里只有脏标记能在浏览器里被稳定地一眼断言。

在 `tools/verify_editor.py` 第 4 节（`block elements carry the source line`）之后插入：

```python
            print("\n4b. the format toolbar edits through the editor")
            check("the format bar appears once a note is open",
                  app_note_visible(page, "#format-bar"))
            page.click(".cm-content")
            page.keyboard.press("Control+a")
            page.wait_for_timeout(200)
            page.click("#fmt-bold")
            page.wait_for_timeout(400)
            check("the bold command wrapped the document", page.evaluate(
                "() => document.querySelector('.cm-content').textContent.indexOf('**') !== -1"),
                page.evaluate("() => document.querySelector('.cm-content').textContent.slice(0, 40)"))
            check("the editor is now marked dirty", page.evaluate(
                "() => document.getElementById('dirty-dot').hidden === false"))
            check("the preview followed the change", page.evaluate(
                "() => document.querySelectorAll('#preview-body strong').length > 0"))
```

其中 `app_note_visible(page, selector)` 是本文件顶部要新增的一个小辅助（`verify_editor.py` 目前没有跨 frame 的可见性判断）：

```python
def app_note_visible(page, selector):
    """Visibility inside whichever frame currently holds the application."""
    for frame in page.frames:
        if "/marknest/" in frame.url:
            try:
                return frame.is_visible(selector)
            except Exception:  # noqa: BLE001
                return False
    return page.is_visible(selector)
```

Run: `python tools/verify_editor.py`
Expected: `4b` 四条全部 PASS

- [ ] **Step 6: 提交**

```bash
git add webui/js/formatbar.js webui/js/editorpane.js webui/index.html webui/css/style.css tools/webui_check.js
git commit -m "feat(webui): wire the format toolbar to the markdown commands"
```

---

## Task 6: 视图状态机与哈希路由

**Files:**
- Modify: `webui/js/app.js`、`webui/index.html`、`webui/css/style.css`

- [ ] **Step 1: 写失败的断言**

在 `tools/verify_editor.py` 的第 2 节（`opening a note`）之前插入：

```python
            print("\n1c. the application starts on its home screen")
            check("home is the initial view", page.evaluate(
                "() => document.getElementById('workspace').classList.contains('is-home')"))
            check("the editor is not shown yet", page.evaluate(
                "() => document.getElementById('pane-editor').offsetParent === null"))
            check("the hash says home", page.evaluate("() => location.hash") == "#/home",
                  page.evaluate("() => location.hash"))
```

- [ ] **Step 2: 运行，确认失败**

```bash
python tools/verify_editor.py
```

预期：三条都 FAIL（当前没有 `is-home` 类，哈希为空）

- [ ] **Step 3: 实现**

在 `webui/index.html` 的 `.workspace` 之后、`.statusbar` 之前插入主页容器：

```html
    <div class="home" id="home" hidden>
      <div class="home-actions">
        <button type="button" class="home-btn" id="home-open"
                data-i18n="home.open">打开文件</button>
        <button type="button" class="home-btn home-btn-primary" id="home-new"
                data-i18n="home.new">新建文件</button>
      </div>
      <div class="home-recent" id="home-recent"></div>
    </div>
```

在 `webui/css/style.css` 的 `.workspace` 规则之后插入：

```css
/* The home screen takes the workspace over entirely. It is the state the app
   opens in, so it is laid out as a starting point rather than as a panel: the
   two actions are the only thing competing for attention. */
.home {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 0;
  overflow-y: auto;
  padding: 48px 24px 32px;
  background: var(--bg);
}
.home[hidden] { display: none; }

.home-actions {
  display: flex;
  gap: 14px;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: center;
}

.home-btn {
  font: inherit;
  font-size: 14px;
  min-width: 148px;
  padding: 12px 22px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  cursor: pointer;
}
.home-btn:hover { border-color: var(--primary); color: var(--primary); }
.home-btn-primary {
  color: #fff;
  background: var(--primary);
  border-color: var(--primary);
}
.home-btn-primary:hover { background: var(--primary-hover); color: #fff; }
.home-btn:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.home-recent {
  flex: 1 1 auto;
  width: 100%;
  max-width: 620px;
  margin-top: 40px;
}

.workspace.is-home { display: none; }
```

在 `webui/js/app.js` 里，`pageFromHash()` 之后插入状态机：

```js
  var view = { name: 'home' };

  /* Two states, derived from whether a note is open rather than stored
     separately - a stored flag and an open note can disagree, and then the
     screen shows one thing and the hash says another. */
  function setView(name) {
    if (view.name === name) {
      return;
    }
    view.name = name;
    var home = document.getElementById('home');
    var workspace = document.getElementById('workspace');
    if (home) {
      home.hidden = name !== 'home';
    }
    if (workspace) {
      workspace.classList.toggle('is-home', name === 'home');
    }
    if (global.FormatBar) {
      global.FormatBar.setEnabled(name === 'note');
    }
  }

  function showHome(push) {
    setView('home');
    if (global.TreePane) {
      global.TreePane.setCurrent('');
    }
    setTitle('');
    if (push) {
      writeHash('');
    }
    if (global.HomePane) {
      global.HomePane.reload();
    }
  }
```

修改 `writeHash` 让它接受空路径：

```js
  function writeHash(path) {
    var next = path ? '#/notes?p=' + encodeURIComponent(path) : '#/home';
    if (global.location.hash !== next) {
      global.location.hash = next;
    }
  }
```

修改 `openNote`，在打开成功后进入 `note` 态：

```js
  function openNote(path, push) {
    if (!path) {
      showHome(push);
      return Promise.resolve();
    }
    setTitle(path);
    setView('note');
    if (global.TreePane) {
      global.TreePane.setCurrent(path);
    }
    if (push) {
      writeHash(path);
    }
    return global.EditorPane.open(path);
  }
```

在 `boot()` 的 `step('shell', bindShell)` 之后插入：

```js
    step('home', function () {
      if (global.HomePane) {
        global.HomePane.init({ onOpen: openNote });
      }
    });

    step('formatbar', function () {
      if (global.FormatBar) {
        global.FormatBar.init();
      }
    });
```

并把 `boot()` 末尾的 `tree-load` 步骤改成先归位到 home：

```js
    step('tree-load', function () {
      global.TreePane.reload().then(function () {
        var route = pageFromHash();
        if (route.params.p) {
          openNote(route.params.p, false);
        } else {
          showHome(false);
        }
      });
    });
```

同时把 `pageFromHash` 里 `raw || 'notes'` 改成 `raw || 'home'`。

- [ ] **Step 4: 运行，确认通过**

```bash
python tools/verify_editor.py
```

预期：`1c` 三条 PASS；但后续 `opening a note` 一节会 FAIL，因为 `HomePane` 还不存在——这正是下一任务要做的。

- [ ] **Step 5: 提交**

```bash
git add webui/js/app.js webui/index.html webui/css/style.css tools/verify_editor.py
git commit -m "feat(webui): a home state, derived from whether a note is open"
```

---

## Task 7: `homepane.js` —— 主页与最近文件

**Files:**
- Create: `webui/js/homepane.js`
- Modify: `webui/js/api.js`、`webui/index.html`、`tools/webui_check.js`、`tools/verify_editor.py`

- [ ] **Step 1: 写失败的断言**

先在 `tools/verify_editor.py` 的第 1c 节之后补上主页断言：

```python
            check("both home actions are offered", page.evaluate(
                "() => !!document.getElementById('home-open') && !!document.getElementById('home-new')"))
            page.wait_for_timeout(600)
            recent = page.inner_text("#home-recent")
            check("the recent list names a note", "welcome.md" in recent, recent[:120])
            check("and it shows a relative time", "分钟前" in recent or "前" in recent, recent[:120])
```

在 `tools/webui_check.js` 的 `ORDER` 里 `js/formatbar.js` 之后加 `'js/homepane.js'`；`MODULES`/`ALLOWED_GLOBALS` 加 `'HomePane'`；`REQUIRED` 加：

```js
  HomePane: ['init', 'reload', 'render'],
```

- [ ] **Step 2: 运行，确认失败**

```bash
node tools/webui_check.js && python tools/verify_editor.py
```

预期：`webui_check.js` 报 `js/homepane.js: file missing`；`verify_editor.py` 的两条新断言 FAIL（`#home-recent` 是空的）

- [ ] **Step 3: 实现**

在 `webui/js/api.js` 的 `search` 之前加：

```js
    getRecent: function (limit) {
      return request('/recent' + queryString({ limit: limit }));
    },
```

创建 `webui/js/homepane.js`：

```js
/* MarkNest for TOS - the home screen.
 *
 * Shown whenever no note is open. It answers the two questions a person has
 * when they arrive: how do I get a note open, and what was I working on. The
 * list is the index ordered by file modification time, so a note edited over
 * SMB appears here after the next scan without this module tracking anything. */

(function (global) {
  'use strict';

  var RECENT_LIMIT = 12;
  var state = { onOpen: null };

  var hosts = {};

  function cacheHosts() {
    hosts.root = document.getElementById('home');
    hosts.recent = document.getElementById('home-recent');
    hosts.open = document.getElementById('home-open');
    hosts.create = document.getElementById('home-new');
  }

  /* Relative time, computed here rather than on the server: the server would
     have to send a rendering decision down with the data, and the answer goes
     stale while the page is open. */
  function relativeTime(ns) {
    if (!ns) {
      return '';
    }
    var then = ns / 1e6;
    var seconds = Math.max(0, (Date.now() - then) / 1000);
    if (seconds < 60) {
      return I18N.t('home.timeJustNow');
    }
    if (seconds < 3600) {
      return I18N.t('home.timeMinutes', { n: Math.floor(seconds / 60) });
    }
    if (seconds < 86400) {
      return I18N.t('home.timeHours', { n: Math.floor(seconds / 3600) });
    }
    if (seconds < 172800) {
      return I18N.t('home.timeYesterday');
    }
    if (seconds < 604800) {
      return I18N.t('home.timeDays', { n: Math.floor(seconds / 86400) });
    }
    var date = new Date(then);
    return date.getFullYear() + '-' +
      String(date.getMonth() + 1).padStart(2, '0') + '-' +
      String(date.getDate()).padStart(2, '0');
  }

  function render(rows) {
    if (!hosts.recent) {
      return;
    }
    UI.clear(hosts.recent);
    hosts.recent.appendChild(
      UI.el('div', { class: 'home-recent-title', 'data-i18n': 'home.recent', text: I18N.t('home.recent') })
    );
    if (!rows.length) {
      hosts.recent.appendChild(
        UI.el('div', { class: 'empty', text: I18N.t('home.noRecent') })
      );
      return;
    }
    var list = UI.el('div', { class: 'home-recent-list' });
    rows.forEach(function (row) {
      var item = UI.el('button', { type: 'button', class: 'home-recent-item', title: row.path });
      item.appendChild(UI.el('span', { class: 'home-recent-name', text: row.title || row.path }));
      item.appendChild(UI.el('span', { class: 'home-recent-time', text: relativeTime(row.mtime_ns) }));
      item.addEventListener('click', function () {
        if (typeof state.onOpen === 'function') {
          state.onOpen(row.path, true);
        }
      });
      list.appendChild(item);
    });
    hosts.recent.appendChild(list);
  }

  function reload() {
    if (!hosts.recent) {
      cacheHosts();
    }
    return API.getRecent(RECENT_LIMIT).then(function (payload) {
      render((payload && payload.recent) || []);
    }).catch(function (error) {
      if (!hosts.recent) {
        return;
      }
      UI.clear(hosts.recent);
      hosts.recent.appendChild(UI.errorBox(UI.el('div'), I18N.errorText(error), reload));
    });
  }

  function init(options) {
    cacheHosts();
    state.onOpen = (options || {}).onOpen || null;
    if (hosts.open) {
      hosts.open.addEventListener('click', function () {
        if (global.FilePicker) {
          global.FilePicker.open();
        }
      });
    }
    if (hosts.create) {
      hosts.create.addEventListener('click', function () {
        if (global.TreePane) {
          global.TreePane.newNote();
        }
      });
    }
  }

  global.HomePane = { init: init, reload: reload, render: render };
})(window);
```

在 `webui/index.html` 的脚本区，`js/formatbar.js` 之后加：

```html
<script src="js/homepane.js?v=1.0.3"></script>
```

在 `webui/css/style.css` 的 `.home` 规则之后加：

```css
.home-recent-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: 8px;
}

.home-recent-list {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface);
}

.home-recent-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  width: 100%;
  padding: 9px 14px;
  font: inherit;
  font-size: 13px;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}
.home-recent-item:last-child { border-bottom: none; }
.home-recent-item:hover { background: var(--surface-2); }

.home-recent-name {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-recent-time {
  flex: 0 0 auto;
  font-size: 11.5px;
  color: var(--text-faint);
}
```

- [ ] **Step 4: 运行，确认通过**

```bash
node tools/webui_check.js
python tools/verify_editor.py
```

预期：两者都 PASS（`opening a note` 一节此时也应恢复通过，因为 `showHome` 不再被误触发）

- [ ] **Step 5: 提交**

```bash
git add webui/js/homepane.js webui/js/api.js webui/index.html webui/css/style.css tools/webui_check.js tools/verify_editor.py
git commit -m "feat(webui): home screen with the two entry actions and recent notes"
```

---

## Task 8: ☰ 更多菜单

**Files:**
- Modify: `webui/index.html`、`webui/css/style.css`、`webui/js/app.js`
- Modify: `tools/verify_editor.py`

- [ ] **Step 1: 写失败的断言**

在 `tools/verify_editor.py` 的第 1c 节之后插入：

```python
            print("\n1d. the more menu")
            check("the menu is closed until asked for", not page.is_visible("#more-menu"))
            page.click("#btn-more")
            page.wait_for_timeout(300)
            check("pressing it opens the menu", page.is_visible("#more-menu"))
            items = page.inner_text("#more-menu")
            for expected in ("主页", "新建文件", "打开文件"):
                check("the menu offers %s" % expected, expected in items, items[:120])
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check("escape closes it", not page.is_visible("#more-menu"))
```

- [ ] **Step 2: 运行，确认失败**

```bash
python tools/verify_editor.py
```

预期：`Page.click: Timeout` —— `#btn-more` 还不存在

- [ ] **Step 3: 实现**

在 `webui/index.html` 的 `.topbar` 里，`.brand` 之前插入：

```html
    <button type="button" class="btn btn-icon" id="btn-more"
            data-i18n-title="nav.more" title="更多"
            aria-haspopup="true" aria-expanded="false" aria-controls="more-menu">
      <span aria-hidden="true">☰</span>
    </button>
```

并把顶栏里原来的 `＋` 按钮整块删除：

```html
      <button type="button" class="btn btn-icon" id="btn-new-note"
              data-i18n-title="tree.newNoteTitle" title="新建笔记">
        <span aria-hidden="true">＋</span>
      </button>
```

在 `webui/index.html` 的 `.app` 内、`.toast-host` 之前插入：

```html
<div class="menu" id="more-menu" role="menu" hidden>
  <button type="button" class="menu-item" id="more-home" role="menuitem"
          data-i18n="nav.home">主页</button>
  <button type="button" class="menu-item" id="more-new" role="menuitem"
          data-i18n="nav.newNote">新建文件</button>
  <button type="button" class="menu-item" id="more-open" role="menuitem"
          data-i18n="nav.openNote">打开文件</button>
</div>
```

在 `webui/css/style.css` 的 `.ctx-menu` 规则之后加：

```css
/* The application menu, anchored under the toolbar button rather than at the
   pointer: it is a menu of the application, not of whatever was clicked. */
.menu {
  position: fixed;
  z-index: 60;
  min-width: 148px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
}
.menu[hidden] { display: none; }

.menu-item {
  font: inherit;
  font-size: 12.5px;
  text-align: left;
  color: var(--text);
  background: none;
  border: none;
  border-radius: 5px;
  padding: 7px 10px;
  cursor: pointer;
}
.menu-item:hover { background: var(--surface-2); }
```

在 `webui/js/app.js` 的 `bindShell()` 里插入菜单逻辑：

```js
    var moreButton = document.getElementById('btn-more');
    var moreMenu = document.getElementById('more-menu');

    function closeMenu() {
      if (!moreMenu || moreMenu.hidden) {
        return;
      }
      moreMenu.hidden = true;
      if (moreButton) {
        moreButton.setAttribute('aria-expanded', 'false');
      }
      document.removeEventListener('mousedown', onOutside);
      document.removeEventListener('keydown', onMenuKey);
    }

    function onOutside() { closeMenu(); }
    function onMenuKey(event) {
      if (event.key === 'Escape') {
        closeMenu();
        if (moreButton) { moreButton.focus(); }
      }
    }

    if (moreButton && moreMenu) {
      moreButton.addEventListener('click', function (event) {
        event.stopPropagation();
        if (!moreMenu.hidden) {
          closeMenu();
          return;
        }
        var box = moreButton.getBoundingClientRect();
        moreMenu.style.left = Math.round(box.left) + 'px';
        moreMenu.style.top = Math.round(box.bottom + 4) + 'px';
        moreMenu.hidden = false;
        moreButton.setAttribute('aria-expanded', 'true');
        // Registered on the next tick so the click that opened the menu does
        // not immediately close it.
        global.setTimeout(function () {
          document.addEventListener('mousedown', onOutside);
          document.addEventListener('keydown', onMenuKey);
        }, 0);
      });
    }

    var moreHome = document.getElementById('more-home');
    if (moreHome) {
      moreHome.addEventListener('click', function () {
        closeMenu();
        showHome(true);
      });
    }
    var moreNew = document.getElementById('more-new');
    if (moreNew) {
      moreNew.addEventListener('click', function () {
        closeMenu();
        global.TreePane.newNote();
      });
    }
    var moreOpen = document.getElementById('more-open');
    if (moreOpen) {
      moreOpen.addEventListener('click', function () {
        closeMenu();
        global.FilePicker.open();
      });
    }
```

同时删掉 `bindShell()` 里原来的 `#btn-new-note` 绑定：

```js
    var newButton = document.getElementById('btn-new-note');
    if (newButton) {
      newButton.addEventListener('click', function () {
        global.TreePane.newNote();
      });
    }
```

- [ ] **Step 4: 运行，确认通过**

```bash
python tools/verify_editor.py
```

预期：`1d` 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add webui/index.html webui/css/style.css webui/js/app.js tools/verify_editor.py
git commit -m "feat(webui): a more menu, and ＋ folds into it"
```

---

## Task 9: 文件选择弹层与本地导入

**Files:**
- Create: `webui/js/filepicker.js`
- Modify: `webui/index.html`、`webui/css/style.css`、`webui/js/app.js`、`tools/webui_check.js`
- Modify: `tools/verify_editor.py`

- [ ] **Step 1: 写失败的断言**

在 `tools/verify_editor.py` 末尾（`browser.close()` 之前）插入：

```python
            print("\n11. opening a file from either source")
            page.evaluate("() => { location.hash = '#/home'; }")
            page.wait_for_timeout(600)
            page.click("#home-open")
            page.wait_for_timeout(700)
            check("the picker opens", page.is_visible("#file-picker"))
            tabs = page.inner_text("#file-picker")
            check("it offers the library", "笔记库" in tabs, tabs[:160])
            check("it offers local files", "本机" in tabs, tabs[:160])

            # A local file is imported, not merely opened: the library is the
            # only place a note lives, so "open" has to mean "bring it in".
            page.evaluate(
                """() => {
                     const dt = new DataTransfer();
                     dt.items.add(new File(['# Imported\\n\\nfrom the test\\n'],
                                           'imported-by-test.md', { type: 'text/markdown' }));
                     const input = document.getElementById('picker-file');
                     input.files = dt.files;
                     input.dispatchEvent(new Event('change'));
                   }"""
            )
            page.wait_for_timeout(2500)
            check("the imported note opened", "imported-by-test.md" in page.inner_text("#current-path"),
                  page.inner_text("#current-path"))
            check("and it is in the library now", page.evaluate(
                """async () => {
                     const r = await fetch('/v2/proxy/marknest/notes?path=imported-by-test.md',
                                           { credentials: 'include', headers: API.authHeaders() });
                     return r.status === 200;
                   }"""))
```

并在 `tools/webui_harness.py` 的 `StubApi.tree()` 里无需改动——导入走 `POST /notes/new`，桩已支持。

在 `tools/webui_check.js` 的 `ORDER` 里 `js/homepane.js` 之后加 `'js/filepicker.js'`；`MODULES`/`ALLOWED_GLOBALS` 加 `'FilePicker'`；`REQUIRED` 加：

```js
  FilePicker: ['init', 'open', 'close', 'isOpen'],
```

- [ ] **Step 2: 运行，确认失败**

```bash
node tools/webui_check.js && python tools/verify_editor.py
```

预期：`webui_check.js` 报文件缺失；`verify_editor.py` 的 `the picker opens` FAIL

- [ ] **Step 3: 实现**

在 `webui/index.html` 的 `#more-menu` 之后插入弹层：

```html
<div class="modal" id="file-picker" hidden>
  <div class="modal-veil" data-picker-close="1"></div>
  <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="file-picker-title">
    <div class="modal-head">
      <h2 id="file-picker-title" data-i18n="picker.title">打开文件</h2>
      <button class="modal-close" type="button" id="picker-close"
              data-i18n-aria-label="common.close" aria-label="关闭">×</button>
    </div>
    <div class="modal-toolbar">
      <button type="button" class="btn btn-sm is-active" id="picker-tab-library"
              data-i18n="picker.library">笔记库</button>
      <button type="button" class="btn btn-sm" id="picker-tab-local"
              data-i18n="picker.local">本机文件</button>
    </div>
    <div class="modal-body" id="picker-body"></div>
    <div class="modal-foot">
      <input type="file" id="picker-file" accept=".md,.markdown,.mdown,.txt" hidden>
      <button type="button" class="btn" id="picker-browse" hidden
              data-i18n="picker.browse">选择本机文件…</button>
    </div>
  </div>
</div>
```

创建 `webui/js/filepicker.js`：

```js
/* MarkNest for TOS - the open-file dialog.
 *
 * Two sources, one dialog, because they answer the same question and the person
 * asking it should not have to know where the file lives before choosing where
 * to look. The library side renders the same tree the left pane does; the local
 * side imports, since a note that is not in the library would be a second place
 * notes live and there is deliberately only one. */

(function (global) {
  'use strict';

  var state = { open: false, tab: 'library', onOpen: null };
  var hosts = {};
  var lastFocus = null;

  function cacheHosts() {
    hosts.modal = document.getElementById('file-picker');
    hosts.body = document.getElementById('picker-body');
    hosts.tabLibrary = document.getElementById('picker-tab-library');
    hosts.tabLocal = document.getElementById('picker-tab-local');
    hosts.browse = document.getElementById('picker-browse');
    hosts.file = document.getElementById('picker-file');
    hosts.close = document.getElementById('picker-close');
  }

  function setTab(tab) {
    state.tab = tab;
    var isLibrary = tab === 'library';
    hosts.tabLibrary.classList.toggle('is-active', isLibrary);
    hosts.tabLocal.classList.toggle('is-active', !isLibrary);
    hosts.browse.hidden = isLibrary;
    if (isLibrary) {
      renderLibrary('');
    } else {
      UI.clear(hosts.body);
      hosts.body.appendChild(UI.el('div', {
        class: 'empty',
        text: I18N.t('picker.localHint')
      }));
    }
  }

  function renderLibrary(path) {
    UI.loading(hosts.body, I18N.t('common.loading'));
    API.getTree(path).then(function (payload) {
      UI.clear(hosts.body);
      var entries = (payload && payload.entries) || [];
      if (!entries.length) {
        hosts.body.appendChild(UI.el('div', { class: 'empty', text: I18N.t('tree.empty') }));
        return;
      }
      // Reuses the tree row styling rather than inventing a second look for
      // the same thing. `.nas-*` does not exist in this stylesheet - that was
      // the previous application's naming - so a copy of it here would render
      // as unstyled markup.
      var list = UI.el('div', { class: 'tree-list' });
      entries.forEach(function (entry) {
        if (entry.type === 'other') {
          return;
        }
        var row = UI.el('button', { type: 'button',
                                    class: 'tree-row' + (entry.type === 'dir' ? ' is-dir' : '') });
        row.appendChild(UI.el('span', { class: 'tree-caret', 'aria-hidden': 'true',
                                        text: entry.type === 'dir' ? '▸' : '' }));
        row.appendChild(UI.el('span', { class: 'tree-name', text: entry.name, title: entry.name }));
        row.addEventListener('click', function () {
          if (entry.type === 'dir') {
            renderLibrary(entry.path);
            return;
          }
          var callback = state.onOpen;
          close();
          if (callback) {
            callback(entry.path, true);
          }
        });
        list.appendChild(row);
      });
      hosts.body.appendChild(list);
    }).catch(function (error) {
      UI.clear(hosts.body);
      hosts.body.appendChild(UI.errorBox(UI.el('div'), I18N.errorText(error), function () {
        renderLibrary(path);
      }));
    });
  }

  /* Importing means "make this a real note". Reading the file and posting it
     as a new note keeps the library the single place a note lives; trying to
     edit a local file in place would leave the application unable to promise
     where the user's writing actually is. */
  function importFile(file) {
    var name = file.name || 'untitled.md';
    var reader = new global.FileReader();
    reader.onload = function () {
      attempt(name, reader.result, 1);
    };
    reader.onerror = function () {
      UI.toast(I18N.t('picker.readFailed'), 'bad');
    };
    reader.readAsText(file);
  }

  function attempt(name, content, round) {
    API.createNote({ path: name, content: content }).then(function (note) {
      var callback = state.onOpen;
      close();
      UI.toast(I18N.t('tree.created', { name: note.path }), 'ok');
      if (callback) {
        callback(note.path, true);
      }
    }).catch(function (error) {
      if (error && error.code === 3006 && round < 100) {
        // A name that is taken is not a failure, it is the next name.
        var split = name.lastIndexOf('.');
        var stem = split > 0 ? name.slice(0, split) : name;
        var ext = split > 0 ? name.slice(split) : '';
        attempt(stem + '-' + round + ext, content, round + 1);
        return;
      }
      UI.toast(I18N.errorText(error), 'bad');
    });
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  function open(onOpen) {
    if (!hosts.modal) {
      cacheHosts();
    }
    if (!hosts.modal) {
      return;
    }
    if (typeof onOpen === 'function') {
      state.onOpen = onOpen;
    }
    state.open = true;
    lastFocus = document.activeElement;
    hosts.modal.hidden = false;
    document.addEventListener('keydown', onKeydown);
    setTab('library');
    if (hosts.close) {
      hosts.close.focus();
    }
  }

  function close() {
    if (!hosts.modal) {
      return;
    }
    state.open = false;
    hosts.modal.hidden = true;
    document.removeEventListener('keydown', onKeydown);
    if (lastFocus && typeof lastFocus.focus === 'function') {
      lastFocus.focus();
    }
  }

  function bind() {
    if (!hosts.modal || hosts.modal.getAttribute('data-bound')) {
      return;
    }
    hosts.modal.setAttribute('data-bound', '1');
    hosts.tabLibrary.addEventListener('click', function () { setTab('library'); });
    hosts.tabLocal.addEventListener('click', function () { setTab('local'); });
    hosts.close.addEventListener('click', close);
    hosts.browse.addEventListener('click', function () { hosts.file.click(); });
    hosts.file.addEventListener('change', function () {
      if (hosts.file.files && hosts.file.files.length) {
        importFile(hosts.file.files[0]);
      }
      hosts.file.value = '';
    });
    Array.prototype.forEach.call(
      hosts.modal.querySelectorAll('[data-picker-close]'),
      function (node) { node.addEventListener('click', close); }
    );
  }

  function init() {
    cacheHosts();
    bind();
  }

  global.FilePicker = {
    init: init,
    open: open,
    close: close,
    isOpen: function () { return state.open; }
  };
})(window);
```

在 `webui/index.html` 的脚本区，`js/homepane.js` 之后加：

```html
<script src="js/filepicker.js?v=1.0.3"></script>
```

在 `webui/js/app.js` 的 `boot()` 里加：

```js
    step('filepicker', function () {
      if (global.FilePicker) {
        global.FilePicker.init();
      }
    });
```

- [ ] **Step 4: 运行，确认通过**

```bash
node tools/webui_check.js
python tools/verify_editor.py
```

预期：两者 PASS，含导入用例

- [ ] **Step 5: 确认撞名不覆盖（补充断言）**

在 Task 9 已写入的导入用例之后追加：

```python
            # A name already in the library must not be overwritten by an
            # import. The second file gets a suffixed name instead.
            page.evaluate(
                """() => {
                     const dt = new DataTransfer();
                     dt.items.add(new File(['# Second\\n'], 'welcome.md',
                                           { type: 'text/markdown' }));
                     const input = document.getElementById('picker-file');
                     input.files = dt.files;
                     input.dispatchEvent(new Event('change'));
                   }"""
            )
            page.wait_for_timeout(2500)
            check("the collision produced a suffixed note", "welcome-1.md" in page.inner_text("#current-path"),
                  page.inner_text("#current-path"))
            check("the original note was not overwritten", page.evaluate(
                """async () => {
                     const r = await fetch('/v2/proxy/marknest/notes?path=welcome.md',
                                           { credentials: 'include', headers: API.authHeaders() });
                     const body = await r.json();
                     return (body.data || {}).content.indexOf('Welcome to MarkNest') !== -1;
                   }"""))
```

Run: `python tools/verify_editor.py`
Expected: 两条都 PASS

- [ ] **Step 6: 提交**

```bash
git add webui/js/filepicker.js webui/index.html webui/css/style.css webui/js/app.js tools/webui_check.js tools/verify_editor.py
git commit -m "feat(webui): an open dialog for both the library and local files"
```

---

## Task 10: 文案（三语言）

**Files:**
- Modify: `webui/js/i18n.js`
- Test: `node tools/webui_check.js`（键集对齐）

- [ ] **Step 1: 写失败的断言**

无需新写——`webui_check.js` 的 i18n 键集对齐检查就是断言。加入文案后若三种语言不齐，它会报错。

- [ ] **Step 2: 运行，确认当前状态**

```bash
node tools/webui_check.js
```

预期：`ok   every dictionary defines the same keys`（此刻还没有新键）

- [ ] **Step 3: 实现**

在 `webui/js/i18n.js` 的三个字典里，各自加入下列键（`zh-cn` / `zh-hk` / `en-us` 各一份，键名完全相同）：

| 键 | zh-cn | zh-hk | en-us |
|---|---|---|---|
| `nav.home` | 主页 | 首頁 | Home |
| `nav.newNote` | 新建文件 | 新增檔案 | New file |
| `nav.openNote` | 打开文件 | 開啟檔案 | Open file |
| `nav.more` | 更多 | 更多 | More |
| `home.open` | 打开文件 | 開啟檔案 | Open file |
| `home.new` | 新建文件 | 新增檔案 | New file |
| `home.recent` | 最近文件 | 最近檔案 | Recent |
| `home.noRecent` | 还没有笔记 | 還沒有筆記 | No notes yet |
| `home.timeJustNow` | 刚刚 | 剛剛 | just now |
| `home.timeMinutes` | {n} 分钟前 | {n} 分鐘前 | {n} min ago |
| `home.timeHours` | {n} 小时前 | {n} 小時前 | {n} h ago |
| `home.timeYesterday` | 昨天 | 昨天 | yesterday |
| `home.timeDays` | {n} 天前 | {n} 天前 | {n} d ago |
| `picker.title` | 打开文件 | 開啟檔案 | Open a file |
| `picker.library` | 笔记库 | 筆記庫 | Library |
| `picker.local` | 本机文件 | 本機檔案 | This computer |
| `picker.browse` | 选择本机文件… | 選擇本機檔案… | Choose a file… |
| `picker.localHint` | 选择本机文件后将导入到笔记库，成为一篇普通笔记。 | 選擇本機檔案後將匯入筆記庫，成為一篇普通筆記。 | A file chosen here is imported into your library, where it becomes an ordinary note. |
| `picker.readFailed` | 无法读取该文件 | 無法讀取該檔案 | That file could not be read |
| `format.ariaLabel` | 格式工具栏 | 格式工具列 | Formatting |
| `format.bold` | 加粗 | 粗體 | Bold |
| `format.italic` | 斜体 | 斜體 | Italic |
| `format.code` | 行内代码 | 行內程式碼 | Inline code |
| `format.codeblock` | 代码块 | 程式碼區塊 | Code block |
| `format.quote` | 引用 | 引用 | Quote |
| `format.h1` | 一级标题 | 一級標題 | Heading 1 |
| `format.h2` | 二级标题 | 二級標題 | Heading 2 |
| `format.h3` | 三级标题 | 三級標題 | Heading 3 |
| `format.task` | 任务 | 待辦 | Task |
| `format.bullet` | 无序列表 | 無序清單 | Bullet list |
| `format.numbered` | 有序列表 | 有序清單 | Numbered list |
| `format.link` | 链接 | 連結 | Link |
| `format.table` | 表格 | 表格 | Table |
| `format.linkPrompt` | 链接地址 | 連結位址 | Link address |

- [ ] **Step 4: 运行，确认通过**

```bash
node tools/webui_check.js
```

预期：`i18n key parity: 3 dictionaries x N keys - identical`，`errors: 0`

- [ ] **Step 5: 提交**

```bash
git add webui/js/i18n.js
git commit -m "feat(i18n): strings for the home screen, the menu and the format bar"
```

---

## Task 11: 宿主几何扫描纳入新控件

**Files:**
- Modify: `tools/measure_topbar.py`

- [ ] **Step 1: 写失败的断言**

`measure_topbar.py` 的 `SCAN_JS` 选择器已经覆盖 `button` 与 `[tabindex]`，因此新按钮**自动**进入扫描。需要新增的是**主页与格式工具栏都要被扫到**——当前脚本只在 `note` 态扫一次。

把 `main()` 里扫描循环之前的一段改成扫两个状态：

```python
            # Both states get scanned: the home screen has its own buttons and
            # the format bar only exists once a note is open, so a scan of one
            # state says nothing about the other.
            print("Scanning %d widths in both the home and note states" % len(WIDTHS))
            print("-" * 62)
            for state_name in ("home", "note"):
                if state_name == "note":
                    page.click('.tree-row:has(.tree-name:text-is("welcome.md"))')
                    page.wait_for_timeout(700)
                else:
                    page.evaluate("() => { location.hash = '#/home'; }")
                    page.wait_for_timeout(700)

                for width in WIDTHS:
                    page.set_viewport_size({"width": width, "height": 720})
                    page.wait_for_timeout(350)
                    elements = page.evaluate(SCAN_JS)
                    zones = reserved(width, 720)
                    intrusions = []
                    for item in elements:
                        for name, zone in zones:
                            if intersects(item["box"], zone):
                                intrusions.append("%s %r" % (item["tag"], item["label"]))
                                break
                    check("%-4s %4dpx: %2d element(s), 0 in a host region"
                          % (state_name, width, len(elements)), not intrusions,
                          intrusions[:4])
```

并把原来的那段单状态循环整块删除。

- [ ] **Step 2: 运行，确认失败或通过**

```bash
python tools/measure_topbar.py
```

预期：**应当直接通过**——新控件都在顶栏下方。如果失败，说明某个控件落进了宿主带，**不要改断言去迁就，改布局**。

- [ ] **Step 3: 补救（仅当 Step 2 失败）**

若报出 `home` 或 `note` 态下有元素侵入，按侵入的元素调整：
- 主页按钮侵入 → `.home` 的 `padding-top` 从 `48px` 加到 `calc(var(--host-band-top) + 24px)`
- 格式工具栏侵入 → 不可能（它在顶栏之下），若报出说明是 `#more-menu` 被展开扫描到了，检查菜单是否在扫描时关闭

- [ ] **Step 4: 提交**

```bash
git add tools/measure_topbar.py
git commit -m "test(webui): scan both view states for host-band intrusions"
```

---

## Task 12: 版本、打包、真机

**Files:**
- Modify: `VERSION` 及 6 处派生字面量（由工具同步）
- Modify: `_ops/_live_verify_marknest.py`

- [ ] **Step 1: 递增版本**

```bash
python tools/bump_version.py --bump patch
python tools/bump_version.py --check
```

预期：`VERSION: 1.0.2 -> 1.0.3`；`--check` → `RESULT: PASSED`

- [ ] **Step 2: 全套离线校验**

```bash
python tools/validate.py
python tools/selftest.py
node tools/webui_check.js
python tools/lang_stats.py
python tools/webui_build.py --check
python tools/verify_editor.py
python tools/measure_topbar.py
```

预期：全部退出码 0。`lang_stats.py` 仍会报 11 种未翻译（既有状态，非本次引入）。

- [ ] **Step 3: 打包**

```bash
python tools/build.py --platform x86_64
```

预期：`dist/marknest_x86_64.deb`，`package inspection passed`

- [ ] **Step 4: 真机部署**

```bash
export PRINT_HOST=<设备> PRINT_PORT=<端口> PRINT_USER=<用户> PRINT_PASS=<口令>
export PRINT_WEB=http://<设备>:8181 PRINT_WEB_USER=<用户> PRINT_WEB_PASS=<口令>
python _ops/_deploy.py
```

预期：`/health` 报 `status: ok`、`library_ready: true`；前端 14 个文件零差异

- [ ] **Step 5: 真机端到端**

```bash
python _ops/_live_verify_marknest.py
```

预期：全部 PASS。若主页断言失败，先看截图 `_scratch/_mn_11_app.png`。

- [ ] **Step 6: 提交并推送**

```bash
git add -A
git commit -m "chore(release): 1.0.3 - home screen and format toolbar"
git push
```

---

## 完成标准

- [ ] `python tools/selftest.py` → 61 项通过（原 51 + recent 10）
- [ ] `node tools/webui_check.js` → 0 错误，含 13 条命令断言 + 8 条切换断言
- [ ] `python tools/verify_editor.py` → 全部通过，含主页、菜单、导入三节
- [ ] `python tools/measure_topbar.py` → home 与 note 两个状态、8 个宽度全部零相交
- [ ] `python tools/validate.py` → 73 项通过、0 错误、0 警告
- [ ] 真机 `_ops/_live_verify_marknest.py` 全部 PASS
- [ ] `git push` 成功，GitHub 上是 1.0.3
