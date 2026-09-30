"""SQLite persistence for the note index.

The index is a derived cache, never the source of truth: every row can be
rebuilt from the files, and deleting the database costs one rescan and nothing
else. It lives in the application runtime data directory, deliberately outside
the shared folder, so the user's File Manager and SMB listings show their notes
and nothing else.

The full-text table is a plain FTS5 table whose ``rowid`` is the ``notes.id``,
which is why there is no mapping table to keep in step. FTS5 is a compile-time
option of SQLite, so its presence is detected once at startup and the search
implementation falls back to a scan when it is missing - see :meth:`search`.
"""

import os
import re
import sqlite3
import threading

from .config import config
from .errors import IndexUnavailable
from .logging_setup import get_logger

log = get_logger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user         TEXT    NOT NULL,
    rel_path     TEXT    NOT NULL,
    title        TEXT    NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    mtime_ns     INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT    NOT NULL DEFAULT '',
    body         TEXT    NOT NULL DEFAULT '',
    indexed_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(user, rel_path)
);

CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user, rel_path);
CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(user, title);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title,
    body,
    tokenize='unicode61 remove_diacritics 2'
);
"""

#: FTS5 query syntax characters. A user typing "foo*" or "a AND b" means those
#: literally, so they are neutralised before the string reaches MATCH.
_FTS_SPECIAL = re.compile(r'["*():^\-]')


def fts5_available(path=None):
    """Detect FTS5 support by trying it, not by reading a version number."""
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE __probe USING fts5(x)")
            conn.execute("INSERT INTO __probe VALUES ('a b')")
            conn.execute("SELECT * FROM __probe WHERE __probe MATCH 'b'").fetchall()
            return True
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.info("FTS5 is not available (%s); search will scan", exc)
        return False


class IndexStore:
    """Thread-safe data access object for the note index."""

    def __init__(self, db_path=None):
        self.db_path = db_path or config.index_db
        self._local = threading.local()
        self._write_lock = threading.Lock()
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.fts = fts5_available() and not config.force_search_fallback
        if config.force_search_fallback:
            log.info("search fallback forced by configuration")
        self._init_schema()

    # ------------------------------------------------------------------ plumbing

    def _connect(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def connection(self):
        """The calling thread's connection, for callers that need it directly."""
        return self._connect()

    def _init_schema(self):
        try:
            with self._connect() as conn:
                conn.executescript(SCHEMA)
                if self.fts:
                    conn.executescript(FTS_SCHEMA)
        except sqlite3.Error as exc:
            log.error("cannot prepare the index schema: %s", exc)
            raise IndexUnavailable("the search index could not be prepared")

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -------------------------------------------------------------------- writes

    def upsert(self, user, rel_path, title, size_bytes, mtime_ns, content_hash, body):
        """Insert or refresh one note and its full-text row."""
        with self._write_lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO notes (user, rel_path, title, size_bytes, "
                        "mtime_ns, content_hash, body, indexed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime')) "
                        "ON CONFLICT(user, rel_path) DO UPDATE SET "
                        "title=excluded.title, size_bytes=excluded.size_bytes, "
                        "mtime_ns=excluded.mtime_ns, "
                        "content_hash=excluded.content_hash, body=excluded.body, "
                        "indexed_at=excluded.indexed_at",
                        (user, rel_path, title or "", int(size_bytes), int(mtime_ns),
                         content_hash or "", body or ""),
                    )
                    note_id = cur.lastrowid
                    if not note_id:
                        row = conn.execute(
                            "SELECT id FROM notes WHERE user=? AND rel_path=?",
                            (user, rel_path),
                        ).fetchone()
                        note_id = row["id"] if row else None
                    if self.fts and note_id:
                        # The FTS rowid is the note id, so there is no mapping
                        # table to drift out of step.
                        conn.execute("DELETE FROM notes_fts WHERE rowid=?", (note_id,))
                        conn.execute(
                            "INSERT INTO notes_fts (rowid, title, body) VALUES (?, ?, ?)",
                            (note_id, title or "", body or ""),
                        )
                    return note_id
            except sqlite3.Error as exc:
                log.warning("index write failed for %s/%s: %s", user, rel_path, exc)
                raise IndexUnavailable("the search index could not be written")

    def delete_paths(self, user, keep_paths):
        """Drop rows for notes that no longer exist on disk.

        ``keep_paths`` is the set the scan actually saw. Deleting by absence
        rather than by tracking removals means a file deleted over SMB - which
        this process never observes - still leaves the index.
        """
        with self._write_lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, rel_path FROM notes WHERE user=?", (user,)
                ).fetchall()
                stale = [r["id"] for r in rows if r["rel_path"] not in keep_paths]
                if not stale:
                    return 0
                with conn:
                    for note_id in stale:
                        conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
                        if self.fts:
                            conn.execute("DELETE FROM notes_fts WHERE rowid=?", (note_id,))
                return len(stale)
            except sqlite3.Error as exc:
                log.warning("index prune failed for %s: %s", user, exc)
                raise IndexUnavailable("the search index could not be updated")

    def forget_user(self, user):
        with self._write_lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id FROM notes WHERE user=?", (user,)
                ).fetchall()
                with conn:
                    for row in rows:
                        conn.execute("DELETE FROM notes WHERE id=?", (row["id"],))
                        if self.fts:
                            conn.execute("DELETE FROM notes_fts WHERE rowid=?", (row["id"],))
                return len(rows)
            except sqlite3.Error as exc:
                log.warning("cannot forget %s: %s", user, exc)
                raise IndexUnavailable("the search index could not be cleared")

    # --------------------------------------------------------------------- reads

    def known(self, user):
        """``{rel_path: (mtime_ns, size_bytes)}`` for the cheap change test."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT rel_path, mtime_ns, size_bytes FROM notes WHERE user=?", (user,)
            ).fetchall()
        except sqlite3.Error as exc:
            log.warning("cannot read the index for %s: %s", user, exc)
            raise IndexUnavailable("the search index could not be read")
        return {r["rel_path"]: (r["mtime_ns"], r["size_bytes"]) for r in rows}

    def count(self, user=None):
        conn = self._connect()
        try:
            if user:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notes WHERE user=?", (user,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()
        except sqlite3.Error:
            return 0
        return int(row["n"]) if row else 0

    def get(self, user, rel_path):
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT * FROM notes WHERE user=? AND rel_path=?", (user, rel_path)
            ).fetchone()
        except sqlite3.Error:
            return None

    def recent(self, user, limit=12):
        """The user's notes, most recently modified first.

        There is no "recently opened" bookkeeping and deliberately so: this is
        the same table the search index maintains, ordered by the file's own
        modification time. That means an edit made over SMB shows up here
        immediately after the next scan, which is what a person means by
        "recent" anyway - and it costs no state to keep in step.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT rel_path, title, mtime_ns, size_bytes FROM notes "
                "WHERE user = ? ORDER BY mtime_ns DESC, rel_path LIMIT ?",
                (user, int(limit)),
            ).fetchall()
        except sqlite3.Error as exc:
            log.warning("cannot list recent notes for %s: %s", user, exc)
            raise IndexUnavailable("the search index could not be read")
        return [
            {
                "path": row["rel_path"],
                "title": row["title"] or row["rel_path"],
                "mtime_ns": int(row["mtime_ns"]),
                "size": int(row["size_bytes"]),
            }
            for row in rows
        ]

    # -------------------------------------------------------------------- search

    def search(self, user, query, limit=50):
        """Return hits for one user, newest engine first.

        Every path is constrained by ``user``; there is no query shape that
        reaches another person's notes.
        """
        terms = [t for t in re.split(r"\s+", (query or "").strip()) if t]
        if not terms:
            return []
        if self.fts:
            hits = self._search_fts(user, terms, limit)
            if hits is not None:
                return hits
        return self._search_scan(user, terms, limit)

    def _search_fts(self, user, terms, limit):
        # Neutralise FTS5 operators so a literal "a-b" or "c*d" is searched for
        # rather than parsed as syntax. The last term gets a prefix match, which
        # is what makes search-as-you-type feel responsive.
        parts = []
        for index, term in enumerate(terms):
            cleaned = _FTS_SPECIAL.sub(" ", term).strip()
            if not cleaned:
                continue
            suffix = "*" if index == len(terms) - 1 else ""
            parts.append('"%s"%s' % (cleaned.replace('"', ""), suffix))
        if not parts:
            return []
        match = " AND ".join(parts)

        sql = (
            "SELECT n.rel_path AS rel_path, n.title AS title, n.body AS body, "
            "       bm25(notes_fts, 4.0, 1.0) AS score, "
            "       snippet(notes_fts, 1, '', '', '…', 14) AS snippet "
            "FROM notes_fts JOIN notes n ON n.id = notes_fts.rowid "
            "WHERE notes_fts MATCH ? AND n.user = ? "
            "ORDER BY score, n.rel_path LIMIT ?"
        )
        try:
            conn = self._connect()
            # Over-fetch, because the literal filter below can drop candidates.
            rows = conn.execute(sql, (match, user, int(limit) * 4)).fetchall()
        except sqlite3.Error as exc:
            # A malformed MATCH expression is a user typing punctuation, not a
            # broken index, so fall back to the scan rather than reporting an
            # error for what is really "no results in that syntax".
            log.info("FTS query rejected (%s); scanning instead", exc)
            return None

        # The tokenizer strips punctuation, so "100_" reduces to the token 100
        # and would otherwise match a note containing "100%". Token-based search
        # is what makes full-text search fast, and that behaviour is worth
        # keeping - but reporting a note that does not contain what the person
        # typed is not. Candidates are therefore checked against the literal
        # text before they are returned, which costs one comparison per
        # candidate and makes the two engines agree on punctuation.
        needles = [t.casefold() for t in terms]
        hits = []
        for row in rows:
            haystack = ((row["title"] or "") + "\n" + (row["body"] or "")).casefold()
            if not all(needle in haystack for needle in needles):
                continue
            hits.append(
                {
                    "path": row["rel_path"],
                    "title": row["title"] or row["rel_path"],
                    "score": float(row["score"] or 0.0),
                    "snippet": row["snippet"] or "",
                    "engine": "fts5",
                }
            )
            if len(hits) >= limit:
                break
        return hits

    def _search_scan(self, user, terms, limit):
        """Substring scan, used when FTS5 is absent.

        ``%`` and ``_`` are ordinary characters here, not wildcards - which is
        the opposite of what a ``LIKE`` based scan would do, and the reason this
        is implemented in Python rather than as SQL ``LIKE``.
        """
        needles = [t.casefold() for t in terms]
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT rel_path, title, body FROM notes WHERE user=? ORDER BY rel_path",
                (user,),
            ).fetchall()
        except sqlite3.Error as exc:
            log.warning("scan search failed for %s: %s", user, exc)
            raise IndexUnavailable("the search index could not be read")

        hits = []
        for row in rows:
            body = row["body"] or ""
            title = row["title"] or ""
            haystack = (title + "\n" + body).casefold()
            if not all(needle in haystack for needle in needles):
                continue
            hits.append(
                {
                    "path": row["rel_path"],
                    "title": title or row["rel_path"],
                    "score": 0.0,
                    "snippet": _scan_snippet(body, needles),
                    "engine": "scan",
                }
            )
            if len(hits) >= limit:
                break
        return hits

    def stats(self):
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS notes, COUNT(DISTINCT user) AS users FROM notes"
            ).fetchone()
            last = conn.execute("SELECT MAX(indexed_at) AS at FROM notes").fetchone()
        except sqlite3.Error:
            return {"notes": 0, "users": 0, "last_indexed": ""}
        return {
            "notes": int(row["notes"]) if row else 0,
            "users": int(row["users"]) if row else 0,
            "last_indexed": (last["at"] if last and last["at"] else ""),
        }


def _scan_snippet(body, needles, width=80):
    """A window of the body around the first match, with nothing marked up.

    The caller escapes before inserting any highlight markup; this returns plain
    text so the escaping happens exactly once, in one place.
    """
    if not body:
        return ""
    folded = body.casefold()
    position = -1
    for needle in needles:
        found = folded.find(needle)
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        return body[: width * 2].strip()
    start = max(0, position - width // 2)
    end = min(len(body), position + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return (prefix + body[start:end].strip() + suffix)


store = IndexStore()
