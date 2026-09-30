#!/usr/bin/env python3
"""Verify the MarkNest editor in a real browser.

Drives the actual WebUI and the actual editor bundle against the stub API, so
what is checked is the behaviour a person would get, not a description of it.
The assertions that matter most are the ones a stub cannot fake:

  * a note containing ``<script>`` does not execute - note content is untrusted
    input, and sanitisation is the only thing standing between a note written
    over SMB and the application's own origin;
  * a save carries the revision it loaded, and a note changed underneath the
    editor produces a conflict rather than a silent overwrite;
  * scrolling one pane moves the other, by line rather than by proportion.

Usage:
    <python> tools/verify_editor.py
"""

import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import webui_harness as H  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

failures = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", label,
                           "" if condition else "  -> %s" % (detail,)))
    if not condition:
        failures.append(label)
    return bool(condition)


def first_difference(before, after):
    """Where two renderings first disagree, for a failure detail that reads.

    "The strings are not equal" says the check failed but not what moved. The
    preview is one long HTML string, so pointing at the first differing
    character - with a little either side - is the difference between a failed
    assertion and an answer.
    """
    limit = min(len(before), len(after))
    for index in range(limit):
        if before[index] != after[index]:
            start = max(0, index - 24)
            return "%d: %r -> %r" % (
                index, before[start:index + 24], after[start:index + 24])
    if len(before) != len(after):
        start = max(0, limit - 24)
        return "%d (length %d -> %d): %r -> %r" % (
            limit, len(before), len(after), before[start:], after[start:])
    return "identical (%d chars)" % len(before)


def click_note(page, name):
    """Click a tree row by its exact name.

    ``:has-text`` matches substrings, so a search for "notes" also matches
    "notes.md" and the wrong row gets clicked. The name is matched exactly,
    against the row's ``.tree-name`` rather than its whole text, which also
    carries the expand caret.
    """
    page.click('.tree-row:has(.tree-name:text-is("%s"))' % name)


def open_note_directly(page, path):
    """Put the application into the note view for a path, without the UI.

    The sections after the first are about the editor, the preview and the
    toolbar - not about how a note is reached. Driving them through the home
    screen would make every one of them depend on the file picker, which does
    not exist yet at this point in the plan. The path in the hash is the
    application's own supported way to address a note, so this is the honest
    shortcut rather than a workaround.
    """
    page.evaluate(
        "(p) => { location.hash = '#/notes?p=' + encodeURIComponent(p); }", path)
    page.wait_for_timeout(900)


def app_note_visible(page, selector):
    """Visibility inside whichever frame currently holds the application."""
    for frame in page.frames:
        if "/marknest/" in frame.url:
            try:
                return frame.is_visible(selector)
            except Exception:  # noqa: BLE001
                return False
    return page.is_visible(selector)


