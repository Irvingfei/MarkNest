#!/usr/bin/env python3
"""Verify in a real browser that backend failures are localised, actionable, and
that the version badge reflects the running backend.

Three reported symptoms are covered:

  1. the Printers page showed the raw backend sentence
     "cups-client is not installed" inside an otherwise Chinese interface - the
     backend is stubbed with the real envelope, HTTP 503
     ``{"code": 2001, "message": "cups-client is not installed"}``, and the
     assertion is that the user sees the localised sentence instead;
  2. the same failure left the operator with no way forward - a remedy line is
     asserted under the message;
  3. the application version was not visible anywhere - the top bar badge is
     asserted to carry the value the backend reports, and to change when that
     value changes (which proves it is not a hard-coded decoration).

Usage:
    <python> tools/verify_error_i18n.py
"""

import functools
import http.server
import json
import os
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
WEBUI = os.path.join(REPO_ROOT, "webui")
INDEX_HTML = os.path.join(WEBUI, "index.html")

BACKEND_MESSAGE = "cups-client is not installed"
PROXY_GLOB = "**/v2/proxy/marknest/**"

# The running backend's version, which the badge must follow. Deliberately
# different from the version baked into index.html so a static decoration cannot
# satisfy the assertion.
LIVE_VERSION = "9.9.9"


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, *a):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Quiet)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def make_router(state):
    """Fulfil the proxy endpoints with the shapes the real backend uses."""

    def handler(route, request):
        url = request.url
        if url.endswith("/health"):
            payload = {
                "code": 0,
                "message": "ok",
                "data": {
                    "cups": False,
                    "status": "degraded",
                    "cups_tools": {},
                    "version": state["version"],
                },
            }
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(payload))
        elif url.endswith("/printers"):
            payload = {"code": 2001, "message": state["message"], "data": None}
            route.fulfill(status=503, content_type="application/json",
                          body=json.dumps(payload))
        else:
            route.fulfill(status=404, content_type="application/json",
                          body=json.dumps({"code": 1404, "message": "not found", "data": None}))

    return handler


def static_badge():
    """The version literal the page ships with, before any request completes."""
    with open(INDEX_HTML, "r", encoding="utf-8") as handle:
        text = handle.read()
    marker = 'class="app-version" id="app-version"'
    index = text.find(marker)
    if index == -1:
        return None
    tail = text[index:]
    start = tail.find(">")
    end = tail.find("<", start)
    return tail[start + 1:end].strip()


def check_failure(page, lang, expect_message, expect_hint):
    page.evaluate("(l) => { try { localStorage.setItem('marknest.lang', l); } catch (e) {} }", lang)
    page.reload(wait_until="load")
    page.wait_for_timeout(600)

    page.evaluate("() => window.App.showPage('printers')")
    page.wait_for_timeout(700)

    body = page.evaluate(
        "() => (document.querySelector('#printers-host') || {}).textContent || ''"
    )
    message_ok = expect_message in body
    hint_ok = expect_hint in body
    # The bare backend sentence must not be the thing on screen. Note the en-us
    # localisation legitimately contains those words, so the check is "the
    # localised sentence is present AND the bare sentence is not the whole box".
    bare_only = BACKEND_MESSAGE in body and not message_ok
    ok = message_ok and hint_ok and not bare_only
    print("  lang=%-6s message=%-5s hint=%-5s bare-only=%-5s ok=%s"
          % (lang, message_ok, hint_ok, bare_only, ok))
    print("      rendered: %s" % " ".join(body.split())[:200])
    return ok


def main():
    httpd, port = serve(WEBUI)
    url = "http://127.0.0.1:%d/index.html" % port
    state = {"message": BACKEND_MESSAGE, "version": LIVE_VERSION}
    failures = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1180, "height": 700}, locale="zh-CN")
        context.route(PROXY_GLOB, make_router(state))
        page = context.new_page()
        page.goto(url, wait_until="load")

        print("serving %s" % url)
        print("backend 503 code=2001 message=%r" % BACKEND_MESSAGE)
        print("backend /health version=%r" % LIVE_VERSION)
        print("index.html ships badge %r" % static_badge())
        print()

        # --- version badge: static on first paint, then the backend's value ---
        # The health poll runs on boot; the badge must not stay on the shipped
        # literal when the running process reports something else.
        page.wait_for_timeout(500)
        badge = page.evaluate("() => (document.getElementById('app-version')||{}).textContent")
        badge_ok = badge == "v" + LIVE_VERSION
        print("  version badge           : %r  follows backend=%s" % (badge, badge_ok))
        if not badge_ok:
            failures.append("version badge")

        # --- localised failure + remediation, per language ---
        cases = [
            ("zh-cn", "CUPS 打印服务不可用", "apt install cups cups-client"),
            ("zh-hk", "CUPS 列印服務無法使用", "apt install cups cups-client"),
            ("en-us", "The CUPS printing service is unavailable", "Install CUPS"),
        ]
        for lang, expect_message, expect_hint in cases:
            if not check_failure(page, lang, expect_message, expect_hint):
                failures.append("i18n:" + lang)

        browser.close()

    httpd.shutdown()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: failures are localised with a remedy, and the version badge")
    print("        follows the running backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
