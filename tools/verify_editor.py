#!/usr/bin/env python3
"""Verify the MarkNest reading and editing surfaces in a real browser.

Drives the actual WebUI and the actual editor bundle against the stub API, so
what is checked is the behaviour a person would get, not a description of it.
The assertions that matter most are the ones a stub cannot fake:

  * a note containing ``<script>`` does not execute - note content is untrusted
    input, and sanitisation is the only thing standing between a note written
    over SMB and the application's own origin;
  * attachments travel through the authenticated proxy and arrive as object
    URLs, so both the reader and the editor preview show the image;
  * a save carries the revision it loaded, and a note changed underneath the
    editor produces a conflict banner rather than a silent overwrite;
  * the toolbar edits the document through the editor's own dispatch, and the
    outline and preview follow without a second parser;
  * scrolling one pane moves the other.

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


def open_route(page, route_hash, marker, wait=420):
    page.evaluate("(hash) => { location.hash = hash; }", route_hash)
    # ``hashchange`` is delivered asynchronously, so the previous page's DOM is
    # still on screen for a moment. Waiting a beat first keeps a read->read
    # navigation from satisfying the marker with the outgoing note.
    page.wait_for_timeout(350)
    page.wait_for_selector(marker, timeout=8000)
    page.wait_for_timeout(wait)


def editor_text(page):
    return page.evaluate(
        "() => { var cm = document.querySelector('.cm-content');"
        " return cm ? cm.textContent : ''; }")


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
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            print("1. the application boots into the library")
            H.boot_page(page, url)
            page.wait_for_selector(".page-library .note-card", timeout=8000)
            check("the shell rendered", page.evaluate(
                "() => !!document.querySelector('.app > .sidebar') && "
                "!!document.querySelector('.app > .main > #view')"))
            check("the editor bundle loaded", page.evaluate(
                "() => typeof window.MDEditor === 'object'"))
            check("the library listed the notes", "welcome.md" in
                  page.inner_text("#library-body"),
                  page.inner_text("#library-body")[:120])
            check("the card is titled with the file name, not the heading",
                  page.inner_text(".note-card-title").strip() == "welcome.md",
                  page.inner_text(".note-card-title"))
            check("no uncaught error during boot", not errors, errors[:2])

            print("\n2. the reader opens a note")
            page.click('.note-card:has(.note-card-title:text-is("welcome.md"))')
            page.wait_for_selector(".page-reader .prose h1", timeout=8000)
            page.wait_for_timeout(400)
            check("the title is typeset", page.inner_text(".reader-title") ==
                  "Welcome to MarkNest", page.inner_text(".reader-title"))
            check("the note path is in the URL fragment, so a reload restores it",
                  "read" in page.evaluate("() => location.hash") and
                  "welcome.md" in page.evaluate("() => location.hash"),
                  page.evaluate("() => location.hash"))
            check("the outline lists the headings",
                  page.locator(".reader-toc a").count() >= 2,
                  page.locator(".reader-toc a").count())
            check("a reading-progress hairline exists",
                  page.locator("#reader-progress-fill").count() == 1)
            check("the footer names the file", "welcome.md" in
                  page.inner_text(".reader-foot"), page.inner_text(".reader-foot"))

            print("\n3. an attachment image is fetched through the proxy")
            open_route(page, "#/read?p=notes/pictures.md", ".page-reader .prose img")
            page.wait_for_function(
                "() => { var img = document.querySelector('.page-reader .prose img');"
                " return !!img && img.classList.contains('is-loaded') &&"
                " /^blob:/.test(img.getAttribute('src') || ''); }",
                timeout=6000)
            check("the image became an object URL", page.evaluate(
                "() => document.querySelector('.page-reader .prose img')"
                ".getAttribute('src').indexOf('blob:') === 0"))
            check("the image bytes came from /attachments",
                  any(path.endswith("/attachments") for _, path, _ in state["requests"]))

            print("\n4. share and export menus")
            page.click('#topbar-actions button[title="分享"]')
            page.wait_for_selector("#overlay-root .menu")
            check("the share menu offers six ways", page.locator(
                "#overlay-root .menu .menu-item").count() == 6,
                page.locator("#overlay-root .menu .menu-item").count())
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            page.locator(".reader-actions .btn").nth(2).click()
            page.wait_for_selector("#overlay-root .menu")
            check("the export menu offers Markdown and HTML", page.locator(
                "#overlay-root .menu .menu-item").count() == 2,
                page.locator("#overlay-root .menu .menu-item").count())
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            print("\n5. version history and restore")
            open_route(page, "#/read?p=welcome.md",
                       '.reader-title:text-is("Welcome to MarkNest")')
            page.locator(".reader-actions .btn").nth(1).click()
            page.wait_for_selector(".modal .version-row", timeout=6000)
            check("the seeded snapshot is listed",
                  page.locator(".modal .version-row").count() >= 1)
            page.locator(".modal .version-row .btn-sm").first.click()
            page.wait_for_selector(".modal-foot .btn-primary")
            page.locator(".modal-foot .btn-primary").last.click()
            page.wait_for_timeout(900)
            check("a restore was sent", any(path.endswith("/versions/restore")
                                            for _, path, _ in state["requests"]))
            check("the restored content is back",
                  "First draft." in api.notes["welcome.md"],
                  api.notes["welcome.md"][:50].replace("\n", " "))
            check("both dialogs closed", page.locator(".modal").count() == 0,
                  page.locator(".modal").count())

            print("\n5b. deleting version records")
            page.locator(".reader-actions .btn").nth(1).click()
            page.wait_for_selector(".modal .version-row", timeout=6000)
            before_rows = page.locator(".modal .version-row").count()
            page.locator(".modal .version-row .version-delete").first.click()
            page.wait_for_selector(".modal-foot .btn-danger")
            page.locator(".modal-foot .btn-danger").last.click()
            page.wait_for_timeout(700)
            check("a version delete was sent",
                  any(method == "DELETE" and path.endswith("/versions")
                      for method, path, _ in state["requests"]))
            check("the deleted record left the list",
                  page.locator(".modal .version-row").count() == before_rows - 1,
                  page.locator(".modal .version-row").count())
            page.locator(".modal .version-head .btn-danger").click()
            page.wait_for_selector(".modal-foot .btn-danger")
            page.locator(".modal-foot .btn-danger").last.click()
            page.wait_for_timeout(700)
            check("a clear-all request was sent",
                  any(method == "DELETE" and path.endswith("/versions/all")
                      for method, path, _ in state["requests"]))
            check("clearing history shows the empty state",
                  page.locator(".modal .empty-state").count() == 1,
                  page.locator(".modal .version-row").count())
            check("clearing history keeps the note",
                  "First draft." in api.notes["welcome.md"])
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            check("the history dialog closed", page.locator(".modal").count() == 0,
                  page.locator(".modal").count())

            print("\n6. the editor opens the same note")
            page.locator(".reader-actions .btn-primary").click()
            page.wait_for_selector(".page-editor .cm-content", timeout=8000)
            page.wait_for_timeout(600)
            check("the route moved to the editor", "#/edit" in
                  page.evaluate("() => location.hash"),
                  page.evaluate("() => location.hash"))
            check("the formatting toolbar has thirteen actions",
                  page.locator(".editor-toolbar .tb-btn").count() == 13,
                  page.locator(".editor-toolbar .tb-btn").count())
            check("the outline followed the note",
                  page.locator(".outline-item").count() >= 1,
                  page.locator(".outline-item").count())
            check("the preview rendered the note",
                  "First draft" in page.inner_text("#editor-preview"))

            print("\n6b. the outline resizes from its left edge")
            grip = page.locator(".editor-outline .outline-resizer")
            check("the outline has a drag handle", grip.count() == 1)
            start_box = page.locator(".editor-outline").bounding_box()
            grip_box = grip.bounding_box()
            check("the handle sits on the outline's left edge",
                  abs((grip_box["x"] + grip_box["width"] / 2) - start_box["x"]) <= 1,
                  (grip_box["x"], start_box["x"]))
            y = start_box["y"] + 60
            page.mouse.move(grip_box["x"] + grip_box["width"] / 2, y)
            page.mouse.down()
            page.mouse.move(grip_box["x"] + grip_box["width"] / 2 - 80, y, steps=6)
            page.mouse.up()
            page.wait_for_timeout(250)
            grown = page.locator(".editor-outline").bounding_box()["width"]
            check("dragging left widens the outline",
                  grown >= start_box["width"] + 60,
                  (start_box["width"], grown))
            stored = page.evaluate(
                "() => parseInt(localStorage.getItem('marknest.outlineWidth'), 10)")
            check("the chosen width is remembered", abs(stored - round(grown)) <= 1,
                  (stored, grown))
            grip.focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(150)
            narrowed = page.locator(".editor-outline").bounding_box()["width"]
            check("the arrow key narrows the outline by one step",
                  abs(narrowed - (grown - 16)) <= 1, (grown, narrowed))
            page.keyboard.press("Home")
            page.wait_for_timeout(150)
            reset_width = page.locator(".editor-outline").bounding_box()["width"]
            check("Home restores the default width", abs(reset_width - 256) <= 1,
                  reset_width)

            print("\n7. the toolbar inserts Markdown through the editor")
            page.click(".cm-content")
            page.keyboard.press("Control+A")
            page.keyboard.type("# Toolbar test\n\n## Section A\n\n## Section B\n\nline two")
            page.wait_for_timeout(600)
            page.keyboard.press("Control+End")
            page.locator('.editor-toolbar .tb-btn[aria-label="加粗"]').click()
            page.wait_for_timeout(200)
            check("bold inserted its placeholder",
                  "**加粗**" in editor_text(page), editor_text(page)[-40:])
            page.keyboard.press("Control+Home")
            page.locator('.editor-toolbar .tb-btn[aria-label="无序列表"]').click()
            page.wait_for_timeout(300)
            check("the list action prefixed the current line",
                  editor_text(page).lstrip().startswith("- # Toolbar test"),
                  editor_text(page)[:40])
            check("the outline picked up the new headings",
                  page.locator(".outline-item").count() >= 2,
                  page.locator(".outline-item").count())
            page.wait_for_timeout(300)
            check("the preview followed the typing",
                  "Section A" in page.inner_text("#editor-preview"))
            page.locator(".outline-item").nth(1).click()
            page.wait_for_timeout(300)
            check("clicking an outline item marks it active",
                  page.locator(".outline-item.is-active").count() == 1)

            print("\n8. saving")
            before = len(state["requests"])
            page.click("#btn-save")
            page.wait_for_timeout(900)
            saves = [r for r in state["requests"][before:] if r[1].endswith("/notes/save")]
            check("a save was sent", len(saves) == 1, len(saves))
            check("the saved text reached the backend",
                  "Toolbar test" in api.notes["welcome.md"],
                  api.notes["welcome.md"][:50].replace("\n", " "))
            check("the editor is marked clean", page.evaluate(
                "() => { var state = document.querySelector('.save-state');"
                " return !!state && !state.classList.contains('is-dirty'); }"))
            check("the save button is disabled while clean",
                  page.locator("#btn-save").is_disabled())

            print("\n9. a note changed underneath the editor conflicts")
            api.notes["welcome.md"] = "# Changed elsewhere\n"
            api.touch("welcome.md")
            page.click(".cm-content")
            page.keyboard.type("x")
            page.wait_for_timeout(250)
            page.click("#btn-save")
            page.wait_for_timeout(900)
            check("a conflict banner is shown",
                  page.locator("#editor-banner").is_visible())
            check("the other writer's content survived",
                  api.notes["welcome.md"] == "# Changed elsewhere\n",
                  api.notes["welcome.md"][:40])
            check("three ways out are offered",
                  page.locator("#editor-banner .btn").count() == 3,
                  page.locator("#editor-banner .btn").count())
            page.locator("#editor-banner .btn-primary").click()
            page.wait_for_timeout(900)
            check("overwriting closes the banner",
                  not page.locator("#editor-banner").is_visible())
            check("the forced save reached the backend",
                  api.notes["welcome.md"].endswith("x"))

            print("\n10. a pasted image is uploaded and referenced")
            page.click(".cm-content")
            page.keyboard.press("Control+End")
            page.evaluate(
                """() => {
                  const bytes = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]);
                  const file = new File([bytes], 'pixel.png', { type: 'image/png' });
                  const dt = new DataTransfer();
                  dt.items.add(file);
                  const host = document.getElementById('editor-host');
                  const ev = new Event('paste', { bubbles: true, cancelable: true });
                  Object.defineProperty(ev, 'clipboardData', { value: dt });
                  host.dispatchEvent(ev);
                }""")
            page.wait_for_timeout(1600)
            check("an attachment upload was sent",
                  any(method == "POST" and path.endswith("/attachments")
                      for method, path, _ in state["requests"]))
            check("the returned Markdown was inserted",
                  "![pasted](.assets/pasted-0000abcd.png)" in editor_text(page),
                  editor_text(page)[-60:])
            page.wait_for_function(
                "() => { var img = document.querySelector('#editor-preview img');"
                " return !!img && img.classList.contains('is-loaded') &&"
                " /^blob:/.test(img.getAttribute('src') || ''); }",
                timeout=6000)
            check("the preview hydrated the image", True)
            check("the upload chip was removed",
                  page.locator(".upload-chip").count() == 0)

            print("\n11. note content cannot execute")
            api.notes["injection.md"] = H.RAW_HTML_NOTE
            api.touch("injection.md")
            page.evaluate("() => { window.__pwned = false; }")
            open_route(page, "#/read?p=injection.md", ".page-reader .prose", wait=800)
            check("a <script> inside a note did not run", page.evaluate(
                "() => window.__pwned === false"), page.evaluate("() => window.__pwned"))
            check("no <script> element reached the preview", page.evaluate(
                "() => document.querySelectorAll('.page-reader .prose script').length") == 0)
            check("the onerror attribute was stripped", page.evaluate(
                "() => document.querySelectorAll('.page-reader .prose [onerror]').length") == 0)

            print("\n12. scroll synchronisation, both directions")
            open_route(page, "#/edit?p=notes/long.md", ".page-editor .cm-content", wait=900)
            page.evaluate(
                "() => { var s = document.querySelector('.cm-scroller');"
                " s.scrollTop = s.scrollHeight / 2;"
                " s.dispatchEvent(new Event('scroll')); }")
            page.wait_for_timeout(500)
            preview_scrolled = page.evaluate(
                "() => document.getElementById('editor-preview').scrollTop")
            check("scrolling the editor moved the preview", preview_scrolled > 50,
                  preview_scrolled)

            page.evaluate(
                "() => { var p = document.getElementById('editor-preview');"
                " p.scrollTop = p.scrollHeight * 0.8;"
                " p.dispatchEvent(new Event('scroll')); }")
            page.wait_for_timeout(500)
            editor_scrolled = page.evaluate(
                "() => document.querySelector('.cm-scroller').scrollTop")
            check("scrolling the preview moved the editor", editor_scrolled > 50,
                  editor_scrolled)

            print("\n13. the layout adapts without losing a control")
            page.set_viewport_size({"width": 760, "height": 700})
            page.wait_for_timeout(500)
            check("the preview pane collapses on a narrow frame", page.evaluate(
                "() => getComputedStyle(document.querySelector('.editor-pane-preview'))"
                ".display === 'none'"))
            check("the outline collapses with it", page.evaluate(
                "() => getComputedStyle(document.querySelector('.editor-outline'))"
                ".display === 'none'"))
            page.locator('.editor-actions .segmented [data-mode="preview"]').click()
            page.wait_for_timeout(400)
            check("preview mode swaps the pane",
                  page.locator(".page-editor.is-preview").count() == 1 and
                  page.evaluate("() => getComputedStyle("
                                "document.querySelector('.editor-pane-preview'))"
                                ".display !== 'none'"))
            check("no uncaught error during the run", not errors, errors[:2])

            browser.close()
    finally:
        httpd.shutdown()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: the reader typesets and hydrates attachments, the editor")
    print("        formats, previews, saves with conflict detection, uploads")
    print("        pasted images, refuses to execute note content and scroll-syncs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
