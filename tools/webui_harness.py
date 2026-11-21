#!/usr/bin/env python3
"""Shared harness for the browser-side verification of the MarkNest WebUI.

Serves the real ``webui/`` directory over loopback and stubs the platform API
with an in-memory note library, so the layout and the pages can be driven in a
real browser without a NAS. ``measure_topbar.py`` and ``verify_editor.py``
build on this rather than each growing their own copy.

The stub answers the same envelope the backend does - ``{"code":0,...}`` - and,
importantly, it is *not* a mock of the frontend's expectations: it is written
against the API in ``usr/local/marknest/lib/api.py``, so a shape that drifts
there fails here.
"""

import datetime
import http.server
import json
import os
import re
import socketserver
import threading
import time
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBUI = os.path.join(REPO_ROOT, "webui")

with open(os.path.join(REPO_ROOT, "VERSION"), "r", encoding="utf-8") as _version_file:
    VERSION = _version_file.read().strip()

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
    "notes/pictures.md": "# Pictures\n\n![a dot](.assets/dot.png)\n",
    "projects/roadmap.md": "# Roadmap\n\n## Now\n\n- redesign the shell\n\n"
                           "## Next\n\n- wikilinks\n",
}

RAW_HTML_NOTE = "# Injection\n\n<script>window.__pwned = true;</script>\n\n<img src=x onerror=\"window.__pwned = true\">\n"

#: One transparent pixel, so the authenticated image path can be exercised.
PNG_DOT = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000000020001e221bc330000000049454e44"
    "ae426082"
)

DEMO_NOTE_EXTENSIONS = (".md", ".markdown", ".mdown")


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _now_ns():
    return time.time_ns()


def _title_of(path, content):
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return os.path.splitext(os.path.basename(path))[0]


def _excerpt_of(content):
    text = re.sub(r"[#>*_`|]", " ", content)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


