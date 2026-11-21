"""HTTP API surface.

Every endpoint is reachable both through the platform proxy
(``/v2/proxy/marknest/<api>``) and directly on the Unix socket at ``/<api>``.
Path normalisation accepts both forms so that the backend behaves identically
under either proxy mode.

Handlers return bare data; ``server.py`` wraps it in the response envelope, and
handlers signal failure only by raising a :class:`MarkNestError` subclass. That
split is what keeps every error on the wire carrying a code the frontend can
localise instead of an English sentence written at the call site.
"""

import json
import os
import re
import urllib.parse

from . import __version__
from . import index as indexer
from . import library
from .auth import resolve_identity, verify_request
from .config import config
from .db import store
from .errors import BadRequest, MarkNestError, MethodNotAllowed, NotFound, NoteExists
from .history import history_store
from .http_util import RawResponse
from .library import probe_readable, probe_writable
from .logging_setup import get_logger

log = get_logger("api")

#: Paths that answer without a resolved user. ``/health`` is polled before sign
#: in and must never leak whose library is being described; ``/options`` is
#: static capability data that the editor needs to configure itself.
USER_FREE_PATHS = ("/health", "/options")

_ATTACHMENT_RE = re.compile(r"^/attachments/([^/]+)$")


def normalize_path(raw_path):
    """Reduce any accepted path shape to the canonical ``/api`` form.

    Accepted inputs, all mapping to ``/notes``::

        /v2/proxy/marknest/notes   (platform proxy, documented form)
        /marknest/notes            (config.ini "path")
        /notes                     (direct on the Unix socket)

    ``/v2/proxy/marknest`` and ``/marknest`` both map to ``/``.
    """
    path = (raw_path or "/").split("?")[0]
    if not path.startswith("/"):
        path = "/" + path

    segments = [item for item in path.split("/") if item]

    # Strip the platform proxy prefix: /v2/proxy/<app_id>/...
    if len(segments) >= 2 and segments[0] == "v2" and segments[1] == "proxy":
        segments = segments[2:]

    # Strip the application prefix: /<app_id>/...
    if segments and segments[0] == config.app_id:
        segments = segments[1:]

    canonical = "/" + "/".join(segments)
    return canonical if canonical != "/" else "/"


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value, field, default=0, minimum=None):
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BadRequest("%s must be a number" % field)
    if minimum is not None and number < minimum:
        raise BadRequest("%s must be at least %d" % (field, minimum))
    return number


def _note_name(rel_path):
    return os.path.basename(rel_path or "")


def _note_title(title, rel_path):
    name = _note_name(rel_path)
    stem = os.path.splitext(name)[0] if name else rel_path
    return (title or "").strip() or stem or rel_path


