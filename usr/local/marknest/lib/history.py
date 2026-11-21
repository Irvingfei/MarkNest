"""Version history for notes.

Every save first records the content that is about to be replaced. That is the
whole feature: the files on disk remain the single source of truth, and this
database only remembers what earlier revisions looked like so that a save can be
inspected or rolled back from inside the application.

Two deliberate properties:

* History lives in its own database under the runtime data directory, not in
  the search index. The index is a cache that may be deleted and rebuilt at any
  time, and coupling the two would make "rebuild search" quietly destroy
  history.
* A revision that is byte-identical to the newest recorded revision is not
  stored again. Opening and saving without editing is common, and each of those
  saves would otherwise add a row that contains nothing new.
"""

import datetime
import hashlib
import os
import sqlite3
import threading

from .config import config
from .errors import VersionNotFound
from .logging_setup import get_logger

log = get_logger("history")

SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user        TEXT    NOT NULL,
    rel_path    TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    created_ns  INTEGER NOT NULL,
    size_bytes  INTEGER NOT NULL,
    rev         TEXT    NOT NULL DEFAULT '',
    sha256      TEXT    NOT NULL,
    content     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_versions_note
    ON versions(user, rel_path, id DESC);
"""


class HistoryStore:
    """Thread-safe store for note revisions."""

    def __init__(self, db_path=None):
        self.db_path = db_path or config.history_db
        self._local = threading.local()
        self._write_lock = threading.Lock()
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ plumbing

    def _connect(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _init_schema(self):
        try:
            with self._connect() as conn:
                conn.executescript(SCHEMA)
        except sqlite3.Error as exc:
            # History is useful but must never be the reason a note cannot be
            # saved or opened. The caller treats a failed record as a warning.
            log.error("cannot prepare the history schema: %s", exc)

    # -------------------------------------------------------------------- writes

    def record(self, user, rel_path, content, rev=""):
        """Store ``content`` as a revision, returning its id or ``None``."""
        if not user or not rel_path:
            return None
        text = content or ""
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        now = datetime.datetime.now()
        with self._write_lock:
            conn = self._connect()
            try:
                latest = conn.execute(
                    "SELECT id, sha256 FROM versions WHERE user=? AND rel_path=? "
                    "ORDER BY id DESC LIMIT 1",
                    (user, rel_path),
                ).fetchone()
                if latest and latest["sha256"] == digest:
                    return int(latest["id"])
                with conn:
                    cur = conn.execute(
                        "INSERT INTO versions "
                        "(user, rel_path, created_at, created_ns, size_bytes, rev, "
                        " sha256, content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            user,
                            rel_path,
                            now.strftime("%Y-%m-%d %H:%M:%S"),
                            int(now.timestamp() * 1_000_000_000),
                            len(text.encode("utf-8", "replace")),
                            rev or "",
                            digest,
                            text,
                        ),
                    )
                    version_id = int(cur.lastrowid)
                    self._prune(conn, user, rel_path)
                    return version_id
            except sqlite3.Error as exc:
                log.warning("cannot record a version of %s/%s: %s", user, rel_path, exc)
                return None

    def _prune(self, conn, user, rel_path):
        keep = max(1, int(config.version_keep))
        try:
            conn.execute(
                "DELETE FROM versions WHERE user=? AND rel_path=? AND id NOT IN ("
                "  SELECT id FROM versions WHERE user=? AND rel_path=? "
                "  ORDER BY id DESC LIMIT ?)",
                (user, rel_path, user, rel_path, keep),
            )
        except sqlite3.Error as exc:
            log.info("cannot prune history for %s/%s: %s", user, rel_path, exc)

    def rename_path(self, user, source, target):
        """Move a note's history with the note so a rename keeps its revisions."""
        with self._write_lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "UPDATE versions SET rel_path=? WHERE user=? AND rel_path=?",
                        (target, user, source),
                    )
            except sqlite3.Error as exc:
                log.info("cannot move history %s -> %s: %s", source, target, exc)

    # --------------------------------------------------------------------- reads

    def list(self, user, rel_path, limit=50):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, created_at, created_ns, size_bytes, rev "
                "FROM versions WHERE user=? AND rel_path=? ORDER BY id DESC LIMIT ?",
                (user, rel_path, int(limit)),
            ).fetchall()
        except sqlite3.Error as exc:
            log.warning("cannot list history for %s/%s: %s", user, rel_path, exc)
            return []
        return [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "created_ns": int(row["created_ns"]),
                "size": int(row["size_bytes"]),
                "rev": row["rev"] or "",
            }
            for row in rows
        ]

    def get(self, user, rel_path, version_id):
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, created_at, size_bytes, rev, content FROM versions "
                "WHERE user=? AND rel_path=? AND id=?",
                (user, rel_path, int(version_id)),
            ).fetchone()
        except sqlite3.Error as exc:
            log.warning("cannot read version %s of %s/%s: %s",
                        version_id, user, rel_path, exc)
            return None
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "size": int(row["size_bytes"]),
            "rev": row["rev"] or "",
            "content": row["content"] or "",
        }

    def count(self, user=None):
        conn = self._connect()
        try:
            if user:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM versions WHERE user=?", (user,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM versions").fetchone()
        except sqlite3.Error:
            return 0
        return int(row["n"]) if row else 0

    def require(self, user, rel_path, version_id):
        version = self.get(user, rel_path, version_id)
        if version is None:
            raise VersionNotFound("that version does not exist")
        return version


history_store = HistoryStore()
