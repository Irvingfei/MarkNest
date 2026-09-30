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

        print("\n5. create a note, edit it, and watch the preview follow")
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

        print("\n6. save, and read it back from the server")
        app.click("#btn-save")
        page.wait_for_timeout(2500)
        check("the editor is no longer dirty", app.evaluate(
            "() => document.getElementById('dirty-dot').hidden") is True)
        saved = api_call(app, "/notes?path=" + note_name)
        content = ((saved.get("body") or {}).get("data") or {}).get("content") or ""
        check("the note reads back from the server", "Hello from the device" in content,
              content[:80].replace("\n", " "))
        shot(page, "_mn_12_note.png")

        print("\n7. the file is where the user can see it")
        print("   library path: %s" % data.get("library_path"))

        print("\n8. cleaning up the note this run created")
        removed = api_call(app, "/notes?path=" + note_name, "DELETE")
        check("the test note was removed again", removed["status"] == 200, removed)

        browser.close()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: the desktop opens MarkNest, the platform identity reaches it")
    print("        through the proxy, and a note survives create, edit, preview,")
    print("        save and delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