class StubApi:
    """In-memory stand-in for the backend, with a real revision counter."""

    def __init__(self):
        self.notes = dict(NOTES)
        self.revs = {}
        self.mtimes = {}
        self.versions = {}
        self.assets = {"notes/.assets/dot.png": PNG_DOT}
        self.folders = set()
        self.requests = []
        self.next_rev = 0
        self.next_version = 0
        for index, path in enumerate(sorted(self.notes)):
            self.next_rev += 1
            self.revs[path] = "rev-%d" % self.next_rev
            self.mtimes[path] = 1760000000000000000 + index * 10 ** 9
        # A pre-existing snapshot makes the version dialog non-empty on first open.
        self._snapshot("welcome.md", "# Welcome to MarkNest\n\nFirst draft.\n")

    # ------------------------------------------------------------ bookkeeping

    def rev(self, path):
        return self.revs.get(path, "")

    def touch(self, path):
        self.next_rev += 1
        self.revs[path] = "rev-%d" % self.next_rev
        self.mtimes[path] = _now_ns()
        return self.revs[path]

    def _snapshot(self, path, content):
        self.next_version += 1
        item = {
            "id": self.next_version,
            "created_at": _now_iso(),
            "created_ns": _now_ns(),
            "size": len(content.encode("utf-8")),
            "rev": self.rev(path),
            "content": content,
        }
        self.versions.setdefault(path, []).insert(0, item)
        return item

    def note_doc(self, path, created=False):
        content = self.notes[path]
        return {
            "path": path,
            "name": os.path.basename(path),
            "title": _title_of(path, content),
            "content": content,
            "rev": self.rev(path),
            "size": len(content.encode("utf-8")),
            "mtime_ns": self.mtimes.get(path, 0),
            "eol": "lf",
            "bom": False,
            "writable": True,
            "created": created,
        }

    # -------------------------------------------------------------- documents

    def all_folders(self):
        found = set(self.folders)
        for path in self.notes:
            parts = path.split("/")[:-1]
            accum = ""
            for part in parts:
                accum = part if not accum else accum + "/" + part
                found.add(accum)
        result = []
        for path in sorted(found):
            result.append({
                "path": path,
                "name": path.split("/")[-1],
                "depth": path.count("/"),
                "count": sum(1 for note in self.notes if note.startswith(path + "/")),
            })
        return result

    def library_view(self, limit=2000):
        notes = []
        for path in sorted(self.notes):
            if not path.lower().endswith(DEMO_NOTE_EXTENSIONS):
                continue
            content = self.notes[path]
            notes.append({
                "path": path,
                "name": os.path.basename(path),
                "title": _title_of(path, content),
                "folder": path.rsplit("/", 1)[0] if "/" in path else "",
                "size": len(content.encode("utf-8")),
                "mtime_ns": self.mtimes.get(path, 0),
                "indexed_at": _now_iso(),
                "excerpt": _excerpt_of(content),
            })
        notes.sort(key=lambda note: note["mtime_ns"], reverse=True)
        notes = notes[:limit]
        totals = {
            "notes": len(notes),
            "bytes": sum(note["size"] for note in notes),
        }
        return {
            "notes": notes,
            "folders": self.all_folders(),
            "count": len(notes),
            "truncated": False,
            "totals": totals,
        }

    def stats(self):
        view = self.library_view()
        total = 4 * 1024 ** 4
        used = int(1.25 * 1024 ** 4)
        return {
            "notes": view["count"],
            "bytes": view["totals"]["bytes"],
            "disk": {"total": total, "used": used, "free": total - used},
            "folders": len(view["folders"]),
            "versions": (sum(len(items) for items in self.versions.values())
                         if self.notes else 0),
            "attachments": False,
            "engine": "fts5",
            "last_indexed": _now_iso(),
            "index_notes": view["count"],
        }

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
                entries.append({
                    "name": rest,
                    "path": full,
                    "type": "note" if rest.lower().endswith(DEMO_NOTE_EXTENSIONS) else "other",
                    "note": rest.lower().endswith(DEMO_NOTE_EXTENSIONS),
                    "size": len(self.notes[full].encode("utf-8")),
                    "mtime_ns": self.mtimes.get(full, 0),
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
                hits.append({"path": path, "title": _title_of(path, body), "score": 0.0,
                             "snippet": _excerpt_of(body), "engine": "fts5"})
        return {"query": query, "hits": hits, "count": len(hits), "engine": "fts5"}

    # ---------------------------------------------------------------- import

    def import_files(self, files, target_dir, conflict):
        results = []
        created = skipped = failed = 0
        for name, relative in files:
            segments = []
            invalid = False
            for part in ((target_dir + "/" if target_dir else "") + relative).split("/"):
                part = part.strip()
                if not part or part in (".", ".."):
                    continue
                if part.startswith("."):
                    invalid = True
                    break
                segments.append(part)
            if invalid or not segments:
                failed += 1
                results.append({"name": name, "path": "", "status": "failed",
                                "code": 3012, "message": "that name is not available"})
                continue
            if not segments[-1].lower().endswith(DEMO_NOTE_EXTENSIONS):
                if os.path.splitext(segments[-1])[1]:
                    failed += 1
                    results.append({"name": name, "path": "", "status": "failed",
                                    "code": 3012, "message": "only Markdown can be imported"})
                    continue
                segments[-1] += ".md"
            rel = "/".join(segments)
            if rel in self.notes and conflict == "skip":
                skipped += 1
                results.append({"name": name, "path": rel, "status": "skipped",
                                "message": "a note already exists at that path"})
                continue
            final = rel
            attempt = 1
            while final in self.notes:
                attempt += 1
                stem, ext = os.path.splitext(rel)
                final = "%s (%d)%s" % (stem, attempt, ext)
            self.notes[final] = "# %s\n\nImported from %s.\n" % (
                os.path.splitext(os.path.basename(final))[0], name)
            self.touch(final)
            created += 1
            results.append({"name": name, "path": final, "status": "created", "message": ""})
        return {
            "results": results,
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "total": len(files),
        }


def _ok(route, payload):
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"code": 0, "message": "ok", "data": payload}))


def _fail(route, status, code, message):
    route.fulfill(status=status, content_type="application/json",
                  body=json.dumps({"code": code, "message": message, "data": None}))