def main():
    httpd, port = H.serve()
    url = "http://127.0.0.1:%d/index.html" % port
    state = H.new_state()
    api = state["api"]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 800},
                                          locale="zh-CN")
            context.route(H.PROXY_GLOB, H.make_router(state))
            page = context.new_page()
            console_errors = []
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))

            print("1. the application boots")
            H.boot_page(page, url)
            check("the shell rendered", page.evaluate(
                "() => !!document.querySelector('.workspace')"))
            check("the editor bundle loaded", page.evaluate(
                "() => typeof window.MDEditor === 'object'"))
            check("the tree listed the notes", "welcome.md" in page.inner_text("#tree-body"),
                  page.inner_text("#tree-body")[:120])
            check("no uncaught error during boot", not console_errors, console_errors[:2])
            # The other half of "only in the note view": the bar appears with a
            # note, and it must therefore not be there without one. Asserted
            # before section 2 opens anything.
            check("the format bar is hidden until a note is open",
                  not app_note_visible(page, "#format-bar"))

            print("\n1c. the application starts on its home screen")
            check("home is the initial view", page.evaluate(
                "() => document.getElementById('workspace').classList.contains('is-home')"))
            check("the editor is not shown yet", page.evaluate(
                "() => document.getElementById('pane-editor').offsetParent === null"))
            check("the hash says home", page.evaluate("() => location.hash") == "#/home",
                  page.evaluate("() => location.hash"))
            check("the home screen is visible", page.evaluate(
                "() => !document.getElementById('home').hidden"))

            print("\n1d. the home actions stack on a narrow frame")
            page.set_viewport_size({"width": 560, "height": 700})
            page.wait_for_timeout(400)
            boxes = page.evaluate("""() => {
                const open = document.getElementById('home-open').getBoundingClientRect();
                const created = document.getElementById('home-new').getBoundingClientRect();
                return {openTop: open.top, newTop: created.top,
                        openLeft: open.left, newLeft: created.left};
            }""")
            check("the two home buttons stack vertically rather than side by side",
                  boxes["newTop"] > boxes["openTop"] + 8, boxes)
            page.set_viewport_size({"width": 1280, "height": 800})
            page.wait_for_timeout(400)

            print("\n1e. the home screen lists recent notes")
            check("both home actions are offered", page.evaluate(
                "() => !!document.getElementById('home-open') && !!document.getElementById('home-new')"))
            # Translated, not the key name. The two buttons rendered "home.open"
            # and "home.new" on screen from Task 6 until these strings landed,
            # and nothing failed: webui_check.js compares the three dictionaries
            # against each other and never against what the code references, so
            # a key missing from all three passes it. This is the only place
            # that would notice the strings going away again.
            check("the home buttons are translated, not raw keys", page.evaluate(
                "() => { var b = document.getElementById('home-open');"
                " return !!b && b.textContent.indexOf('home.') !== 0; }"),
                page.evaluate("() => (document.getElementById('home-open')||{}).textContent"))
            page.wait_for_timeout(800)
            recent = page.inner_text("#home-recent")
            check("the recent list names a note", "welcome.md" in recent, recent[:160])
            check("it shows a relative time rather than an empty cell",
                  "分钟前" in recent or "前" in recent, recent[:160])

            # Spec §11 item 3 requires the list to be ordered by modification
            # time, and requires an entry to open its note. Neither is implied by
            # finding the name in the text: a list in any order contains it.
            order = page.evaluate("""() => Array.from(
                document.querySelectorAll('#home-recent .home-recent-item'))
                .map(function (node) { return node.textContent; })""")
            check("the newest note is listed first",
                  order and "welcome.md" in order[0], order)
            check("more than one note is listed, so the order means something",
                  len(order) > 1, order)

            # The click is guarded rather than fired blindly. With no row to
            # click - which is the state of the pre-task tree, and of any build
            # whose home screen is broken - page.click() raises a TimeoutError,
            # and that exception takes sections 2 to 11 down with it. A broken
            # home screen should leave a readable failure list, not an unhandled
            # exception that hides every section after this one.
            items = page.evaluate(
                "() => document.querySelectorAll('#home-recent .home-recent-item').length")
            if items:
                page.click("#home-recent .home-recent-item")
                page.wait_for_timeout(900)
            check("clicking a recent note opens it",
                  bool(items) and "welcome.md" in page.inner_text("#current-path"),
                  page.inner_text("#current-path") if items else "no recent item to click")
            check("and the application leaves the home screen",
                  bool(items) and page.evaluate(
                      "() => !document.getElementById('workspace').classList.contains('is-home')"),
                  "" if items else "no recent item to click")

            print("\n1f. the more menu")
            # Both nodes, looked up once, and every click below is guarded by
            # the result. page.click() on an element that does not exist raises
            # a TimeoutError, and that exception takes sections 2 to 11 down
            # with it - a missing menu should leave a readable failure list,
            # for the same reason the recent-item click above is guarded.
            has_menu = page.evaluate(
                "() => !!document.getElementById('btn-more') "
                "&& !!document.getElementById('more-menu')")
            # Existence as well as visibility. is_visible() is false for a node
            # that was never built, so a bare negation reports a menu that was
            # never implemented as a menu that is correctly shut - which is how
            # this line passed against a tree with no menu on it at all.
            check("the menu is closed until asked for",
                  has_menu and not page.is_visible("#more-menu"))
            if has_menu:
                page.click("#btn-more")
                page.wait_for_timeout(300)
            check("pressing it opens the menu",
                  has_menu and page.is_visible("#more-menu"))
            items = page.inner_text("#more-menu") if has_menu else ""
            for expected in ("主页", "新建文件", "打开文件"):
                check("the menu offers %s" % expected, expected in items, items[:120])
            check("the old plus button is gone", page.evaluate(
                "() => !document.getElementById('btn-new-note')"))
            if has_menu:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
            check("escape closes it", has_menu and not page.is_visible("#more-menu"))

            # Spec §11 item 5. The home screen is reachable from the note view
            # only through this menu item, so this is the one place the two
            # halves of the state machine meet a real gesture.
            open_note_directly(page, "welcome.md")
            check("a note is open before the menu is used again", page.evaluate(
                "() => !document.getElementById('workspace').classList.contains('is-home')"))
            if has_menu:
                page.click("#btn-more")
                page.wait_for_timeout(300)
                page.click("#more-home")
                page.wait_for_timeout(600)
            check("the menu's home item returns to the home screen",
                  has_menu and page.evaluate(
                      "() => document.getElementById('workspace').classList.contains('is-home')"))
            check("and the fragment says so",
                  has_menu and page.evaluate("() => location.hash") == "#/home",
                  page.evaluate("() => location.hash"))

            # The item that replaced ＋. Nothing else offline clicks it: the
            # device script does, and that needs a device. The name is injected
            # rather than typed into the dialog, the way the device script
            # injects it - the library is the filesystem, so a fixed name
            # collides with what a previous run left behind, the create is
            # refused, and the check would fail for a reason that is not the
            # code's.
            if has_menu:
                page.evaluate("""() => {
                    window.__realPrompt = window.prompt;
                    window.prompt = () => 'menu-created.md';
                }""")
                page.click("#btn-more")
                page.wait_for_timeout(300)
                page.click("#more-new")
                page.wait_for_timeout(900)
                # The real prompt goes back immediately: section 11 asks for a
                # link address through prompt(), and a stub left in place would
                # answer that question with a filename. Restoring beats
                # installing a dialog handler here, which would still be
                # registered when section 11 installs its own.
                page.evaluate("() => { window.prompt = window.__realPrompt; }")
            check("the menu's new-file item creates a note", has_menu and
                  "menu-created.md" in page.inner_text("#current-path"),
                  page.inner_text("#current-path"))
            check("and the tree gained it", has_menu and
                  "menu-created.md" in page.inner_text("#tree-body"),
                  page.inner_text("#tree-body")[:120])

            print("\n2. opening a note")
            # Section 2 is about the click path, so the note that is already
            # open has to be there for the click to be a switch between notes -
            # which is the real situation. It also puts the workspace back on
            # screen, since the tree row is not clickable while the home screen
            # is covering it.
            open_note_directly(page, "welcome.md")

            # The tree row is the only way a person opens a note by name, and it
            # was refusing every one of them. treepane's click guard asked for a
            # `type` of 'note'; library.py has never sent that value - it sends
            # 'file' for a note and 'other' for a file it will not open, and
            # answers "is this a note?" with the separate `note` boolean. The stub
            # sent the shape the frontend wanted, so the two agreed with each
            # other and with neither the backend nor a device, and no other
            # section noticed because every one of them opens its note by address.
            #
            # Both ends are read, so the pair cannot drift apart quietly: the
            # entry is the stub's own answer, fetched through the same endpoint
            # and credentials the tree uses, and the second check is the tree
            # acting on it. If the stub stops answering the way library.py does,
            # the first check fails; if the tree stops honouring that answer, the
            # second one does - which is exactly what it did here.
            entry = page.evaluate("""async () => {
                const r = await fetch('/v2/proxy/marknest/tree',
                                      { credentials: 'include', headers: API.authHeaders() });
                const body = await r.json();
                return ((body.data || {}).entries || []).filter(
                    (e) => e.name === 'welcome.md')[0] || null;
            }""")
            check("the stub serves a note the way library.py does (type 'file', note true)",
                  bool(entry) and entry.get("type") == "file" and entry.get("note") is True,
                  entry)

            # Counted through the request the click causes, not through what the
            # editor holds: the shortcut above already put welcome.md there, so
            # reading the editor back would pass even if the click did nothing -
            # the mistake section 8's comment records.
            before = len(state["requests"])
            click_note(page, "welcome.md")
            page.wait_for_timeout(700)
            reopened = [r for r in state["requests"][before:]
                        if r[1].endswith("/notes")
                        and (r[2].get("path") or [""])[0] == "welcome.md"]
            check("clicking a note in the tree opens it", len(reopened) == 1,
                  "the click sent %d read(s) of welcome.md" % len(reopened))
            check("the editor holds the note", page.evaluate(
                "() => { var cm = document.querySelector('.cm-content');"
                " return !!cm && cm.textContent.indexOf('Welcome to MarkNest') !== -1; }"))
            check("the preview rendered it", page.evaluate(
                "() => { var h = document.querySelector('#preview-body h1');"
                " return !!h && h.textContent.indexOf('Welcome') !== -1; }"))
            check("the path is shown", "welcome.md" in page.inner_text("#current-path"),
                  page.inner_text("#current-path"))
            check("the open note is in the URL fragment, so a reload restores it",
                  "welcome.md" in page.evaluate("() => location.hash"),
                  page.evaluate("() => location.hash"))

            print("\n3. the preview follows the editor")
            page.click(".cm-content")
            page.keyboard.press("Control+End")
            page.keyboard.type("\n\nappended from the test\n")
            page.wait_for_timeout(600)
            check("the typing reached the preview", page.evaluate(
                "() => document.getElementById('preview-body').textContent"
                ".indexOf('appended from the test') !== -1"))

            print("\n4. block elements carry the source line (scroll sync needs it)")
            check("headings carry data-line", page.evaluate(
                "() => document.querySelectorAll('#preview-body [data-line]').length > 3"),
                page.evaluate("() => document.querySelectorAll('#preview-body [data-line]').length"))

            print("\n4b. the format toolbar edits through the editor")
            check("the format bar appears once a note is open",
                  app_note_visible(page, "#format-bar"))
            check("all thirteen buttons are present", page.evaluate(
                "() => document.querySelectorAll('#format-bar .format-btn').length") == 13,
                page.evaluate("() => document.querySelectorAll('#format-bar .format-btn').length"))
            check("the tooltips are translated, not raw keys", page.evaluate(
                "() => { var b = document.getElementById('fmt-bold');"
                " return !!b && b.getAttribute('title').indexOf('format.') !== 0; }"),
                page.evaluate("() => (document.getElementById('fmt-bold')||{}).title"))
            # The dirty flag is cleared before anything is asserted about it.
            # Section 3 typed into the note and never saved, so "the editor is
            # dirty" was already true on arrival and a press that did nothing
            # satisfied it. The save leaves section 5 alone: it counts the saves
            # in a slice of the request log it snapshots after this point.
            page.click("#btn-save")
            page.wait_for_timeout(800)
            check("the toolbar starts from a clean editor", page.evaluate(
                "() => document.getElementById('dirty-dot').hidden") is True)

            # The rendered preview is snapshotted rather than searched for a
            # <strong>. welcome.md already contains **Markdown**, so one is
            # present before the press; the wrapping does not even add another,
            # because emphasis cannot span the block boundaries of the whole
            # document. The comparison below is what actually depends on the
            # edit.
            before_preview = page.evaluate(
                "() => document.getElementById('preview-body').innerHTML")

            page.click(".cm-content")
            page.keyboard.press("Control+a")
            page.wait_for_timeout(200)
            page.click("#fmt-bold")
            # schedule() renders 150ms after the last change; four times that is
            # slack for a slow first paint, not a race being papered over.
            page.wait_for_timeout(700)

            # Both ends, not a substring: the note already carried '**' before
            # the press, so a presence check could not fail.
            check("the bold command wrapped the document", page.evaluate(
                "() => { var t = document.querySelector('.cm-content').textContent;"
                " return t.slice(0, 2) === '**' && t.slice(-2) === '**'; }"),
                page.evaluate(
                    "() => { var t = document.querySelector('.cm-content').textContent;"
                    " return JSON.stringify([t.slice(0, 2), t.slice(-2)]); }"))
            # The transition is the evidence that the edit travelled through
            # CodeMirror's transaction path; a flag left over from earlier
            # typing is not.
            check("the edit marked the editor dirty", page.evaluate(
                "() => document.getElementById('dirty-dot').hidden === false"))
            after_preview = page.evaluate(
                "() => document.getElementById('preview-body').innerHTML")
            check("the preview was re-rendered", before_preview != after_preview,
                  first_difference(before_preview, after_preview))

            print("\n5. saving")
            before = len(state["requests"])
            page.click("#btn-save")
            page.wait_for_timeout(800)
            saves = [r for r in state["requests"][before:] if r[1].endswith("/notes/save")]
            check("a save was sent", len(saves) == 1, len(saves))
            check("the save carries a revision", api.notes["welcome.md"].find("appended") != -1,
                  api.notes["welcome.md"][:60].replace("\n", " "))
            check("the editor is no longer marked dirty", page.evaluate(
                "() => document.getElementById('dirty-dot').hidden") is True)

            print("\n6. a note changed underneath the editor conflicts")
            # Somebody else writes the file - over SMB, from the File Manager -
            # and the revision the browser holds is now stale.
            api.notes["welcome.md"] = "# Changed elsewhere\n"
            api.touch("welcome.md")
            page.click(".cm-content")
            page.keyboard.type("x")
            page.wait_for_timeout(300)
            page.click("#btn-save")
            page.wait_for_timeout(900)
            check("a conflict banner is shown", page.evaluate(
                "() => !!document.getElementById('editor-banner')"))
            check("the other writer's content survived", api.notes["welcome.md"] == "# Changed elsewhere\n",
                  api.notes["welcome.md"][:40])
            check("three ways out are offered", page.evaluate(
                "() => document.querySelectorAll('#editor-banner .btn').length") == 3)

            print("\n7. note content cannot execute")
            api.notes["injection.md"] = H.RAW_HTML_NOTE
            api.touch("injection.md")
            page.evaluate("() => { document.getElementById('tree-body').innerHTML = ''; }")
            page.reload(wait_until="load")
            page.wait_for_timeout(1200)
            page.evaluate(
                "() => { window.__pwned = false; }")
            click_note(page, "injection.md")
            page.wait_for_timeout(800)
            check("a <script> inside a note did not run", page.evaluate(
                "() => window.__pwned === false"), page.evaluate("() => window.__pwned"))
            check("no <script> element reached the preview", page.evaluate(
                "() => document.querySelectorAll('#preview-body script').length") == 0)
            check("the onerror attribute was stripped", page.evaluate(
                "() => document.querySelectorAll('#preview-body [onerror]').length") == 0)

            print("\n8. scroll synchronisation, both directions")
            page.reload(wait_until="load")
            page.wait_for_timeout(1200)
            # long.md lives in a subfolder, which the tree would reach only by
            # expanding it a directory at a time. The scroll assertions are not
            # about the tree, so the note is addressed the way the application
            # itself addresses one.
            open_note_directly(page, "notes/long.md")

            # The shortcut above had removed the only exercise of the tree's
            # directory expansion: click_note is otherwise called for root-level
            # notes only, so "expand a folder, then click the note inside it"
            # was tested nowhere. The click path comes back here.
            #
            # What is asserted is the fetch the click causes, not the content:
            # the editor already holds long.md from the shortcut, so reading it
            # back would pass even if the click did nothing at all.
            before = len(state["requests"])
            click_note(page, "notes")
            page.wait_for_timeout(600)
            click_note(page, "long.md")
            page.wait_for_timeout(900)
            reopened = [r for r in state["requests"][before:]
                        if r[1].endswith("/notes")
                        and (r[2].get("path") or [""])[0] == "notes/long.md"]
            check("expanding a folder and clicking a note in it opens that note",
                  len(reopened) == 1, len(reopened))
            # The first line rather than a later section: CodeMirror renders
            # only the lines in view, and long.md is long enough that anything
            # past the fold is not in the DOM to be read.
            check("the editor holds the note the tree click opened", page.evaluate(
                "() => { var cm = document.querySelector('.cm-content');"
                " return !!cm && cm.textContent.indexOf('Long note') !== -1; }"))
            page.evaluate(
                "() => { var s = document.querySelector('.cm-scroller'); s.scrollTop = s.scrollHeight / 2; s.dispatchEvent(new Event('scroll')); }")
            page.wait_for_timeout(400)
            preview_scrolled = page.evaluate(
                "() => document.getElementById('preview-body').scrollTop")
            check("scrolling the editor moved the preview", preview_scrolled > 50,
                  preview_scrolled)

            page.evaluate(
                "() => { var p = document.getElementById('preview-body'); p.scrollTop = p.scrollHeight * 0.8; p.dispatchEvent(new Event('scroll')); }")
            page.wait_for_timeout(400)
            editor_scrolled = page.evaluate(
                "() => document.querySelector('.cm-scroller').scrollTop")
            check("scrolling the preview moved the editor", editor_scrolled > 50,
                  editor_scrolled)

            print("\n9. search")
            page.fill("#search-box", "Section 30")
            page.wait_for_timeout(900)
            body = page.inner_text("#tree-body")
            check("a search lists matching notes", "long.md" in body, body[:120])

            print("\n9b. the tree's context menu runs the item it is given")
            # The menu is detached from the document by the mousedown that
            # precedes the click. A detached mousedown target and a mouseup
            # target outside it share no inclusive ancestor, so the browser
            # dispatches no click event at all and the item's handler never
            # runs: 重命名 and 删除 did nothing on a real click, while a
            # synthetic click on the same button worked.
            #
            # What is asserted is therefore that the handler was entered, not
            # that the tree changed. A cancelled rename leaves the tree exactly
            # as it was, so the tree cannot tell "ran, and the answer was
            # empty" from "never ran" - which is the mistake this assertion
            # exists to avoid making.
            #
            # The search box is emptied first: a search renders .hit rows
            # rather than .tree-row ones, and the tree row is what carries the
            # contextmenu handler.
            page.fill("#search-box", "")
            page.wait_for_timeout(700)
            menu_row = '.tree-row:has(.tree-name:text-is("long.md"))'
            # Counted through the same selector engine click_note uses:
            # :has() and :text-is() are Playwright's, not the DOM's, and
            # document.querySelector rejects them.
            has_row = page.locator(menu_row).count() > 0
            if has_row:
                page.click(menu_row, button="right")
                page.wait_for_timeout(300)
            first_open = has_row and page.evaluate(
                "() => !!document.getElementById('tree-menu')")
            check("right-clicking a tree row opens the context menu", first_open)

            if first_open:
                # The prompts are replaced rather than answered through a
                # dialog listener: treepane calls window.prompt and
                # window.confirm directly, the recorder is what proves the
                # handler was entered, and nothing is left registered for
                # section 11's link prompt to trip over. Cancelling both is
                # also what keeps this section from renaming or deleting
                # anything.
                page.evaluate("""() => {
                    window.__realPrompt = window.prompt;
                    window.__realConfirm = window.confirm;
                    window.__asked = { rename: 0, remove: 0 };
                    window.prompt = () => { window.__asked.rename += 1; return null; };
                    window.confirm = () => { window.__asked.remove += 1; return false; };
                }""")
                page.click("#tree-menu .ctx-item")
                page.wait_for_timeout(400)
                check("a real click on 重命名 reaches its handler",
                      page.evaluate("() => window.__asked.rename") == 1,
                      page.evaluate("() => window.__asked"))
                check("and choosing it closed the menu", page.evaluate(
                    "() => !document.getElementById('tree-menu')"))

                if has_row:
                    page.click(menu_row, button="right")
                    page.wait_for_timeout(300)
                second_open = has_row and page.evaluate(
                    "() => !!document.getElementById('tree-menu')")
                if second_open:
                    page.click("#tree-menu .ctx-item.is-danger")
                    page.wait_for_timeout(400)
                check("a real click on 删除 reaches its handler",
                      second_open and page.evaluate(
                          "() => window.__asked.remove") == 1,
                      page.evaluate("() => window.__asked"))
                page.evaluate("""() => {
                    window.prompt = window.__realPrompt;
                    window.confirm = window.__realConfirm;
                }""")

            print("\n10. the three host bands stay clear and the layout adapts")
            page.fill("#search-box", "")
            page.wait_for_timeout(400)
            page.set_viewport_size({"width": 760, "height": 700})
            page.wait_for_timeout(500)
            check("the preview collapses on a narrow frame", page.evaluate(
                "() => document.getElementById('workspace').classList.contains('is-no-preview')"))
            page.set_viewport_size({"width": 560, "height": 700})
            page.wait_for_timeout(500)
            check("the tree collapses on a narrower one", page.evaluate(
                "() => document.getElementById('workspace').classList.contains('is-no-tree')"))

            print("\n11. every format button calls its own command")
            # Last, because thirteen commands rewrite the document and nothing
            # after this needs it intact. The viewport goes back to its normal
            # size so the whole bar is on screen and none of the buttons has to
            # be scrolled to inside an overflow container to be clicked.

            # A dialog handler has to be installed before the link button is
            # pressed: Playwright dismisses an unhandled dialog automatically,
            # prompt() then returns null, and the link command - which asks
            # twice when there is no selection - would never fire, failing the
            # check for a reason that has nothing to do with the wiring.
            page.on("dialog", lambda dialog: dialog.accept("https://example.com"))

            page.set_viewport_size({"width": 1280, "height": 800})
            page.wait_for_timeout(300)

            # Each command is wrapped rather than replaced, so a correctly
            # wired button still edits the document. The wrapper records the
            # name it was reached by, which is the thing under test.
            #
            # The originals are copied into `real` before anything is
            # overwritten. Holding a second reference to the live object is not
            # enough: `live[name] = wrapper` would make `real[name]` the wrapper
            # too, and every press would recurse until the stack ran out.
            page.evaluate("""() => {
                window.__fired = [];
                const live = window.MDCmd.commands;
                const real = {};
                Object.keys(live).forEach(function (name) { real[name] = live[name]; });
                Object.keys(real).forEach(function (name) {
                  live[name] = function () {
                    window.__fired.push(name);
                    return real[name].apply(null, arguments);
                  };
                });
              }""")

            # Iterating the expected names and requiring exactly that one
            # covers both a transposed command and a row whose `id` and
            # `command` disagree - GROUPS repeats the same value in all
            # thirteen rows and nothing else checks they stay equal.
            for name in ("bold", "italic", "code", "codeblock", "quote", "h1", "h2",
                         "h3", "task", "bullet", "numbered", "link", "table"):
                page.evaluate("() => { window.__fired = []; }")
                page.click("#fmt-" + name)
                page.wait_for_timeout(150)
                fired = page.evaluate("() => window.__fired")
                check("%s calls %s and nothing else" % (name, name),
                      fired == [name], fired)

            print("\n12. opening a file from either source")
            # Spec §11 items 8 and 9. The picker offers the library and the
            # machine's own disk; a file from the disk is *imported* rather than
            # merely opened - the library is the only place a note lives, so
            # "open" has to mean "bring it in" - and a name the library already
            # holds is suffixed instead of overwritten.
            #
            # Every click below is guarded, for the reason sections 1e and 1f
            # give: page.click() on an element that does not exist raises a
            # TimeoutError, and that exception is not a check result - it takes
            # everything after it down with it. A missing picker should leave a
            # readable list of failures, not an unhandled exception.
            page.evaluate("() => { location.hash = '#/home'; }")
            page.wait_for_timeout(700)
            has_open = page.evaluate("() => !!document.getElementById('home-open')")
            if has_open:
                page.click("#home-open")
                page.wait_for_timeout(700)
            picker_open = page.is_visible("#file-picker")
            check("the picker opens", picker_open)
            # Read only when it is there: inner_text() raises on a missing node.
            tabs = page.inner_text("#file-picker") if picker_open else ""
            check("it offers the library", "笔记库" in tabs, tabs[:160])
            check("it offers local files", "本机" in tabs, tabs[:160])

            # The library tab filters the same entries the tree does, and it
            # now asks the same question of them - the backend's `note` boolean
            # rather than a `type` literal. A folder is false for that boolean
            # too, so a filter that dropped everything non-note would empty the
            # list of the folders a person needs to reach a nested note, and
            # nothing else here would notice: no other section clicks a folder
            # inside the picker.
            rows = page.evaluate("""() => Array.from(
                document.querySelectorAll('#picker-body .tree-name'))
                .map((node) => node.textContent)""") if picker_open else []
            check("the library tab lists the folder as well as the notes",
                  "notes" in rows and "welcome.md" in rows, rows)

            def hand_to_picker(name, content):
                """Give the picker's file input a File, as a real dialog would.

                A synthetic change event is the only way to reach the import
                without a native dialog. The input and the handler it fires are
                the same ones a person's file dialog reaches, and the handler is
                bound for the document's lifetime rather than only while the
                dialog is on screen, so the gesture works from either state.
                """
                page.evaluate(
                    """([name, content]) => {
                         const dt = new DataTransfer();
                         dt.items.add(new File([content], name, { type: 'text/markdown' }));
                         const input = document.getElementById('picker-file');
                         input.files = dt.files;
                         input.dispatchEvent(new Event('change'));
                       }""",
                    [name, content])

            # Spec §7 also puts the type check in the frontend, not only in the
            # file dialog's accept list: 所有文件 is one click away, and a binary
            # imported as a note is a garbled note. A .png is the file a person
            # actually has to hand in this situation - the accept list is
            # precisely what they overrode to get here.
            notes_before = len(api.notes)
            if picker_open:
                hand_to_picker("picture.png", "\x89PNG not really a png")
                page.wait_for_timeout(1500)
            check("a file of a rejected type imported nothing",
                  picker_open and len(api.notes) == notes_before,
                  "library went from %d to %d note(s)" % (notes_before, len(api.notes)))

            if picker_open:
                hand_to_picker("imported-by-test.md", "# Imported\n\nfrom the test\n")
                page.wait_for_timeout(2500)
            path_text = page.inner_text("#current-path")
            check("the imported note opened", "imported-by-test.md" in path_text, path_text)
            # The library is checked through the same GET the editor uses, not
            # through the stub's dictionary: an import that wrote to the wrong
            # place would still fill the dictionary.
            check("and it is in the library now", page.evaluate(
                """async () => {
                     const r = await fetch('/v2/proxy/marknest/notes?path=imported-by-test.md',
                                           { credentials: 'include', headers: API.authHeaders() });
                     return r.status === 200;
                   }"""))

            # The second import carries a name the library already holds. The
            # stub answers 3006, which is what the retry path keys off; what is
            # asserted is the outcome - a suffixed note - and that the note that
            # was already there still holds its own content. The original is read
            # back rather than searched for a phrase: an earlier section replaced
            # welcome.md's body, so a phrase check here would assert the wrong
            # thing and would fail for that reason rather than this one.
            original_welcome = api.notes.get("welcome.md", "")
            if picker_open:
                # Reopened without arguments on purpose: this is the call the
                # home screen's button and the menu item make, and the import
                # has to open what it imported with no callback passed in.
                page.evaluate("() => { window.FilePicker.open(); }")
                page.wait_for_timeout(300)
                hand_to_picker("welcome.md", "# Second\n")
                page.wait_for_timeout(2500)
            collision_text = page.inner_text("#current-path")
            check("the collision produced a suffixed note",
                  "welcome-1.md" in collision_text, collision_text)
            check("the original note was not overwritten",
                  api.notes.get("welcome.md", "") == original_welcome,
                  api.notes.get("welcome.md", "")[:60].replace("\n", " "))
            check("and the colliding file became a note of its own",
                  api.notes.get("welcome-1.md") == "# Second\n",
                  api.notes.get("welcome-1.md"))

            browser.close()
    finally:
        httpd.shutdown()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: the editor opens, previews, saves with conflict detection,")
    print("        refuses to execute note content, and scroll-syncs both ways.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
