"""Configuration loading.

Runtime options are read from ``marknest.env`` (declared in the systemd unit
through ``EnvironmentFile=``) with environment variables taking precedence.
"""

import glob
import os

APP_ID = os.environ.get("MARKNEST_APP_ID", "marknest")

_APP_ROOT = os.environ.get("MARKNEST_ROOT") or "/usr/local/marknest"

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if not os.path.isdir(_APP_ROOT):
    # Development / self-test mode: resolve relative to the repository checkout.
    _APP_ROOT = os.path.dirname(_LIB_DIR)

_ENV_FILE = os.path.join(_APP_ROOT, "marknest.env")


def _load_env_file(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


_FILE_ENV = _load_env_file(_ENV_FILE)


class Config:
    """Resolved runtime configuration."""

    def __init__(self):
        env = lambda key, default="": os.environ.get(key) or _FILE_ENV.get(key, default)

        self.app_id = env("MARKNEST_APP_ID", APP_ID)
        self.app_root = _APP_ROOT
        self.lib_dir = _LIB_DIR

        prefix = env("MARKNEST_PROXY_PREFIX", "/%s/" % self.app_id)
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        if not prefix.endswith("/"):
            prefix += "/"
        self.proxy_prefix = prefix

        self.socket_path = env("MARKNEST_SOCKET", "/var/api/%s.sock" % self.app_id)
        self.socket_mode = int(env("MARKNEST_SOCKET_MODE", "660"), 8)

        self.data_dir = env("MARKNEST_DATA_DIR", os.path.join(self.app_root, "data"))
        # The search index lives beside the application, never inside the shared
        # folder: the user's File Manager and SMB listings are for their notes,
        # and a SQLite file with its -wal and -shm siblings among them would be
        # both baffling and easy to corrupt.
        self.index_db = env(
            "MARKNEST_INDEX_DB", os.path.join(self.data_dir, "index.db")
        )
        self.tmp_dir = env("MARKNEST_TMP_DIR", os.path.join(self.data_dir, "tmp"))
        self.log_dir = env("MARKNEST_LOG_DIR", os.path.join(self.app_root, "logs"))

        self.log_level = env("MARKNEST_LOG_LEVEL", "INFO")
        self.log_to_file = _as_bool(env("MARKNEST_LOG_TO_FILE", "false"))

        self.max_concurrency = int(env("MARKNEST_MAX_CONCURRENCY", "8"))
        self.idle_timeout = float(env("MARKNEST_IDLE_TIMEOUT", "30"))

        # ------------------------------------------------------------------ library

        # The note library is a shared folder this package creates for itself in
        # postinst with the platform's ter_share_add. ``share_root`` names it
        # outright - the self-test uses this, and so would any deployment that
        # had to fall back to an operator-granted folder - while the default is
        # to discover it, because the platform tool decides which volume it
        # lands on and that can differ between machines.
        self.share_name = env("MARKNEST_SHARE_NAME", "%s-data" % self.app_id)
        self.volume_glob = env("MARKNEST_VOLUME_GLOB", "/Volume*")
        self.share_root_override = env("MARKNEST_SHARE_ROOT", "")

        # The subdirectory inside the library that holds each user's own notes.
        self.users_dirname = env("MARKNEST_USERS_DIR", "users")
        self.notes_dirname = env("MARKNEST_NOTES_DIR", "notes")

        # What the editor will open. One list, advertised through /options and
        # enforced on every write, so the file tree can never offer something the
        # server would refuse or hide something it would accept.
        self.note_extensions = tuple(
            ext if ext.startswith(".") else "." + ext
            for ext in (
                item.strip().lower()
                for item in env(
                    "MARKNEST_NOTE_EXTENSIONS", ".md,.markdown,.mdown,.txt"
                ).split(",")
            )
            if ext
        )

        # 8 MiB is far past any hand-written note, so it only ever catches paste
        # accidents and runaway generators.
        self.max_note_bytes = int(env("MARKNEST_MAX_NOTE_MB", "8")) * 1024 * 1024
        # Above this, a save is compared by mtime and size rather than by a
        # content hash. Hashing is what makes conflict detection reliable; this
        # is only here so a pathological file cannot make saving slow.
        self.hash_max_bytes = int(env("MARKNEST_HASH_MAX_MB", "8")) * 1024 * 1024
        self.max_attachment_bytes = int(env("MARKNEST_MAX_ATTACHMENT_MB", "64")) * 1024 * 1024

        # Listing a folder with more entries than this is truncated rather than
        # streamed: the browser cannot present a hundred thousand rows usefully,
        # and the JSON has to stay small enough for the Unix socket proxy.
        self.tree_max_entries = int(env("MARKNEST_TREE_MAX_ENTRIES", "2000"))
        self.search_max_hits = int(env("MARKNEST_SEARCH_MAX_HITS", "200"))

        # ---------------------------------------------------------- index freshness

        # No inotify: the library is an SMB surface whose change-notification
        # semantics vary by client, and one watcher per user would multiply for
        # no benefit. A stat sweep over a note library costs milliseconds.
        self.scan_interval = float(env("MARKNEST_SCAN_INTERVAL", "30"))
        self.scan_min_interval = float(env("MARKNEST_SCAN_MIN_INTERVAL", "2"))
        self.scan_enabled = _as_bool(env("MARKNEST_SCAN_ENABLED", "true"))

        # Forces the non-FTS5 search path so the self-test can exercise it on a
        # machine whose SQLite does have FTS5 compiled in.
        self.force_search_fallback = _as_bool(env("MARKNEST_FORCE_SEARCH_FALLBACK", "false"))

        # -------------------------------------------------------------------- auth

        self.require_auth = _as_bool(env("MARKNEST_REQUIRE_AUTH", "true"))
        self.env_verify_url = env("MARKNEST_VERIFY_URL", "")

        # Which cookie carries the requesting user. TOS's own backend services
        # read this name, but it does NOT survive the platform's proxy on the
        # way to an embedded application, so the WebUI also sends the same value
        # in a header of its own and that is what is normally consulted. The
        # cookie is kept as a fallback because it is the platform's convention
        # and costs nothing to read.
        self.user_cookie = env("MARKNEST_USER_COOKIE", "tos_current_username")
        self.user_header = env("MARKNEST_USER_HEADER", "X-MarkNest-User")

        # Require the name to resolve to a real system account. Off only for the
        # self-test harness, which runs on a host with no TOS accounts at all.
        self.require_system_user = _as_bool(env("MARKNEST_REQUIRE_SYSTEM_USER", "true"))

    # -------------------------------------------------------------------- paths

    def share_root(self):
        """The folder the notes live in, or ``""`` when it cannot be found.

        Re-resolved on every call rather than cached at import: a volume can be
        mounted after the service starts, and a cached empty answer would keep
        the application reporting an unavailable library for its whole lifetime.
        The check is a ``isfile``-free directory test on at most a handful of
        paths, so the cost is irrelevant next to being wrong.
        """
        if self.share_root_override:
            return self.share_root_override
        for volume in sorted(glob.glob(self.volume_glob)):
            candidate = os.path.join(volume, self.share_name)
            if os.path.isdir(candidate):
                return candidate
        return ""

    def users_root(self):
        root = self.share_root()
        return os.path.join(root, self.users_dirname) if root else ""

    def user_root(self, user):
        users = self.users_root()
        return os.path.join(users, user) if users and user else ""

    def user_notes_root(self, user):
        base = self.user_root(user)
        return os.path.join(base, self.notes_dirname) if base else ""

    def ensure_directories(self):
        for path in (self.data_dir, self.tmp_dir, os.path.dirname(self.index_db)):
            if path:
                os.makedirs(path, exist_ok=True)

    def describe(self):
        return {
            "app_id": self.app_id,
            "app_root": self.app_root,
            "proxy_prefix": self.proxy_prefix,
            "socket_path": self.socket_path,
            "index_db": self.index_db,
            "share_name": self.share_name,
            "share_root": self.share_root() or "(not found)",
            "log_level": self.log_level,
        }


def _as_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


config = Config()
