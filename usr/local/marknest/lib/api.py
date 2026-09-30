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

import os
import re

from . import __version__
from . import index as indexer
from . import library
from .auth import resolve_identity, verify_request
from .config import config
from .db import store
from .errors import BadRequest, MethodNotAllowed, NotFound
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
                "attachments": False,
                "wiki_links": False,
                "backlinks": False,
            },
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

    # ----------------------------------------------------------------- recent

    def get_recent(self, request):
        """The notes the home screen lists, most recently modified first.

        Deliberately not paginated: this is a starting point, not a browser.
        The ceiling exists so a client cannot ask for the whole library and
        make the socket proxy carry it.
        """
        limit = _as_int(request.param("limit"), "limit", default=12, minimum=1)
        limit = min(limit, 50)
        indexer.maybe_scan(request.user)
        rows = store.recent(request.user, limit)
        return {"recent": rows, "count": len(rows), "limit": limit}

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
            if path == "/tree":
                return 200, self.get_tree(request)
            if path == "/notes":
                return 200, self.get_note(request)
            if path == "/search":
                return 200, self.get_search(request)
            if path == "/recent":
                return 200, self.get_recent(request)
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
            if path == "/index/scan":
                return 200, self.post_index_scan(request)
            raise NotFound("no such endpoint: %s" % path)

        if method == "DELETE":
            if path == "/notes":
                return 200, self.delete_note(request)
            raise NotFound("no such endpoint: %s" % path)

        raise MethodNotAllowed("method %s is not allowed on %s" % (method, path))


api = Api()
