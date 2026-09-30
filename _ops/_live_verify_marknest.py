#!/usr/bin/env python3
"""Verify MarkNest in the real TOS desktop, end to end.

Everything up to here proves the package installs and its backend answers. This
proves a person can actually use it: the desktop opens the application, the
application resolves which TOS user is asking, and a note survives a round trip
through the editor, the preview and the filesystem.

Two things this run is the only evidence for:

  * The platform does NOT forward `tos_current_username` to an embedded
    application. The browser holds it, the session and CSRF cookies arrive
    (authentication would fail before identity is considered otherwise), and
    this one does not - while the identical request made directly against the
    application's socket carries it fine. The WebUI therefore sends the value in
    a header of its own, and this verifies that path works through the proxy.
  * The application's web route only exists after the platform creates its
    AppAccessControl nginx config. `_ops/_install_web_route.py` supplies one for
    development; this asserts the result is reachable.

It also carries the branch's own features the offline harness cannot settle on
its own: the home screen the application now opens on, the menu item that comes
back to it, and the format toolbar that edits through the editor. Those three
meet a real TOS desktop here and nowhere else - `verify_editor.py` drives them
against a stub, which agrees with the code by construction.

    python _ops/_live_verify_marknest.py
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

from _device import setting  # noqa: E402  (same directory)

HOST = setting("PRINT_WEB")
USER = setting("PRINT_WEB_USER")
PASSWORD = setting("PRINT_WEB_PASS")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(REPO, "_scratch")

failures = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", label,
                           "" if condition else "  -> %s" % (detail,)))
    if not condition:
        failures.append(label)
    return bool(condition)


def shot(page, name):
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, name)
    page.screenshot(path=path)
    print("   screenshot: %s" % path)


def login(page):
    page.goto(HOST + "/tos/", wait_until="load", timeout=90000)
    page.wait_for_timeout(3000)
    # Selected by shape rather than placeholder: the shell follows the device
    # locale, so the label is "Username" or its Chinese equivalent depending on
    # how the NAS was set up.
    page.locator("input[type=text]:visible").first.wait_for(state="visible", timeout=90000)
    page.locator("input[type=text]:visible").first.fill(USER)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    try:
        password = page.locator("input[type=password]:visible").first
        password.wait_for(state="visible", timeout=15000)
        password.fill(PASSWORD)
        page.keyboard.press("Enter")
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(9000)


def open_app(page):
    """Open MarkNest inside the desktop and return ``(frame, embedded)``.

    Requesting /marknest/ without a session redirects to
    ``/tos/?id=marknest#/`` - the desktop's own "open this application" URL - so
    once signed in, navigating there makes the desktop open the application as
    an embedded window, which is the arrangement the host-band geometry is
    about.

    The launcher is not consulted. A .deb installed by hand is not in the
    platform's application registry, so it never appears there, and a loose
    ``text=`` lookup for the name matches unrelated parts of the desktop shell -
    which is a way to click something surprising.
    """
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    for attempt in range(3):
        page.goto(HOST + "/marknest/", wait_until="load", timeout=60000)
        page.wait_for_timeout(9000)
        for candidate in page.frames:
            if "/marknest/" in candidate.url:
                return candidate, True
        print("   attempt %d: the application frame did not appear (url=%s)"
              % (attempt + 1, page.url))
        page.wait_for_timeout(3000)
    return page.main_frame, False


def api_call(frame, path, method="GET"):
    return frame.evaluate(
        """async ([p, m]) => {
             const headers = window.API ? API.authHeaders() : {};
             const r = await fetch('/v2/proxy/marknest' + p,
                                   { method: m, credentials: 'include', headers });
             return { status: r.status, body: await r.json().catch(() => ({})) };
           }""",
        [path, method],
    )


def main():
    expected_badge = "v" + open(os.path.join(REPO, "VERSION"), encoding="utf-8").read().strip()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="zh-CN", ignore_https_errors=True)
        page = context.new_page()

        print("1. sign in to the desktop")
        login(page)
        check("signed in", "/desktop" in page.url, page.url)

        print("\n2. open MarkNest")
        app, embedded = open_app(page)
        shot(page, "_mn_11_app.png")
        print("   frames: %s" % [f.url for f in page.frames])
        print("   embedded in the desktop: %s" % embedded)
        check("the application page loaded", "/marknest/" in app.url, app.url)
        if not embedded:
            print("   NOTE: the desktop did not open it as a window this time;")
            print("         the rest of the run still exercises the application.")

        print("\n3. the application resolved who is asking")
        me = api_call(app, "/me")
        print("   GET /me -> %s" % me)
        data = (me.get("body") or {}).get("data") or {}
        check("the platform identity reached the application", me["status"] == 200,
              (me.get("body") or {}).get("message"))
        check("it resolved to the signed-in TOS user", data.get("user") == USER, data.get("user"))
        check("that user's library exists", data.get("exists") is True, data)
        check("and was measured writable", data.get("writable") is True, data)

        print("\n4. the user interface loaded")
        check("the editor bundle is present in the page",
              app.evaluate("() => typeof window.MDEditor === 'object'"))
        check("the three panes rendered", app.evaluate(
            "() => !!document.querySelector('.pane-tree') && "
            "!!document.querySelector('.pane-editor') && "
            "!!document.querySelector('.pane-preview')"))
        badge = app.evaluate("() => (document.getElementById('app-version')||{}).textContent")
        check("the version badge matches the package (%s)" % expected_badge,
              badge == expected_badge, badge)

        print("\n5. the application opens on its home screen")
        # Nothing has opened a note yet, so this is the state a person lands in.
        # The workspace is the three-pane editor; on the home screen it carries
        # `is-home`, which is what hides it and shows the home pane instead - so
        # the class, not the pane's own visibility, is the fact to assert.
        check("the workspace says it is the home view", app.evaluate(
            "() => document.getElementById('workspace').classList.contains('is-home')"))
        check("the home screen is the visible one", app.evaluate(
            "() => document.getElementById('home').hidden === false"))
        check("it offers 打开文件 and 新建文件", app.evaluate(
            "() => !!document.getElementById('home-open') && !!document.getElementById('home-new')"))
        # Translated, not raw keys. The two buttons rendered "home.open" on
        # screen from the task that added them until the strings landed, and
        # nothing else on this route notices them going missing again: the
        # dictionaries are compared against each other, never against what the
        # code references.
        check("the home buttons are translated, not raw keys", app.evaluate(
            "() => { var b = document.getElementById('home-open');"
            " return !!b && b.textContent.indexOf('home.') !== 0; }"),
            app.evaluate("() => (document.getElementById('home-open')||{}).textContent"))
        # The other half of "the toolbar appears once a note is open": it must
        # not be there while this screen is up. Asserted here, before anything
        # opens a note, because afterwards the answer is always true.
        check("the format bar is hidden until a note is open", app.evaluate(
            "() => document.getElementById('format-bar').hidden === true"))

        print("\n6. create a note, edit it, and watch the preview follow")
        try:
            app.wait_for_selector("#btn-more", timeout=30000)
        except Exception:  # noqa: BLE001
            shot(page, "_mn_13_stuck.png")
            print("   the toolbar never appeared; frame html follows")
            print("   %s" % app.evaluate("() => document.body.innerHTML")[:600])
            browser.close()
            return 1

        # A unique name per run. The library is the filesystem, so a fixed name
        # collides with the previous run's note and the create is refused -
        # correct behaviour, and a useless test.
        note_name = "selftest-%d.md" % int(time.time())
        app.evaluate("(name) => { window.prompt = () => name; }", note_name)
        # The ＋ button is gone; creating a note is now the ☰ menu's 新建文件,
        # which reaches the same TreePane.newNote() the button called. Opening
        # the menu first is what a person does, so the create is exercised
        # through the route that will exist rather than a removed one.
        app.click("#btn-more")
        app.wait_for_selector("#more-menu", timeout=30000)
        app.click("#more-new")
        page.wait_for_timeout(3000)
        current = app.evaluate("() => (document.getElementById('current-path')||{}).textContent")
        check("the note was created and opened", note_name in (current or ""), current)
        check("the tree now lists it", note_name in app.inner_text("#tree-body"),
              app.inner_text("#tree-body")[:120])

        app.click(".cm-content")
        # A Frame has no keyboard; input goes through the page once the element
        # in the frame holds focus.
        page.keyboard.type("# Hello from the device\n\nsome **bold** text\n")
        page.wait_for_timeout(900)
        check("the preview rendered the typing", app.evaluate(
            "() => { var h = document.querySelector('#preview-body h1');"
            " return !!h && h.textContent.indexOf('Hello from the device') !== -1; }"))
        check("markdown markup became markup, not text", app.evaluate(
            "() => document.querySelectorAll('#preview-body strong').length > 0"))

        print("\n7. save, and read it back from the server")
        app.click("#btn-save")
        page.wait_for_timeout(2500)
        check("the editor is no longer dirty", app.evaluate(
            "() => document.getElementById('dirty-dot').hidden") is True)
        saved = api_call(app, "/notes?path=" + note_name)
        content = ((saved.get("body") or {}).get("data") or {}).get("content") or ""
        check("the note reads back from the server", "Hello from the device" in content,
              content[:80].replace("\n", " "))
        shot(page, "_mn_12_note.png")

        print("\n8. the format toolbar applies its Markdown through the editor")
        # The bar only exists once there is a note to edit, so its presence is
        # asserted here rather than at boot. The count is what separates a bar
        # that rendered its buttons from one that is merely visible: an empty
        # toolbar passes a visibility check and cannot be pressed.
        check("the format bar appears once a note is open", app.evaluate(
            "() => document.getElementById('format-bar').hidden === false"))
        check("it carries all thirteen buttons", app.evaluate(
            "() => document.querySelectorAll('#format-bar .format-btn').length") == 13,
            app.evaluate("() => document.querySelectorAll('#format-bar .format-btn').length"))

        # The selection and the press go through the same route the typing above
        # uses - the element holds focus, so the page can send the keys - rather
        # than a second way of driving the editor. The document is snapshotted
        # because the note already contains **bold**: a search for that markup
        # could not fail, so the comparison of both ends is what actually
        # depends on the press.
        app.click(".cm-content")
        page.keyboard.press("Control+a")
        page.wait_for_timeout(300)
        before_bold = app.evaluate(
            "() => document.querySelector('.cm-content').textContent")
        app.click("#fmt-bold")
        page.wait_for_timeout(1500)
        after_bold = app.evaluate(
            "() => document.querySelector('.cm-content').textContent")
        check("the B button wrapped the selection in ** at both ends",
              after_bold[:2] == "**" and after_bold[-2:] == "**",
              "%r ... %r" % (after_bold[:12], after_bold[-12:]))
        check("the press changed the document", after_bold != before_bold,
              "unchanged (%d chars)" % len(after_bold))
        # The transition is the evidence that the edit travelled through the
        # editor rather than through a second path that left the shell's own
        # notion of the document untouched. The save above put the editor back
        # to clean, so a dirty flag here can only come from this press.
        check("the press marked the editor dirty", app.evaluate(
            "() => document.getElementById('dirty-dot').hidden === false"))

        print("\n9. the menu's home item returns to the home screen")
        # The menu item is the only way back once a note is open: the workspace
        # is what is on screen, so the home screen's own buttons are behind it.
        # A real click is what the item needs - the menu is the application's
        # own panel, and its items are bound to the click that a real down/up
        # pair delivers.
        app.click("#btn-more")
        app.wait_for_selector("#more-menu", timeout=30000)
        app.click("#more-home")
        page.wait_for_timeout(3000)

        check("the application is back on its home screen", app.evaluate(
            "() => document.getElementById('workspace').classList.contains('is-home')"))
        check("the home screen is the visible one again", app.evaluate(
            "() => document.getElementById('home').hidden === false"))
        check("and the fragment says so", app.evaluate("() => location.hash") == "#/home",
              app.evaluate("() => location.hash"))

        # The note lands in this list because both the create and the save above
        # ran the indexer's own scan, not because the page remembers it. It is
        # found by its path - the item carries `title=row.path` - rather than by
        # the text on the row: that text is the note's first heading, a derived
        # value which falls back to the file name once the first line no longer
        # begins with '#', so it is not a stable thing to assert on.
        recent_paths = app.evaluate(
            "() => Array.from(document.querySelectorAll('#home-recent .home-recent-item'))"
            ".map(function (node) { return node.getAttribute('title'); })")
        check("the recent list is populated", bool(recent_paths), recent_paths)
        check("and it lists the note this run created", note_name in (recent_paths or []),
              recent_paths)
        shot(page, "_mn_14_home.png")

        print("\n10. the file is where the user can see it")
        print("   library path: %s" % data.get("library_path"))

        print("\n11. cleaning up the note this run created")
        removed = api_call(app, "/notes?path=" + note_name, "DELETE")
        check("the test note was removed again", removed["status"] == 200, removed)

        browser.close()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: the desktop opens MarkNest, the platform identity reaches it")
    print("        through the proxy, a note survives create, edit, preview,")
    print("        save and delete, the home screen lists it, and the format")
    print("        toolbar edits through the editor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
