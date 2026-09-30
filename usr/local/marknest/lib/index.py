"""Keeping the index in step with the files.

Change detection is a stat sweep, not a watcher
-----------------------------------------------
The library is an SMB surface: the person editing a note may be doing it from
Windows, from the File Manager, or from this application, and their writes land
through a stack this process never sees. inotify on such a mount has semantics
that vary by client, and one watcher per user would multiply for no benefit. A
sweep that compares ``mtime_ns`` and ``size_bytes`` costs milliseconds over a
note library and is correct regardless of who wrote the file.

The sweep is triggered two ways: on demand when a request needs a fresh answer,
rate-limited by ``scan_min_interval`` so a burst of requests does not turn into
a burst of walks, and periodically by a background thread so a note edited over
SMB shows up in search without anybody having to click anything.

Deletions are inferred from absence. A file removed over SMB leaves no event
here at all, so the only way to notice is that the scan did not see it - which
is why pruning compares against the set the walk actually produced rather than
against anything the process remembers.
"""

import hashlib
import os
import threading
import time

from .config import config
from .db import store as index_store
from .errors import ScanBusy
from .library import user_notes_root
from .logging_setup import get_logger

log = get_logger("index")

_locks_guard = threading.Lock()
_user_locks = {}
_last_scan = {}

_sweeper = None
_stop = threading.Event()


def _lock_for(user):
    with _locks_guard:
        lock = _user_locks.get(user)
        if lock is None:
            lock = threading.Lock()
            _user_locks[user] = lock
        return lock


def _title_of(text, fallback):
    """The first Markdown heading, or the file name."""
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading[:200]
    return fallback


def _is_note(name):
    return name.lower().endswith(config.note_extensions)


def _walk(notes_root, user):
    """Yield ``(rel_path, absolute_path, stat_result)`` for every note file."""
    found = []
    stack = [("", notes_root)]
    while stack:
        rel_dir, abs_dir = stack.pop()
        try:
            with os.scandir(abs_dir) as entries:
                for entry in entries:
                    name = entry.name
                    if name.startswith("."):
                        # Staging files and platform bookkeeping, never content.
                        continue
                    rel = name if not rel_dir else rel_dir + "/" + name
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append((rel, entry.path))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if not _is_note(name):
                        continue
                    found.append((rel, entry.path, info))
        except PermissionError:
            log.info("skipping an unreadable folder in %s: %s", user, abs_dir)
        except OSError as exc:
            log.info("cannot walk %s: %s", abs_dir, exc)
    return found


def scan(user, force=False):
    """Bring the index for one user up to date. Returns a summary."""
    lock = _lock_for(user)
    if not lock.acquire(blocking=force):
        raise ScanBusy("an index scan is already running for this user")
    started = time.time()
    try:
        notes_root = user_notes_root(user)
        known = index_store.known(user)
        seen = set()
        added = updated = unchanged = 0

        for rel, abs_path, info in _walk(notes_root, user):
            seen.add(rel)
            previous = known.get(rel)
            if previous and previous[0] == info.st_mtime_ns and previous[1] == info.st_size:
                unchanged += 1
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError as exc:
                log.info("cannot read %s: %s", abs_path, exc)
                continue
            digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            index_store.upsert(
                user,
                rel,
                _title_of(text, os.path.basename(rel)),
                info.st_size,
                info.st_mtime_ns,
                digest,
                text,
            )
            if previous:
                updated += 1
            else:
                added += 1

        removed = index_store.delete_paths(user, seen)
        _last_scan[user] = time.time()
        summary = {
            "added": added,
            "updated": updated,
            "removed": removed,
            "unchanged": unchanged,
            "notes": len(seen),
            "duration_ms": int((time.time() - started) * 1000),
        }
        if added or updated or removed:
            log.info(
                "index %s: +%d ~%d -%d (%d unchanged, %d ms)",
                user, added, updated, removed, unchanged, summary["duration_ms"],
            )
        return summary
    finally:
        lock.release()


def maybe_scan(user):
    """Scan if the last one is older than the minimum interval.

    Returns the summary when a scan ran, or ``None`` when the recent answer is
    still considered fresh. A busy scan is not an error here: it means somebody
    else is already bringing the index up to date, which is the desired outcome.
    """
    last = _last_scan.get(user, 0.0)
    if time.time() - last < config.scan_min_interval:
        return None
    try:
        return scan(user)
    except ScanBusy:
        return None


def status(user):
    last = _last_scan.get(user, 0.0)
    return {
        "notes": index_store.count(user),
        "last_scan": last,
        "last_scan_ago": (time.time() - last) if last else None,
        "engine": "fts5" if index_store.fts else "scan",
    }


class Sweeper(threading.Thread):
    """Periodic background sweep over the users that exist."""

    def __init__(self):
        super().__init__(name="marknest-index", daemon=True)

    def run(self):
        log.info("index sweeper started (every %.0fs)", config.scan_interval)
        while not _stop.wait(config.scan_interval):
            try:
                self.sweep_once()
            except Exception as exc:  # noqa: BLE001 - the sweep must never die
                log.warning("index sweep failed: %s", exc)
        log.info("index sweeper stopped")

    def sweep_once(self):
        users_root = config.users_root()
        if not users_root or not os.path.isdir(users_root):
            return
        try:
            with os.scandir(users_root) as entries:
                names = [e.name for e in entries
                         if not e.name.startswith(".") and e.is_dir()]
        except OSError as exc:
            log.info("cannot enumerate library users: %s", exc)
            return
        for name in names:
            if _stop.is_set():
                return
            try:
                scan(name)
            except ScanBusy:
                continue
            except Exception as exc:  # noqa: BLE001 - one bad user must not stop the rest
                log.info("sweep skipped %s: %s", name, exc)


def start_sweeper():
    """Start the background sweep. Never allowed to block startup."""
    global _sweeper
    if not config.scan_enabled:
        log.info("index sweeper disabled by configuration")
        return None
    if _sweeper is not None and _sweeper.is_alive():
        return _sweeper
    _stop.clear()
    _sweeper = Sweeper()
    _sweeper.start()
    return _sweeper


def stop_sweeper():
    _stop.set()
    sweeper = _sweeper
    if sweeper is not None and sweeper.is_alive():
        sweeper.join(timeout=2.0)
