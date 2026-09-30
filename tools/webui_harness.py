#!/usr/bin/env python3
"""Shared harness for the browser-side verification of the MarkNest WebUI.

Serves the real ``webui/`` directory over loopback and stubs the platform API
with an in-memory note library, so the layout and the editor can be driven in a
real browser without a NAS. Both ``measure_topbar.py`` and ``verify_editor.py``
build on this rather than each growing their own copy.

The stub answers the same envelope the backend does - ``{"code":0,...}`` - and,
importantly, it is *not* a mock of the frontend's expectations: it is written
against the API in ``usr/local/marknest/lib/api.py``, so a shape that drifts
there fails here.
"""

import http.server
import json
import os
import socketserver
import threading
import time
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBUI = os.path.join(REPO_ROOT, "webui")

PROXY_GLOB = "**/v2/proxy/marknest/**"

#: A note library large enough to be interesting and small enough to reason
#: about. The long note exists so that scroll synchronisation has something to
#: actually synchronise over.
NOTES = {
    "welcome.md": "# Welcome to MarkNest\n\n"
                  "This is a **Markdown** note. Edit it and the preview follows.\n\n"
                  "## Lists\n\n- one\n- two\n- [ ] a task\n\n"
                  "## Code\n\n```\nplain text, no language highlighting\n```\n\n"
                  "> A quote.\n\n| a | b |\n| - | - |\n| 1 | 2 |\n",
    "notes/long.md": "# Long note\n\n" + "\n\n".join(
        "## Section %d\n\nParagraph %d with some words in it." % (i, i)
        for i in range(1, 61)
    ) + "\n",
    "notes/plain.txt": "just text\n",
}

#: What the backend opens as a note, mirroring the default of
#: ``MARKNEST_NOTE_EXTENSIONS`` in ``usr/local/marknest/lib/config.py``. ``.txt``
#: belongs in this list: the backend accepts it on every write and the picker's
#: accept list already offers it, so a stub that left it out hid a real note
#: from the picker's library tab and left one of the four accepted types with no
#: test that ever saw it.
NOTE_EXTENSIONS = (".md", ".markdown", ".mdown", ".txt")

RAW_HTML_NOTE = "# Injection\n\n<script>window.__pwned = true;</script>\n\n<img src=x onerror=\"window.__pwned = true\">\n"

#: How stale each note is, in minutes, for ``/recent``. Ages are offsets from
#: "now" and are applied at request time rather than frozen into ``NOTES``: a
#: constant epoch ages with the suite, so an assertion reading "5 分钟前" today
#: reads "2 小时前" next week, and the failure would have nothing to do with the
#: code. Keyed by path, so a note keeps its place in the order however the
#: ``notes`` dictionary is later mutated; a note not named here - one a test
#: added - is treated as three days old.
RECENT_AGES = {
    "welcome.md": 5,
    "notes/long.md": 90,
    "notes/plain.txt": 60 * 26,
}
RECENT_DEFAULT_AGE = 60 * 24 * 3


class StubApi:
    """In-memory stand-in for the backend, with a real revision counter."""

    def __init__(self):
        self.notes = dict(NOTES)
        self.revs = {path: "rev-%d" % index for index, path in enumerate(sorted(NOTES))}
        self.requests = []
        self.next_rev = len(NOTES)

    def rev(self, path):
        return self.revs.get(path, "")

    def touch(self, path):
        self.next_rev += 1
        self.revs[path] = "rev-%d" % self.next_rev
        return self.revs[path]

    def tree(self, path):
        prefix = (path + "/") if path else ""
        entries = []
        seen_dirs = set()
        for full in sorted(self.notes):
            if prefix and not full.startswith(prefix):
                continue
            rest = full[len(prefix):]
            if "/" in rest:
                top = rest.split("/")[0]
                if top in seen_dirs:
                    continue
                seen_dirs.add(top)
                entries.append({"name": top, "path": prefix + top, "type": "dir",
                                "note": False, "size": 0, "mtime_ns": 0})
            else:
                is_note = rest.lower().endswith(NOTE_EXTENSIONS)
                entries.append({
                    "name": rest,
                    "path": full,
                    # library.py's shape, exactly: `type` is "dir" for a folder
                    # and "file" for a file, rewritten to "other" when the file
                    # is not one this application will open. "Is this a note?" is
                    # the separate `note` boolean. There is no "note" type - the
                    # stub used to send one, which let the tree's guard ask for a
                    # value no backend has ever emitted and stay green.
                    "type": "file" if is_note else "other",
                    "note": is_note,
                    "size": len(self.notes[full].encode("utf-8")),
                    "mtime_ns": 0,
                })
        entries.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))
        return {
            "path": path,
            "root": "/Volume1/marknest-data/users/test/notes",
            "readable": True,
            "writable": True,
            "entries": entries,
            "count": len(entries),
            "truncated": False,
        }

    def search(self, query):
        hits = []
        for path, body in sorted(self.notes.items()):
            if query.lower() in body.lower():
                hits.append({"path": path, "title": path, "score": 0.0,
                             "snippet": body[:120], "engine": "fts5"})
        return {"query": query, "hits": hits, "count": len(hits), "engine": "fts5"}

    def recent(self, raw_limit=None):
        """The home screen's list, most recently modified first.

        Mirrors ``GET /recent`` in ``usr/local/marknest/lib/api.py``: the same
        envelope keys, the same default of 12 and ceiling of 50, and the same
        ordering. The stub exists because the home pane cannot be exercised
        without it - and because a stub that answered a different shape would
        let the frontend and the backend drift apart while both suites stayed
        green.
        """
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 12
        limit = max(1, min(limit, 50))
        # One "now" for the whole request, so the entries keep their relative
        # spacing rather than each being measured against a slightly later
        # clock.
        now = time.time_ns()
        rows = []
        for path in sorted(self.notes):
            minutes = RECENT_AGES.get(path, RECENT_DEFAULT_AGE)
            rows.append({
                "path": path,
                "title": path,
                "mtime_ns": now - minutes * 60 * 10 ** 9,
                "size": len(self.notes[path].encode("utf-8")),
            })
        rows.sort(key=lambda row: row["mtime_ns"], reverse=True)
        rows = rows[:limit]
        return {"recent": rows, "count": len(rows), "limit": limit}


