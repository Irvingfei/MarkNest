#!/usr/bin/env python3
"""What cookies does the signed-in session actually carry?

The backend reads `tos_current_username` to decide whose library a request is
for, on the strength of two observations: TOS's own backend services read that
name, and the browser's cookies reach this application (which is why the session
and CSRF cookies arrive). The live run says the name is not arriving, so one of
those premises needs checking rather than assuming.
"""

import os
import sys

from playwright.sync_api import sync_playwright

from _device import setting  # noqa: E402  (same directory)

HOST = setting("PRINT_WEB")
USER = setting("PRINT_WEB_USER")
PASSWORD = setting("PRINT_WEB_PASS")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="zh-CN", ignore_https_errors=True)
        page = context.new_page()

        print("1. sign in")
        page.goto(HOST + "/tos/", wait_until="load", timeout=90000)
        page.wait_for_timeout(3000)
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
        print("   url: %s" % page.url)

        print("\n2. cookies the browser holds")
        print("   document.cookie : %s" % page.evaluate("() => document.cookie"))
        jar = context.cookies()
        for cookie in sorted(jar, key=lambda c: c["name"]):
            print("   %-28s domain=%-20s httpOnly=%s" %
                  (cookie["name"], cookie["domain"], cookie["httpOnly"]))

        print("\n3. what the platform's own services read")
        # filemanager and storagemanager were seen reading tos_current_username,
        # so the name should be somewhere in the jar above if it exists at all.

        print("\n4. does the application receive it?")
        page.goto(HOST + "/marknest/", wait_until="load", timeout=60000)
        page.wait_for_timeout(8000)
        frame = None
        for candidate in page.frames:
            if "/marknest/" in candidate.url:
                frame = candidate
                break
        if frame is None:
            print("   the application frame never appeared; frames=%s"
                  % [f.url for f in page.frames])
            browser.close()
            return 1

        result = frame.evaluate(
            """async () => {
                 const out = {};
                 out.documentCookie = document.cookie;
                 const r = await fetch('/v2/proxy/marknest/me', { credentials: 'include' });
                 out.status = r.status;
                 out.body = await r.json().catch(() => ({}));
                 return out;
               }"""
        )
        print("   document.cookie inside the app frame: %s" % result["documentCookie"])
        print("   GET /me -> %s %s" % (result["status"], result["body"]))

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