RELATIVE_RE = re.compile(r'name="relative"\r\n\r\n([^\r]*)\r\n')
FILENAME_RE = re.compile(r'filename="([^"]*)"')
FIELD_RE = re.compile(r'name="(dir|conflict)"\r\n\r\n([^\r]*)\r\n')


def make_router(state):
    def handler(route, request):
        url = urllib.parse.urlsplit(request.url)
        path = url.path
        query = urllib.parse.parse_qs(url.query)
        api = state["api"]
        state["requests"].append((request.method, path, query))

        if path.endswith("/health"):
            return _ok(route, {
                "status": "ok", "version": VERSION, "app_id": "marknest",
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
                "features": {"search": True, "attachments": True,
                             "versions": True, "import": True,
                             "wiki_links": False, "backlinks": False},
                "version_keep": 50,
                "max_import_files": 50,
                "editor": "codemirror6",
            })
        if path.endswith("/me"):
            return _ok(route, {
                "user": "test", "library_path": api.tree("")["root"],
                "exists": True, "readable": True, "writable": True,
                "read_reason": "", "write_reason": "",
            })
        if path.endswith("/library"):
            limit = int((query.get("limit") or ["2000"])[0])
            return _ok(route, api.library_view(limit))
        if path.endswith("/stats"):
            return _ok(route, api.stats())
        if path.endswith("/folders/new") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = (body.get("path") or "").strip()
            if not target:
                return _fail(route, 400, 1400, "parameter path is required")
            api.folders.add(target)
            return _ok(route, {"path": target, "created": True})
        if path.endswith("/folders") and request.method == "DELETE":
            target = (query.get("path") or [""])[0]
            if not target:
                return _fail(route, 400, 1400, "parameter path is required")
            if any(note.startswith(target + "/") for note in api.notes):
                return _fail(route, 409, 3015, "the folder is not empty")
            api.folders.discard(target)
            return _ok(route, {"path": target, "deleted": True})
        if path.endswith("/folders"):
            folders = api.all_folders()
            return _ok(route, {"folders": folders, "count": len(folders)})
        if path.endswith("/index/status"):
            return _ok(route, {"notes": len(api.notes), "last_scan": 0,
                               "last_scan_ago": 1.0, "engine": "fts5",
                               "enabled": True, "interval": 30})
        if path.endswith("/index/scan") and request.method == "POST":
            return _ok(route, {"scanned": len(api.notes), "removed": 0})
        if path.endswith("/search"):
            return _ok(route, api.search((query.get("q") or [""])[0]))
        if path.endswith("/tree"):
            return _ok(route, api.tree((query.get("path") or [""])[0]))

        # ---------------------------------------------------- version history
        if path.endswith("/versions/item"):
            target = (query.get("path") or [""])[0]
            version_id = int((query.get("id") or ["0"])[0] or 0)
            for item in api.versions.get(target, []):
                if item["id"] == version_id:
                    return _ok(route, item)
            return _fail(route, 404, 3016, "that version does not exist")
        if path.endswith("/versions/restore") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = body.get("path") or ""
            version_id = int(body.get("id") or 0)
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            chosen = None
            for item in api.versions.get(target, []):
                if item["id"] == version_id:
                    chosen = item
            if chosen is None:
                return _fail(route, 404, 3016, "that version does not exist")
            api._snapshot(target, api.notes[target])
            api.notes[target] = chosen["content"]
            api.touch(target)
            return _ok(route, api.note_doc(target))
        if path.endswith("/versions"):
            target = (query.get("path") or [""])[0]
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            items = [
                {key: item[key] for key in ("id", "created_at", "created_ns", "size", "rev")}
                for item in api.versions.get(target, [])
            ]
            return _ok(route, {"path": target, "keep": 50, "versions": items})

        # -------------------------------------------------------- attachments
        if path.endswith("/attachments") and request.method == "POST":
            target_dir = (query.get("dir") or [""])[0]
            name = "pasted-0000abcd.png"
            relative = ".assets/" + name
            full = (target_dir + "/" if target_dir else "") + relative
            api.assets[full] = PNG_DOT
            return _ok(route, {
                "path": full,
                "name": name,
                "relative": relative,
                "dir": target_dir,
                "size": len(PNG_DOT),
                "mime": "image/png",
                "markdown": "![pasted](%s)" % relative,
            })
        if path.endswith("/attachments") and request.method == "GET":
            target = (query.get("path") or [""])[0]
            data = api.assets.get(target)
            if data is None:
                return _fail(route, 404, 3010, "the attachment does not exist")
            route.fulfill(status=200, content_type="image/png", body=data)
            return None

        # -------------------------------------------------------------- import
        if path.endswith("/notes/import") and request.method == "POST":
            raw = request.post_data or ""
            relatives = RELATIVE_RE.findall(raw)
            names = FILENAME_RE.findall(raw)
            files = []
            for index, name in enumerate(names):
                relative = relatives[index] if index < len(relatives) else name
                files.append((name, relative))
            target_dir = ""
            conflict = "rename"
            for part in FIELD_RE.finditer(raw):
                if part.group(1) == "dir":
                    target_dir = part.group(2)
                elif part.group(2) in ("rename", "skip"):
                    conflict = part.group(2)
            if not files:
                return _fail(route, 400, 1400, "no files were uploaded")
            return _ok(route, api.import_files(files, target_dir, conflict))

        # --------------------------------------------------------------- notes
        if path.endswith("/notes/save") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = body.get("path") or ""
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            if body.get("base_rev") and body["base_rev"] != api.rev(target) and not body.get("force"):
                return _fail(route, 409, 3007, "the note was changed by someone else")
            content = body.get("content") or ""
            if content != api.notes[target]:
                api._snapshot(target, api.notes[target])
            api.notes[target] = content
            api.touch(target)
            return _ok(route, api.note_doc(target))

        if path.endswith("/notes/new") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            target = body.get("path") or ""
            if not target:
                return _fail(route, 400, 1400, "parameter path is required")
            if target in api.notes:
                return _fail(route, 409, 3006, "a note already exists at that path")
            api.notes[target] = body.get("content") or ""
            api.touch(target)
            return _ok(route, api.note_doc(target, created=True))

        if path.endswith("/notes/rename") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            source = body.get("from") or ""
            target = body.get("to") or ""
            if source not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            if target in api.notes and not body.get("overwrite"):
                return _fail(route, 409, 3006, "a note already exists at that path")
            api.notes[target] = api.notes.pop(source)
            api.revs[target] = api.revs.pop(source, "")
            api.mtimes[target] = api.mtimes.pop(source, _now_ns())
            if source in api.versions:
                api.versions[target] = api.versions.pop(source)
            api.touch(target)
            return _ok(route, api.note_doc(target))

        if path.endswith("/notes") and request.method == "DELETE":
            target = (query.get("path") or [""])[0]
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            api.notes.pop(target, None)
            api.revs.pop(target, None)
            api.mtimes.pop(target, None)
            api.versions.pop(target, None)
            return _ok(route, {"path": target, "deleted": True})

        if path.endswith("/notes"):
            target = (query.get("path") or [""])[0]
            if target not in api.notes:
                return _fail(route, 404, 3005, "the note does not exist")
            return _ok(route, api.note_doc(target))

        return _fail(route, 404, 1404, "no such endpoint: %s" % path)

    return handler


def serve(directory=None):
    """Serve the WebUI on a loopback port; returns ``(httpd, port)``."""
    target = directory or WEBUI

    class Quiet(http.server.SimpleHTTPRequestHandler):
        # Some Python builds resolve .svg to the non-standard "image/svg",
        # which Chromium refuses to decode inside an <img>.
        extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map)
        extensions_map[".svg"] = "image/svg+xml"

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
        for path in notes:
            if path not in api.revs:
                api.touch(path)
    return {"api": api, "requests": []}


def boot_page(page, url, lang="zh-cn"):
    """Load the application with a fixed language so assertions are stable."""
    page.evaluate(
        "(value) => { try { localStorage.setItem('marknest.lang', value); } catch (e) {} }",
        lang,
    )
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1200)