def _ok(route, payload):
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"code": 0, "message": "ok", "data": payload}))


def _fail(route, status, code, message):
    route.fulfill(status=status, content_type="application/json",
                  body=json.dumps({"code": code, "message": message, "data": None}))


def make_router(state):
    def handler(route, request):
        url = urllib.parse.urlsplit(request.url)
        path = url.path
        query = urllib.parse.parse_qs(url.query)
        api = state["api"]
        state["requests"].append((request.method, path, query))

        if path.endswith("/health"):
            return _ok(route, {
                "status": "ok", "version": "1.0.0", "app_id": "marknest",
                "library_ready": True, "library_readable": True,
                "library_writable": True, "library_users": 1,
                "share_name": "marknest-data",
                "index": {"engine": "fts5", "notes": len(api.notes)},
                "degraded_features": [], "auth_enforced": True,
            })
        if path.endswith("/options"):
            return _ok(route, {
                "note_extensions": [".md", ".markdown", ".mdown", ".txt"],
                "max_note_mb": 8, "max_attachment_mb": 64,
                "tree_max_entries": 2000, "search_max_hits": 200,
                "search_engine": "fts5",
                "features": {"search": True, "attachments": False,
                             "wiki_links": False, "backlinks": False},
                "editor": "codemirror6",
            })
        if path.endswith("/me"):
            return _ok(route, {
                "user": "test", "library_path": api.tree("")["root"],
                "exists": True, "readable": True, "writable": True,
                "read_reason": "", "write_reason": "",
            })
        if path.endswith("/index/status"):
            return _ok(route, {"notes": len(api.notes), "last_scan": 0,
                               "last_scan_ago": 1.0, "engine": "fts5",
                               "enabled": True, "interval": 30})
        if path.endswith("/search"):
            return _ok(route, api.search((query.get("q") or [""])[0]))
        if path.endswith("/recent"):
            return _ok(route, api.recent((query.get("limit") or [None])[0]))
        if path.endswith("/tree"):
            return _ok(route, api.tree((query.get("path") or [""])[0]))

        if path.endswith("/notes/save") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = body.get("path") or ""
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            if body.get("base_rev") and body["base_rev"] != api.rev(target) and not body.get("force"):
                return _fail(route, 409, 3007, "the note was changed by someone else")
            api.notes[target] = body.get("content") or ""
            rev = api.touch(target)
            return _ok(route, {"path": target, "name": os.path.basename(target),
                               "content": api.notes[target], "rev": rev,
                               "size": len(api.notes[target]), "mtime_ns": 0,
                               "eol": "lf", "bom": False, "writable": True,
                               "created": False})

        if path.endswith("/notes/new") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = body.get("path") or ""
            if target in api.notes:
                return _fail(route, 409, 3006, "a note already exists at that path")
            api.notes[target] = body.get("content") or ""
            rev = api.touch(target)
            return _ok(route, {"path": target, "name": os.path.basename(target),
                               "content": api.notes[target], "rev": rev,
                               "size": len(api.notes[target]), "mtime_ns": 0,
                               "eol": "lf", "bom": False, "writable": True,
                               "created": True})

        if path.endswith("/notes/rename") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            source = body.get("from") or ""
            target = body.get("to") or ""
            if source not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            api.notes[target] = api.notes.pop(source)
            api.revs.pop(source, None)
            rev = api.touch(target)
            return _ok(route, {"path": target, "name": os.path.basename(target),
                               "content": api.notes[target], "rev": rev,
                               "size": len(api.notes[target]), "mtime_ns": 0,
                               "eol": "lf", "bom": False, "writable": True,
                               "created": False})

        if path.endswith("/notes") and request.method == "DELETE":
            target = (query.get("path") or [""])[0]
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            api.notes.pop(target, None)
            api.revs.pop(target, None)
            return _ok(route, {"path": target, "deleted": True})

        if path.endswith("/notes"):
            target = (query.get("path") or [""])[0]
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            return _ok(route, {"path": target, "name": os.path.basename(target),
                               "content": api.notes[target], "rev": api.rev(target),
                               "size": len(api.notes[target]), "mtime_ns": 0,
                               "eol": "lf", "bom": False, "writable": True})

        return _fail(route, 404, 1404, "no such endpoint: %s" % path)

    return handler


def serve(directory=None):
    """Serve the WebUI on a loopback port; returns ``(httpd, port)``."""
    target = directory or WEBUI

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=target, **kwargs)

        def log_message(self, *args):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Quiet)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def new_state(notes=None):
    api = StubApi()
    if notes:
        api.notes.update(notes)
        for index, path in enumerate(sorted(api.notes)):
            api.revs.setdefault(path, "rev-%d" % index)
    return {"api": api, "requests": []}


def boot_page(page, url, lang="zh-cn"):
    """Load the application with a fixed language so assertions are stable."""
    page.evaluate(
        "(value) => { try { localStorage.setItem('marknest.lang', value); } catch (e) {} }",
        lang,
    )
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1200)
