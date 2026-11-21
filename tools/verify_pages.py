#!/usr/bin/env python3
"""Verify the library, import, settings and responsive shell in a browser.

``verify_editor.py`` covers the reading and editing surfaces; this harness
covers the rest of the application: the document list and its file operations,
the import queue against the stub's per-file verdicts, the preferences that
must survive a reload, and the off-canvas navigation the host iframe forces at
narrow widths.

Usage:
    <python> tools/verify_pages.py
"""

import json
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


def route(page, route_hash, marker, wait=450):
    page.evaluate("(hash) => { location.hash = hash; }", route_hash)
    page.wait_for_timeout(350)
    page.wait_for_selector(marker, timeout=8000)
    page.wait_for_timeout(wait)


def settings_json(page):
    return json.loads(page.evaluate(
        "() => localStorage.getItem('marknest.settings') || '{}'"))


def menu_item(page, text):
    return page.locator("#overlay-root .menu .menu-item", has_text=text)


def main():
    httpd, port = H.serve()
    url = "http://127.0.0.1:%d/index.html" % port
    state = H.new_state()
    api = state["api"]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 820},
                                          locale="zh-CN")
            context.route(H.PROXY_GLOB, H.make_router(state))
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            print("1. the library lists the documents")
            H.boot_page(page, url)
            page.wait_for_selector(".page-library .note-card", timeout=8000)
            page.wait_for_timeout(400)
            check("four Markdown notes are shown", page.locator(
                ".page-library .note-card").count() == 4,
                page.locator(".page-library .note-card").count())
            check("four statistics are shown",
                  page.locator(".page-library .stat").count() == 4,
                  page.locator(".page-library .stat").count())
            storage_text = page.inner_text("#storage-text")
            check("the storage card shows volume usage out of capacity",
                  storage_text == "1.25 TB / 4.00 TB", storage_text)
            check("its tooltip carries the free space",
                  "剩余 2.75 TB" in (page.get_attribute("#storage-text", "title") or ""),
                  page.get_attribute("#storage-text", "title"))
            check("a plain text file is not offered as a note",
                  page.locator(".note-card-title", has_text="plain").count() == 0)

            check("the library title is not repeated as an eyebrow",
                  page.locator(".page-library .eyebrow").count() == 0)

            print("\n2. search, view switch and folder scope")
            page.fill(".library-toolbar input[type=search]", "roadmap")
            page.wait_for_timeout(400)
            check("search narrows the list",
                  page.locator(".page-library .note-card").count() == 1,
                  page.locator(".page-library .note-card").count())
            check("the result counter appears",
                  page.locator(".library-result-count").count() == 1)
            page.fill(".library-toolbar input[type=search]", "")
            page.wait_for_timeout(400)
            check("clearing the search restores the list",
                  page.locator(".page-library .note-card").count() == 4,
                  page.locator(".page-library .note-card").count())
            page.locator(".library-toolbar .segmented button").nth(1).click()
            page.wait_for_timeout(300)
            check("the list view renders rows",
                  page.locator(".page-library .note-row").count() == 4,
                  page.locator(".page-library .note-row").count())
            page.locator(".library-toolbar .segmented button").nth(0).click()
            page.wait_for_timeout(300)
            page.click('#folder-list [data-folder="notes"]')
            page.wait_for_timeout(700)
            check("a folder scopes the list",
                  page.locator(".page-library .note-card").count() == 2,
                  page.locator(".page-library .note-card").count())
            check("the toolbar shows the scope",
                  "notes" in page.inner_text(".library-scope"))
            page.click('#folder-list [data-folder=""]')
            page.wait_for_timeout(700)
            check("all notes returns to the full list",
                  page.locator(".page-library .note-card").count() == 4,
                  page.locator(".page-library .note-card").count())

            page.locator(".page-library .note-card").first.click()
            page.wait_for_selector(".page-reader .reader-title", timeout=8000)
            page.wait_for_timeout(500)
            meta = page.inner_text(".page-reader .reader-meta")
            check("the reader fills in the update time",
                  "更新于" in meta and "{" not in meta, meta)
            check("the reader title is shown once",
                  page.locator(".page-reader .reader-title").count() == 1,
                  page.locator(".page-reader .reader-title").count())
            reader_title = page.inner_text(".page-reader .reader-title")
            reader_crumb = page.inner_text(".page-reader .reader-crumb")
            check("the breadcrumb carries the folder, not the title again",
                  reader_title not in reader_crumb,
                  "%s / %s" % (reader_crumb, reader_title))
            route(page, "#/library", ".page-library .note-card")

            print("\n2b. a note is opened from the NAS folder")
            page.locator(".page-head-actions button", has_text="从 NAS 打开").click()
            page.wait_for_selector(".modal .nas-browser .nas-row", timeout=6000)
            check("the picker lists the folders and notes on the share",
                  page.locator(".modal .nas-row").count() == 3,
                  page.locator(".modal .nas-row").count())
            hint = page.inner_text(".modal .nas-hint")
            check("the picker explains what can be opened",
                  "Markdown" in hint and "PDF" in hint, hint)
            check("there is no dead up button at the root",
                  page.locator(".nas-bar button").is_hidden())
            page.locator(".modal .nas-row", has_text="notes").first.click()
            page.wait_for_timeout(500)
            check("a folder opens inside the picker",
                  page.inner_text(".nas-path-text") == "全部笔记 / notes",
                  page.inner_text(".nas-path-text"))
            check("the up button appears inside a folder",
                  page.locator(".nas-bar button").is_visible())
            page.locator(".nas-bar button").click()
            page.wait_for_timeout(500)
            check("up returns to the root",
                  page.inner_text(".nas-path-text") == "全部笔记",
                  page.inner_text(".nas-path-text"))
            page.locator(".modal .nas-row", has_text="notes").first.click()
            page.wait_for_timeout(500)
            page.locator(".modal .nas-row", has_text="long.md").first.click()
            page.wait_for_selector(".page-reader .reader-title", timeout=8000)
            page.wait_for_timeout(500)
            check("the picked note opens in the reader",
                  page.inner_text(".page-reader .reader-title") == "Long note",
                  page.inner_text(".page-reader .reader-title"))
            route(page, "#/library", ".page-library .note-card")

            print("\n3. a note is created and another deleted")
            page.click("#topbar-actions .btn-primary")
            page.wait_for_selector(".modal .input")
            page.fill(".modal .input", "demo/prompt.md")
            page.click(".modal-foot .btn-primary")
            page.wait_for_function(
                "() => location.hash.indexOf('#/edit') === 0", timeout=8000)
            page.wait_for_timeout(600)
            check("the new note exists on the backend",
                  "demo/prompt.md" in api.notes)
            route(page, "#/library", ".page-library .note-card")
            page.wait_for_timeout(500)
            roadmap = page.locator(".note-card", has_text="Roadmap")
            roadmap.locator(".card-menu-btn").click()
            page.wait_for_selector("#overlay-root .menu")
            menu_item(page, "删除").click()
            page.wait_for_selector(".modal-foot .btn-danger")
            page.click(".modal-foot .btn-danger")
            page.wait_for_timeout(900)
            check("the delete reached the backend",
                  "projects/roadmap.md" not in api.notes)
            check("the list dropped the deleted note",
                  page.locator(".page-library .note-card").count() == 4,
                  page.locator(".page-library .note-card").count())

            print("\n4. folders are created and removed")
            page.click("#btn-new-folder")
            page.wait_for_selector(".modal .input")
            page.fill(".modal .input", "archive")
            page.click(".modal-foot .btn-primary")
            page.wait_for_selector('#folder-list [data-folder="archive"]',
                                   timeout=6000)
            check("the folder appears in the sidebar", True)
            check("the folder was created on the backend",
                  any(path.endswith("/folders/new") for _, path, _ in state["requests"]))
            route(page, "#/import", ".page-import .dropzone")
            destination = page.locator(
                ".page-import .panel:has(.panel-title:text-is('导入到'))")
            check("the destination picker appears once a subfolder exists",
                  destination.is_visible())
            check("the new folder is offered as a destination",
                  page.locator(".page-import select option",
                               has_text="archive").count() == 1)
            route(page, "#/library", ".page-library .note-card")
            page.click('#folder-list [data-folder="archive"]')
            page.wait_for_selector(".page-library .empty-state", timeout=6000)
            page.wait_for_timeout(400)
            empty_body = page.inner_text(".page-library .empty-body")
            check("the empty folder names itself without a placeholder",
                  "archive" in empty_body and "{" not in empty_body, empty_body)
            page.click('#folder-list [data-folder="archive"]', button="right")
            page.wait_for_selector("#overlay-root .menu")
            menu_item(page, "删除文件夹").click()
            page.wait_for_selector(".modal-foot .btn-danger")
            page.click(".modal-foot .btn-danger")
            page.wait_for_timeout(800)
            check("the folder is gone from the sidebar",
                  page.locator('#folder-list [data-folder="archive"]').count() == 0)
            check("the folder delete reached the backend",
                  any(method == "DELETE" and path.endswith("/folders")
                      for method, path, _ in state["requests"]))

            print("\n5. the import queue handles every verdict")
            route(page, "#/import", ".page-import .dropzone")
            check("the import title is not repeated as an eyebrow",
                  page.locator(".page-import .eyebrow").count() == 0)
            page.set_input_files(".page-import input[type=file]", [
                {"name": "hello.md", "mimeType": "text/markdown",
                 "buffer": b"# Hello\n\nImported body.\n"},
                {"name": "note.txt", "mimeType": "text/plain",
                 "buffer": b"only text\n"},
            ])
            page.wait_for_selector(".queue-item")
            check("both files are queued",
                  page.locator(".queue-item").count() == 2,
                  page.locator(".queue-item").count())
            page.click(".panel.queue .btn-primary")
            page.wait_for_function(
                "() => !!document.querySelector('.import-summary:not([hidden])')",
                timeout=10000)
            page.wait_for_timeout(400)
            summary = page.inner_text(".import-summary")
            check("the summary counts one created and one failed",
                  "新增 1" in summary and "失败 1" in summary, summary)
            check("the queue shows both verdicts",
                  page.locator(".queue-item .badge-ok").count() == 1 and
                  page.locator(".queue-item .badge-bad").count() == 1)
            check("the created note reached the backend", "hello.md" in api.notes)
            check("the text file was rejected by the server",
                  "note.txt" not in api.notes)

            before = len([r for r in state["requests"] if r[1].endswith("/notes/import")])
            page.locator(".import-summary .btn", has_text="重试失败项").click()
            page.wait_for_function(
                "() => !document.querySelector('.queue-item .badge-accent')",
                timeout=10000)
            page.wait_for_timeout(400)
            after = len([r for r in state["requests"] if r[1].endswith("/notes/import")])
            check("retry re-sent only the failed file", after == before + 1,
                  "%d -> %d" % (before, after))

            page.click(".panel.queue .panel-actions .btn-ghost")
            page.wait_for_timeout(300)
            check("the queue can be cleared",
                  page.locator(".queue-item").count() == 0)
            page.click('.radio-card[data-value="skip"]')
            page.set_input_files(".page-import input[type=file]", [
                {"name": "welcome.md", "mimeType": "text/markdown",
                 "buffer": b"# Replaced\n"},
            ])
            page.wait_for_timeout(300)
            page.click(".panel.queue .btn-primary")
            page.wait_for_function(
                "() => !!document.querySelector('.import-summary:not([hidden])')",
                timeout=10000)
            page.wait_for_timeout(400)
            check("skip leaves the existing note untouched",
                  api.notes["welcome.md"].startswith("# Welcome to MarkNest"))
            check("the summary reports the skip",
                  "跳过 1" in page.inner_text(".import-summary"),
                  page.inner_text(".import-summary"))

            print("\n6. text can become a note")
            page.fill(".text-create input.input", "made.md")
            page.fill(".text-create textarea", "# Made\n\nText create body.\n")
            page.click(".text-create .btn-primary")
            page.wait_for_timeout(1000)
            check("the typed note was created",
                  api.notes.get("made.md", "").startswith("# Made"),
                  api.notes.get("made.md", "")[:30])

            print("\n7. settings persist and apply")
            route(page, "#/settings", ".page-settings .settings-grid")
            page.wait_for_timeout(600)
            check("the settings title is shown once",
                  page.locator(".page-settings .page-head h1").count() == 1,
                  page.locator(".page-settings .page-head h1").count())
            check("and no eyebrow repeats it above",
                  page.locator(".page-settings .eyebrow").count() == 0)
            check("the data panel is populated",
                  page.locator(".page-settings .data-cell").count() == 4,
                  page.locator(".page-settings .data-cell").count())
            check("the account card names the platform user",
                  "test" in page.inner_text(".page-settings .account-name"))

            page.locator(".page-settings .segmented").nth(0) \
                .locator("button", has_text="深色").click()
            page.wait_for_timeout(250)
            check("the dark theme is applied",
                  page.evaluate("() => document.documentElement.dataset.theme") == "dark")
            page.click('.page-settings .swatch[data-swatch="clay"]')
            page.wait_for_timeout(250)
            check("the accent is applied",
                  page.evaluate("() => document.documentElement.dataset.accent") == "clay")
            page.locator(".page-settings .segmented").nth(1) \
                .locator("button", has_text="大").click()
            page.wait_for_timeout(250)
            check("the font size is applied",
                  page.evaluate("() => document.documentElement.dataset.font") == "lg")

            page.locator(".page-settings .switch").click()
            page.wait_for_timeout(200)
            check("autosave is stored", settings_json(page).get("autosave") is False,
                  settings_json(page).get("autosave"))
            page.locator(".page-settings select").nth(1).select_option("import")
            page.wait_for_timeout(200)
            check("the default page is stored",
                  settings_json(page).get("defaultPage") == "import",
                  settings_json(page).get("defaultPage"))

            page.locator(".page-settings select").nth(0).select_option("en-us")
            page.wait_for_timeout(700)
            check("the interface switched language",
                  page.inner_text('#nav a[data-route="library"] span') == "Library",
                  page.inner_text('#nav a[data-route="library"] span'))
            check("the sidebar folders switched with it",
                  page.inner_text('#folder-list [data-folder=""] .folder-name') == "All notes",
                  page.inner_text('#folder-list [data-folder=""] .folder-name'))
            page.locator(".page-settings select").nth(0).select_option("zh-cn")
            page.wait_for_timeout(700)
            check("the interface switched back",
                  page.inner_text('#nav a[data-route="library"] span') == "文档库",
                  page.inner_text('#nav a[data-route="library"] span'))
            check("and the sidebar folders came back too",
                  page.inner_text('#folder-list [data-folder=""] .folder-name') == "全部笔记",
                  page.inner_text('#folder-list [data-folder=""] .folder-name'))

            before = len(state["requests"])
            page.locator(".page-settings button", has_text="重建搜索索引").click()
            page.wait_for_timeout(900)
            check("reindex called the scanner",
                  any(r[1].endswith("/index/scan")
                      for r in state["requests"][before:]),
                  [r[1] for r in state["requests"][before:]])

            page.locator(".page-settings button", has_text="重置外观与习惯设置").click()
            page.wait_for_selector(".modal-foot .btn-danger")
            page.click(".modal-foot .btn-danger")
            page.wait_for_timeout(800)
            restored = settings_json(page)
            check("reset restored the appearance defaults",
                  restored.get("theme") == "system" and
                  restored.get("accent") == "forest" and
                  restored.get("fontSize") == "md" and
                  restored.get("defaultPage") == "library", restored)

            print("\n8. the sidebar width can be dragged and is remembered")
            page.set_viewport_size({"width": 1280, "height": 820})
            route(page, "#/library", ".page-library .note-card")
            page.wait_for_timeout(400)
            width_before = page.evaluate(
                "() => Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)")
            grip = page.locator("#sidebar-resizer")
            box = grip.bounding_box()
            start_y = box["y"] + min(180, box["height"] / 2)
            page.mouse.move(box["x"] + box["width"] / 2, start_y)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 70, start_y, steps=6)
            page.mouse.up()
            page.wait_for_timeout(300)
            width_after = page.evaluate(
                "() => Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)")
            check("dragging the right edge widens the sidebar",
                  width_after >= width_before + 50,
                  "%d -> %d" % (width_before, width_after))
            stored_width = page.evaluate(
                "() => parseInt(localStorage.getItem('marknest.sidebarWidth'), 10)")
            check("the new width is stored", stored_width == width_after,
                  "%s vs %s" % (stored_width, width_after))
            page.reload(wait_until="load")
            page.wait_for_selector(".page-library .note-card", timeout=8000)
            page.wait_for_timeout(400)
            width_reload = page.evaluate(
                "() => Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)")
            check("the width survives a reload", width_reload == width_after,
                  "%d vs %d" % (width_reload, width_after))
            grip.focus()
            page.keyboard.press("Home")
            page.wait_for_timeout(250)
            width_reset = page.evaluate(
                "() => Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)")
            check("Home restores the default width", width_reset == 258, width_reset)

            print("\n9. the shell adapts to a narrow frame")
            page.set_viewport_size({"width": 900, "height": 760})
            route(page, "#/library", ".page-library .note-card")
            page.wait_for_timeout(500)
            check("the menu button appears",
                  page.locator("#btn-menu").is_visible())
            closed_right = page.evaluate(
                "() => document.querySelector('.sidebar').getBoundingClientRect().right")
            check("the sidebar starts off canvas (%.0f)" % closed_right,
                  closed_right <= 1, closed_right)
            page.click("#btn-menu")
            page.wait_for_timeout(350)
            check("the drawer opens",
                  page.evaluate(
                      "() => document.getElementById('app').classList.contains('is-menu-open')"))
            check("the scrim blocks the page",
                  page.locator("#scrim").is_visible())
            open_left = page.evaluate(
                "() => document.querySelector('.sidebar').getBoundingClientRect().left")
            check("the sidebar slid into view (%.0f)" % open_left, open_left >= -1)
            check("the resizer is hidden while the sidebar is a drawer",
                  not page.locator("#sidebar-resizer").is_visible())
            check("and the collapse toggle is hidden too",
                  not page.locator(".collapse-btn").is_visible())
            page.click("#scrim")
            page.wait_for_timeout(350)
            check("the scrim closes the drawer",
                  not page.evaluate(
                      "() => document.getElementById('app').classList.contains('is-menu-open')"))

            page.set_viewport_size({"width": 560, "height": 720})
            page.wait_for_timeout(400)
            page.click("#btn-menu")
            page.wait_for_timeout(350)
            check("the drawer still opens at 560px",
                  page.evaluate(
                      "() => document.getElementById('app').classList.contains('is-menu-open')"))
            page.click('.sidebar a[data-route="import"]')
            page.wait_for_timeout(700)
            check("choosing a page closes the drawer",
                  not page.evaluate(
                      "() => document.getElementById('app').classList.contains('is-menu-open')"))
            check("the import page mounted",
                  page.locator(".page-import .dropzone").count() == 1)

            print("\n10. the interface follows the TOS language")
            context2 = browser.new_context(viewport={"width": 1280, "height": 820},
                                           locale="en-US")
            context2.route(H.PROXY_GLOB, H.make_router(state))
            page2 = context2.new_page()
            page2.add_init_script(
                "try { if (!localStorage.getItem('tos_language')"
                " && !localStorage.getItem('langModel')) {"
                " localStorage.setItem('tos_language', 'zh-cn'); } } catch (e) {}")
            page2.goto(url, wait_until="load")
            page2.wait_for_selector(".page-library .note-card", timeout=8000)
            page2.wait_for_timeout(500)
            check("the TOS language beats the browser language",
                  page2.inner_text('#nav a[data-route="library"] span') == "文档库",
                  page2.inner_text('#nav a[data-route="library"] span'))
            page2.evaluate(
                "() => localStorage.setItem('tos_language', 'en-us')")
            page2.reload(wait_until="load")
            page2.wait_for_selector(".page-library .note-card", timeout=8000)
            page2.wait_for_timeout(500)
            check("a changed TOS language is picked up on load",
                  page2.inner_text('#nav a[data-route="library"] span') == "Library",
                  page2.inner_text('#nav a[data-route="library"] span'))
            page2.evaluate(
                "() => localStorage.setItem('tos_language', 'ja-jp')")
            page2.reload(wait_until="load")
            page2.wait_for_selector(".page-library .note-card", timeout=8000)
            page2.wait_for_timeout(500)
            check("a newly added dictionary is used for its TOS language",
                  page2.inner_text('#nav a[data-route="library"] span') == "ライブラリ",
                  page2.inner_text('#nav a[data-route="library"] span'))
            page2.evaluate(
                "() => localStorage.setItem('tos_language', 'hu-hu')")
            page2.reload(wait_until="load")
            page2.wait_for_selector(".page-library .note-card", timeout=8000)
            page2.wait_for_timeout(500)
            check("a TOS language without a dictionary renders in English",
                  page2.inner_text('#nav a[data-route="library"] span') == "Library",
                  page2.inner_text('#nav a[data-route="library"] span'))
            page2.evaluate(
                "() => { localStorage.removeItem('tos_language');"
                " localStorage.setItem('langModel', 'de-de'); }")
            page2.reload(wait_until="load")
            page2.wait_for_selector(".page-library .note-card", timeout=8000)
            page2.wait_for_timeout(500)
            check("the TOS langModel key is followed too",
                  page2.inner_text('#nav a[data-route="library"] span') == "Bibliothek",
                  page2.inner_text('#nav a[data-route="library"] span'))
            page2.evaluate(
                "() => { localStorage.setItem('langModel', 'ko-kr');"
                " window.dispatchEvent(new StorageEvent('storage',"
                " {key: 'langModel', newValue: 'ko-kr'})); }")
            page2.wait_for_timeout(900)
            check("a live TOS language change refreshes the open page",
                  page2.inner_text('.page-library .page-title') == "모든 노트",
                  page2.inner_text('.page-library .page-title'))
            route(page2, "#/settings", ".page-settings .settings-grid")
            page2.wait_for_timeout(400)
            check("the language selector starts on Follow TOS",
                  page2.eval_on_selector(
                      ".page-settings select", "el => el.value") == "",
                  page2.eval_on_selector(".page-settings select", "el => el.value"))
            context2.close()

            print("\n11. an emptied library reports no stale revisions")
            api.notes.clear()
            api.versions.clear()
            page.set_viewport_size({"width": 1280, "height": 820})
            route(page, "#/settings", ".page-settings .settings-grid")
            page.wait_for_timeout(700)
            cells = page.locator(
                ".page-settings .data-cell .data-value").all_inner_texts()
            check("the note count is zero", cells and cells[0] == "0", cells)
            check("and the revision count is zero",
                  len(cells) > 1 and cells[1] == "0", cells)

            page.reload(wait_until="load")
            page.wait_for_selector(".page-settings .settings-grid", timeout=8000)
            route(page, "#/library", ".page-library .empty-state")
            page.wait_for_timeout(300)
            check("the sidebar folder hint talks about folders, not notes",
                  page.inner_text("#folder-list .folder-empty") ==
                  "暂无子文件夹，笔记都保存在根目录。",
                  page.inner_text("#folder-list .folder-empty"))
            route(page, "#/import", ".page-import .dropzone")
            check("the destination picker is hidden when the library has no subfolders",
                  page.locator(".page-import .panel:has(.panel-title:text-is('导入到'))")
                  .is_hidden())
            check("the rest of the import page is still there",
                  page.locator(".page-import .text-create").is_visible())

            check("no uncaught error during the run", not errors, "; ".join(errors))
            browser.close()
    finally:
        httpd.shutdown()

    print("\n" + "-" * 62)
    if failures:
        print("FAILED: " + "; ".join(failures))
        return 1
    print("PASSED: the library searches, scopes, creates and deletes; the import\n"
          "        queue reports created, failed and skipped verdicts and retries;\n"
          "        settings apply, persist and reset; the shell drawers at 900px\n"
          "        and 560px without losing a control.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
