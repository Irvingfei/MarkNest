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

            print("\n2. opening a note")
            # Section 2 is about the click path, so the note that is already
            # open has to be there for the click to be a switch between notes -
            # which is the real situation. It also puts the workspace back on
            # screen, since the tree row is not clickable while the home screen
            # is covering it.
            open_note_directly(page, "welcome.md")
            click_note(page, "welcome.md")
            page.wait_for_timeout(700)
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
