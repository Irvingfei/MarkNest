#!/usr/bin/env python3
"""Assert that no interactive control enters the space the TOS desktop owns.

The TOS desktop paints its window furniture ON TOP of the application frame
rather than giving the application a client area that excludes it. Three regions
are therefore unusable by anything the user is meant to press:

    top     46px, full width   a window-drag surface
                               (.tos-dialog-move is height:40px, width:100%,
                               cursor:move - the WHOLE band, not a corner)
    bottom  12px, full width   a resize strip
    corner  18x18, bottom right  a resize grip

The assertion is deliberately structural - "no interactive element's visible box
intersects those three rectangles" - rather than "the toolbar padding is 46".
A magic number matches one host build; a zero-intersection test matches any host
that still reserves those regions, and it also catches the failure mode this
file exists for, which is a container that is *mostly* clear with one control
peeking into the band.

The earlier defect that produced this approach had two halves: a toolbar whose
gutter was guessed from a screenshot (48-98px guessed, 141px actual), and a
single element that stretched to the right edge under the host's window buttons.
Measuring the host stylesheet fixed the first; asserting intersection fixes the
second.

Usage:
    <python> tools/measure_topbar.py
"""

import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import webui_harness as H  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

#: The host's reserved geometry, read off the device stylesheet.
BAND_TOP = 46
BAND_BOTTOM = 12
GRIP = 18

#: Frame widths to scan. The narrow ones are where a layout wraps and a control
#: that was clear at 1180 suddenly is not.
WIDTHS = [1180, 1024, 900, 820, 760, 700, 640, 600]

failures = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("PASS" if condition else "FAIL", label,
                           "" if condition else "  -> %s" % (detail,)))
    if not condition:
        failures.append(label)
    return bool(condition)


# Collect every interactive element's visible box, already clipped by its
# scrollable ancestors and by the viewport. getBoundingClientRect alone reports
# viewport coordinates for a row that has been scrolled out of its pane, which
# would flag invisible controls as intrusions.
SCAN_JS = """
() => {
  const SELECTOR = 'button, input, select, textarea, a[href], [role="button"], [tabindex]:not([tabindex="-1"])';
  function visibleBox(el) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) { return null; }
    let box = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    box.left = Math.max(box.left, 0);
    box.top = Math.max(box.top, 0);
    box.right = Math.min(box.right, window.innerWidth);
    box.bottom = Math.min(box.bottom, window.innerHeight);
    let p = el.parentElement;
    while (p) {
      const style = getComputedStyle(p);
      if (/(auto|scroll|hidden)/.test(
            style.overflow + style.overflowX + style.overflowY)) {
        const pr = p.getBoundingClientRect();
        box.left = Math.max(box.left, pr.left);
        box.top = Math.max(box.top, pr.top);
        box.right = Math.min(box.right, pr.right);
        box.bottom = Math.min(box.bottom, pr.bottom);
      }
      p = p.parentElement;
    }
    if (box.right <= box.left || box.bottom <= box.top) { return null; }
    return box;
  }
  const out = [];
  document.querySelectorAll(SELECTOR).forEach((el) => {
    const box = visibleBox(el);
    if (!box) { return; }
    out.push({
      tag: el.tagName.toLowerCase(),
      label: (el.id || el.className || el.textContent || '').toString().trim().slice(0, 40),
      box: box
    });
  });
  return out;
}
"""


def reserved(width, height):
    return [
        ("top band", {"left": 0, "top": 0, "right": width, "bottom": BAND_TOP}),
        ("bottom band", {"left": 0, "top": height - BAND_BOTTOM,
                         "right": width, "bottom": height}),
        ("bottom-right grip", {"left": width - GRIP, "top": height - GRIP,
                               "right": width, "bottom": height}),
    ]


def intersects(a, b):
    return not (a["right"] <= b["left"] or a["left"] >= b["right"] or
                a["bottom"] <= b["top"] or a["top"] >= b["bottom"])


def main():
    httpd, port = H.serve()
    url = "http://127.0.0.1:%d/index.html" % port
    state = H.new_state()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": WIDTHS[0], "height": 720},
                                          locale="zh-CN")
            context.route(H.PROXY_GLOB, H.make_router(state))
            page = context.new_page()
            H.boot_page(page, url)

            # Open a note so the editor, the preview and their footers are all
            # populated; an empty layout is not the layout.
            #
            # The note is addressed through the fragment rather than by clicking
            # its row: the tree lives inside the workspace, and the application
            # opens on the home screen, which hides it until a note is open. The
            # fragment is the application's own way to name a note, so this
            # reaches the same layout the click did.
            page.evaluate(
                "() => { location.hash = '#/notes?p=' + encodeURIComponent('welcome.md'); }")
            page.wait_for_timeout(900)

            print("Scanning %d widths for controls inside the host's regions" % len(WIDTHS))
            print("-" * 62)
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
                check("%4dpx: %2d interactive element(s), 0 in a host region"
                      % (width, len(elements)), not intrusions,
                      intrusions[:4])

            # The rule is not "the band is exactly 46px" but "nothing is in it",
            # yet the top bar's own content still has to start below it or the
            # band would be painted over by the application's own background.
            page.set_viewport_size({"width": WIDTHS[0], "height": 720})
            page.wait_for_timeout(300)
            brand_top = page.evaluate(
                "() => document.querySelector('.brand').getBoundingClientRect().top")
            check("the top bar's content starts below the drag band (%.0f >= %d)"
                  % (brand_top, BAND_TOP), brand_top >= BAND_TOP)

            status_bottom = page.evaluate(
                "() => window.innerHeight - document.querySelector('.statusbar')"
                ".getBoundingClientRect().bottom")
            check("the status line leaves the bottom strip free",
                  status_bottom <= BAND_BOTTOM + 0.5, status_bottom)

            browser.close()
    finally:
        httpd.shutdown()

    print()
    print("-" * 62)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("PASSED: no interactive control enters the host's top band, bottom strip")
    print("        or resize grip, at any width from %d to %d."
          % (WIDTHS[-1], WIDTHS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