def _excerpt(body, limit=220):
    """A readable one-line preview from Markdown source.

    Deliberately crude: the card shows a hint, not a render. Order matters -
    code fences, images and links are removed before punctuation, because a URL
    is full of characters that would otherwise survive into the excerpt.
    """
    text = body or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`~>#|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].strip()


def _folder_of(rel_path):
    return (rel_path or "").rpartition("/")[0]


def _disk_usage(path):
    """Bytes used and available on the volume that holds the notes share."""
    if not path:
        return None
    try:
        st = os.statvfs(path)
    except (OSError, AttributeError):
        return None
    total = int(st.f_frsize * st.f_blocks)
    free = int(st.f_frsize * st.f_bavail)
    return {
        "total": total,
        "free": free,
        "used": max(0, total - free),
    }


def _library_view(user, limit):
    notes = []
    for row in store.list_notes(user, limit=limit):
        rel_path = row["rel_path"]
        notes.append({
            "path": rel_path,
            "name": _note_name(rel_path),
            "title": _note_title(row.get("title"), rel_path),
            "folder": _folder_of(rel_path),
            "size": int(row.get("size_bytes") or 0),
            "mtime_ns": int(row.get("mtime_ns") or 0),
            "indexed_at": row.get("indexed_at") or "",
            "excerpt": _excerpt(row.get("excerpt")),
        })
    folders = library.list_folders(user)
    counts = {}
    for note in notes:
        folder = note["folder"]
        while folder:
            counts[folder] = counts.get(folder, 0) + 1
            folder = _folder_of(folder)
    for folder in folders:
        folder["count"] = counts.get(folder["path"], 0)
    totals = store.totals(user)
    return {
        "notes": notes,
        "folders": folders,
        "count": len(notes),
        "truncated": len(notes) >= limit,
        "totals": totals,
    }


class Api:
    """Stateless dispatcher for every public endpoint."""

    # ------------------------------------------------------------------ health

    def get_health(self, request):
        """Capability and library state. Deliberately user-neutral.

        This endpoint is reachable before sign in, so it must describe the
        installation without describing anybody's notes. It reports how many
        users have a library - a count, not a roll call.
        """
        summary = library.summary()
        return {
            "status": "ok" if summary.get("library_ready") else "degraded",
            "version": __version__,
            "app_id": config.app_id,
            "library_ready": bool(summary.get("library_ready")),
            "library_readable": bool(summary.get("readable")),
            "library_writable": bool(summary.get("writable")),
            "library_users": int(summary.get("users") or 0),
            "share_name": config.share_name,
            "index": {
                "engine": "fts5" if store.fts else "scan",
                "notes": store.count(),
            },
            "degraded_features": [] if summary.get("library_ready") else ["library"],
            "auth_enforced": config.require_auth,
        }

    def get_options(self, request):
        return {
            "note_extensions": list(config.note_extensions),
            "max_note_mb": config.max_note_bytes // (1024 * 1024),
            "max_attachment_mb": config.max_attachment_bytes // (1024 * 1024),
            "tree_max_entries": config.tree_max_entries,
            "search_max_hits": config.search_max_hits,
            "search_engine": "fts5" if store.fts else "scan",
            "features": {
                "search": True,
                "attachments": True,
                "versions": True,
                "import": True,
                "wiki_links": False,
                "backlinks": False,
            },
            "version_keep": config.version_keep,
            "max_import_files": config.max_import_files,
            "editor": "codemirror6",
        }

    def get_me(self, request):
        """The resolved identity and the measured state of that user's library."""
        user = request.user
        root = config.user_notes_root(user)
        readable, read_reason = False, ""
        writable, write_reason = False, ""
        if root and os.path.isdir(root):
            readable, read_reason = probe_readable(root)
            writable, write_reason = probe_writable(root)
        return {
            "user": user,
            "library_path": root,
            "exists": bool(root) and os.path.isdir(root),
            "readable": readable,
            "writable": writable,
            "read_reason": read_reason,
            "write_reason": write_reason,
        }

    # ------------------------------------------------------------------ library

    def get_library(self, request):
        """Flat note listing for the library page."""
        user = request.user
        indexer.maybe_scan(user)
        limit = min(
            request.param_int("limit", config.tree_max_entries, minimum=1),
            config.tree_max_entries,
        )
        return _library_view(user, limit)

    def get_stats(self, request):
        user = request.user
        indexer.maybe_scan(user)
        folder = (request.param("folder") or "").strip().strip("/")
        totals = store.totals(user, folder)
        stats = store.stats()
        folders = library.list_folders(user)
        if folder:
            prefix = folder + "/"
            folders = [item for item in folders if item["path"].startswith(prefix)]
        return {
            "notes": totals["notes"],
            "bytes": totals["bytes"],
            "disk": _disk_usage(config.share_root()),
            "folders": len(folders),
            # Revisions only exist through their note. With an empty library
            # any row still on disk belongs to a note deleted outside the
            # application and can never be opened again.
            "versions": history_store.count(user, folder) if totals["notes"] else 0,
            "attachments": False,
            "engine": "fts5" if store.fts else "scan",
            "last_indexed": stats.get("last_indexed") or "",
            "index_notes": stats.get("notes", 0),
        }

    def get_folders(self, request):
        user = request.user
        indexer.maybe_scan(user)
        view = _library_view(user, config.tree_max_entries)
        return {"folders": view["folders"], "count": len(view["folders"])}

    def post_folder_new(self, request):
        body = request.json_body()
        path = (body.get("path") or "").strip()
        if not path:
            raise BadRequest("parameter path is required")
        result = library.create_folder(request.user, path)
        indexer.scan(request.user)
        return result

    def delete_folder(self, request):
        result = library.delete_folder(request.user, request.param("path") or "")
        indexer.scan(request.user)
        return result

    # ------------------------------------------------------------------ import

    def post_notes_import(self, request):
        """Create notes from an uploaded batch of Markdown/text files.

        Options and files arrive interleaved, and the multipart iterator is
        one-pass, so parts are collected first and written afterwards. A per-file
        failure is reported in the result rather than aborting the batch: a
        single odd file must not discard the other thirty.
        """
        user = request.user
        target_dir = ""
        conflict = "rename"
        pending_relative = ""
        files = []

        for part in request.multipart_parts():
            if part.is_file:
                files.append((part, pending_relative))
                pending_relative = ""
                continue
            value = (part.value or "").strip()
            if part.name == "dir":
                target_dir = value
            elif part.name == "conflict":
                conflict = value if value in ("rename", "skip") else "rename"
            elif part.name == "relative":
                pending_relative = value

        if not files:
            raise BadRequest("no files were uploaded")
        if len(files) > config.max_import_files:
            raise BadRequest(
                "at most %d files can be imported at once" % config.max_import_files
            )
        if conflict not in ("rename", "skip"):
            conflict = "rename"

        results = []
        created = skipped = failed = 0
        for part, relative in files:
            original = part.filename or "untitled.md"
            try:
                if part.size > config.max_note_bytes:
                    raise BadRequest("the file is larger than the note size limit")
                with open(part.path, "rb") as handle:
                    raw = handle.read(config.max_note_bytes + 1)
                text, eol, _bom = library.decode_upload(raw)
                hint = relative or original
                segments = library.normalise_rel(
                    (target_dir + "/" if target_dir else "") + hint
                )
                if not segments:
                    raise BadRequest("the file has no name")
                if not segments[-1].lower().endswith(config.note_extensions):
                    if os.path.splitext(segments[-1])[1]:
                        raise BadRequest(
                            "only %s files can be imported"
                            % ", ".join(config.note_extensions)
                        )
                    segments[-1] = segments[-1] + ".md"
                rel = "/".join(segments)
                final = rel
                if conflict == "skip" and os.path.exists(
                    library.resolve_note(user, rel)[0]
                ):
                    skipped += 1
                    results.append({
                        "name": original, "path": rel, "status": "skipped",
                        "message": "a note already exists at that path",
                    })
                    continue
                attempt = 1
                while True:
                    try:
                        note = library.create_note(user, final, text, eol)
                        break
                    except NoteExists:
                        if conflict == "skip":
                            note = None
                            break
                        attempt += 1
                        if attempt > 50:
                            raise
                        stem, ext = os.path.splitext(rel)
                        final = "%s (%d)%s" % (stem, attempt, ext)
                if note is None:
                    skipped += 1
                    results.append({
                        "name": original, "path": rel, "status": "skipped",
                        "message": "a note already exists at that path",
                    })
                    continue
                created += 1
                results.append({
                    "name": original, "path": note["path"], "status": "created",
                    "message": "",
                })
            except MarkNestError as exc:
                failed += 1
                results.append({
                    "name": original, "path": "",
                    "status": "failed", "code": exc.code,
                    "message": exc.message,
                })
            except (OSError, ValueError) as exc:
                failed += 1
                results.append({
                    "name": original, "path": "",
                    "status": "failed", "message": str(exc),
                })

        if created or skipped:
            indexer.scan(request.user)
        return {
            "results": results,
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "total": len(files),
        }

    # ------------------------------------------------------------- attachments

    def post_attachment(self, request):
        user = request.user
        target_dir = request.param("dir") or ""
        upload = None
        for part in request.multipart_parts():
            if part.is_file and (part.name in ("file", "image") or upload is None):
                upload = part
                if part.name == "file":
                    break
        if upload is None:
            raise BadRequest("no image was uploaded")
        return library.save_attachment(
            user, target_dir, upload.filename, upload.path, upload.size
        )

    def get_attachment(self, request):
        attachment = library.read_attachment(user=request.user,
                                             rel=request.param("path") or "")
        filename = attachment["name"]
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "image"
        quoted = urllib.parse.quote(filename)
        return RawResponse(
            attachment["data"],
            attachment["mime"],
            200,
            {
                "Content-Disposition": "inline; filename=\"%s\"; filename*=UTF-8''%s"
                                       % (ascii_name, quoted),
                "X-MarkNest-Path": urllib.parse.quote(attachment["path"]),
            },
        )

    # ---------------------------------------------------------- version history

    def get_versions(self, request):
        user = request.user
        rel = request.param("path") or ""
        if not rel:
            raise BadRequest("parameter path is required")
        library.resolve_note(user, rel, must_exist=True)
        return {
            "path": rel,
            "keep": config.version_keep,
            "versions": history_store.list(user, rel, config.version_keep),
        }

    def get_version_item(self, request):
        user = request.user
        rel = request.param("path") or ""
        version_id = _as_int(request.param("id"), "id", 0, minimum=1)
        if not rel:
            raise BadRequest("parameter path is required")
        return library.read_version(user, rel, version_id)

    def post_version_restore(self, request):
        body = request.json_body()
        rel = (body.get("path") or "").strip()
        version_id = _as_int(body.get("id"), "id", 0, minimum=1)
        if not rel or not version_id:
            raise BadRequest("parameters path and id are required")
        note = library.restore_version(request.user, rel, version_id)
        indexer.scan(request.user)
        return note

    def delete_version(self, request):
        rel = request.param("path") or ""
        version_id = _as_int(request.param("id"), "id", 0, minimum=1)
        if not rel:
            raise BadRequest("parameter path is required")
        library.resolve_note(request.user, rel, must_exist=True)
        return library.delete_version(request.user, rel, version_id)

    def delete_versions(self, request):
        rel = request.param("path") or ""
        if not rel:
            raise BadRequest("parameter path is required")
        library.resolve_note(request.user, rel, must_exist=True)
        return library.delete_versions(request.user, rel)

    # ------------------------------------------------------------------ notes

    def get_tree(self, request):
        user = request.user
        indexer.maybe_scan(user)
        return library.list_tree(user, request.param("path") or "")

    def get_note(self, request):
        return library.read_note(request.user, request.param("path") or "")

    def post_note_save(self, request):
        body = request.json_body()
        path = body.get("path") or ""
        if "content" not in body:
            raise BadRequest("parameter content is required")
        result = library.save_note(
            request.user,
            path,
            body.get("content") or "",
            base_rev=body.get("base_rev"),
            eol=body.get("eol") or "lf",
            force=_as_bool(body.get("force")),
        )
        indexer.scan(request.user)
        return result

    def post_note_new(self, request):
        body = request.json_body()
        path = body.get("path") or ""
        result = library.create_note(
            request.user, path, body.get("content") or "", body.get("eol") or "lf"
        )
        indexer.scan(request.user)
        return result

    def post_note_rename(self, request):
        body = request.json_body()
        source = body.get("from") or ""
        target = body.get("to") or ""
        if not source or not target:
            raise BadRequest("parameters from and to are required")
        result = library.rename_note(
            request.user, source, target, overwrite=_as_bool(body.get("overwrite"))
        )
        indexer.scan(request.user)
        return result

    def delete_note(self, request):
        result = library.delete_note(request.user, request.param("path") or "")
        indexer.scan(request.user)
        return result

    # ----------------------------------------------------------------- search

    def get_search(self, request):
        user = request.user
        query = (request.param("q") or "").strip()
        limit = _as_int(
            request.param("limit"), "limit",
            default=config.search_max_hits, minimum=1,
        )
        limit = min(limit, config.search_max_hits)
        if not query:
            return {"query": "", "hits": [], "count": 0,
                    "engine": "fts5" if store.fts else "scan"}
        indexer.maybe_scan(user)
        hits = store.search(user, query, limit)
        return {
            "query": query,
            "hits": hits,
            "count": len(hits),
            "engine": "fts5" if store.fts else "scan",
        }

    # ------------------------------------------------------------------ index

    def get_index_status(self, request):
        state = indexer.status(request.user)
        state["enabled"] = config.scan_enabled
        state["interval"] = config.scan_interval
        return state

    def post_index_scan(self, request):
        return indexer.scan(request.user, force=True)

    # --------------------------------------------------------------- dispatch

    def dispatch(self, request):
        path = normalize_path(request.raw_path)
        method = request.method

        if method == "OPTIONS":
            return 204, None

        auth_exempt = path in ("/health",)
        verify_request(request, require=config.require_auth and not auth_exempt)

        request.user = ""
        if path not in USER_FREE_PATHS:
            request.user = resolve_identity(request)

        if method == "GET":
            if path == "/health":
                return 200, self.get_health(request)
            if path == "/options":
                return 200, self.get_options(request)
            if path == "/me":
                return 200, self.get_me(request)
            if path == "/library":
                return 200, self.get_library(request)
            if path == "/stats":
                return 200, self.get_stats(request)
            if path == "/folders":
                return 200, self.get_folders(request)
            if path == "/attachments":
                return 200, self.get_attachment(request)
            if path == "/versions":
                return 200, self.get_versions(request)
            if path == "/versions/item":
                return 200, self.get_version_item(request)
            if path == "/tree":
                return 200, self.get_tree(request)
            if path == "/notes":
                return 200, self.get_note(request)
            if path == "/search":
                return 200, self.get_search(request)
            if path == "/index/status":
                return 200, self.get_index_status(request)
            raise NotFound("no such endpoint: %s" % path)

        if method == "POST":
            if path == "/notes/save":
                return 200, self.post_note_save(request)
            if path == "/notes/new":
                return 200, self.post_note_new(request)
            if path == "/notes/rename":
                return 200, self.post_note_rename(request)
            if path == "/notes/import":
                return 200, self.post_notes_import(request)
            if path == "/folders/new":
                return 200, self.post_folder_new(request)
            if path == "/attachments":
                return 200, self.post_attachment(request)
            if path == "/versions/restore":
                return 200, self.post_version_restore(request)
            if path == "/index/scan":
                return 200, self.post_index_scan(request)
            raise NotFound("no such endpoint: %s" % path)

        if method == "DELETE":
            if path == "/notes":
                return 200, self.delete_note(request)
            if path == "/folders":
                return 200, self.delete_folder(request)
            if path == "/versions":
                return 200, self.delete_version(request)
            if path == "/versions/all":
                return 200, self.delete_versions(request)
            raise NotFound("no such endpoint: %s" % path)

        raise MethodNotAllowed("method %s is not allowed on %s" % (method, path))


api = Api()
