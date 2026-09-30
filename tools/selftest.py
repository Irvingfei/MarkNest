#!/usr/bin/env python3
"""Backend self test for MarkNest.

Runs entirely offline against a temporary library, with no TOS device and no
system accounts involved. The HTTP transport is covered by the browser harnesses;
what is pinned here is the logic that is easy to get subtly wrong and impossible
to eyeball - containment, the two independent capability bits, atomic writes,
conflict detection, and the search fallback.

Usage:
    python tools/selftest.py
Exit code 0 means every check passed.
"""

import os
import shutil
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(REPO_ROOT, "usr", "local", "marknest")

# The library root has to be set before lib.config is imported, because the
# configuration is resolved once at module import time.
WORK_DIR = tempfile.mkdtemp(prefix="marknest-selftest-")
SHARE = os.path.join(WORK_DIR, "share")
os.makedirs(SHARE, exist_ok=True)

os.environ["MARKNEST_SHARE_ROOT"] = SHARE
os.environ["MARKNEST_DATA_DIR"] = os.path.join(WORK_DIR, "data")
os.environ["MARKNEST_INDEX_DB"] = os.path.join(WORK_DIR, "data", "index.db")
os.environ["MARKNEST_TMP_DIR"] = os.path.join(WORK_DIR, "data", "tmp")
os.environ["MARKNEST_LOG_DIR"] = os.path.join(WORK_DIR, "logs")
os.environ["MARKNEST_REQUIRE_AUTH"] = "false"
# There are no TOS accounts on a development host, and the identity check's job
# is to reject names that are not accounts - which is asserted separately below
# with the check switched back on.
os.environ["MARKNEST_REQUIRE_SYSTEM_USER"] = "false"
os.environ["MARKNEST_SCAN_ENABLED"] = "false"

sys.path.insert(0, APP_ROOT)

PASSED = 0
FAILED = 0
FAILURES = []


def check(label, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print("  [PASS] %s" % label)
    else:
        FAILED += 1
        FAILURES.append(label)
        print("  [FAIL] %s%s" % (label, "" if not detail else "  -> %s" % (detail,)))
    return bool(condition)


def raises(label, exception, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exception:
        return check(label, True)
    except Exception as exc:  # noqa: BLE001
        return check(label, False, "raised %s: %s" % (type(exc).__name__, exc))
    return check(label, False, "no error raised")


# --------------------------------------------------------------------- imports

from lib import db, index, library  # noqa: E402
from lib.config import config  # noqa: E402
from lib.errors import (  # noqa: E402
    ConflictDetected,
    LibraryNotWritable,
    NameInvalid,
    NoteExists,
    NoteNotFound,
    NoteTooLarge,
    PathInvalid,
)

USER = "alice"
OTHER = "bob"


def test_containment():
    print("\n1. Containment: nothing reaches outside the caller's own library")
    root = library.user_notes_root(USER)
    check("the user library is created on demand", os.path.isdir(root), root)

    raises("'..' is refused", PathInvalid, library.normalise_rel, "../evil.md")
    raises("an absolute path is refused", PathInvalid, library.normalise_rel, "/etc/passwd")
    raises("a backslash path is refused", PathInvalid, library.normalise_rel, "..\\evil.md")
    raises("an embedded separator in a name is refused", NameInvalid,
           library.validate_name, "a/b")
    raises("a dot-prefixed name is refused", NameInvalid, library.validate_name, ".hidden")
    raises("a NUL is refused", PathInvalid, library.normalise_rel, "a\x00b.md")

    check("a normal nested path is accepted",
          library.normalise_rel("notes/projects/roadmap.md")
          == ["notes", "projects", "roadmap.md"])

    # The prefix trap: /tmp/lib-backup must not count as being inside /tmp/lib.
    sibling = root + "-backup"
    os.makedirs(sibling, exist_ok=True)
    try:
        path, _ = library.resolve_note(USER, "../%s/escape.md" % os.path.basename(sibling))
        check("a sibling directory with a shared prefix is refused", False, path)
    except PathInvalid:
        check("a sibling directory with a shared prefix is refused", True)

    # A symlink that leaves the library is judged by where it points.
    outside = os.path.join(WORK_DIR, "outside")
    os.makedirs(outside, exist_ok=True)
    link = os.path.join(root, "escape")
    try:
        os.symlink(outside, link)
        raises("a symlink out of the library is refused", PathInvalid,
               library.resolve_note, USER, "escape/evil.md")
    except (OSError, NotImplementedError):
        print("  [SKIP] symlinks are not available on this host")
    finally:
        try:
            os.unlink(link)
        except OSError:
            pass


def test_cross_user_isolation():
    print("\n2. Cross-user isolation: one library cannot address another")
    library.user_notes_root(USER)
    library.user_notes_root(OTHER)
    library.create_note(USER, "private.md", "alice only\n")
    library.create_note(OTHER, "private.md", "bob only\n")

    alice = library.read_note(USER, "private.md")["content"]
    bob = library.read_note(OTHER, "private.md")["content"]
    check("the same relative path is a different note per user",
          alice == "alice only\n" and bob == "bob only\n", (alice, bob))

    raises("a path climbing into another library is refused", PathInvalid,
           library.read_note, USER, "../%s/notes/private.md" % OTHER)


def test_write_path():
    print("\n3. The write path: atomic, same-directory, and refusing symlinks")
    created = library.create_note(USER, "write/one.md", "# One\n\nbody\n")
    check("a note is created and read back", created["content"].startswith("# One"))
    check("the revision is a content hash", len(created["rev"]) == 64, created["rev"])

    raises("creating over an existing note is refused", NoteExists,
           library.create_note, USER, "write/one.md", "clobber")

    # The staging file must live in the target's own directory. A staging file in
    # the application's tmp directory is on a different filesystem, where the
    # replace is not atomic - and does not raise either.
    seen_dirs = []
    real_mkstemp = tempfile.mkstemp

    def spy(*args, **kwargs):
        seen_dirs.append(kwargs.get("dir"))
        return real_mkstemp(*args, **kwargs)

    tempfile.mkstemp = spy
    try:
        library.save_note(USER, "write/one.md", "# One\n\nedited\n", base_rev=created["rev"])
    finally:
        tempfile.mkstemp = real_mkstemp
    target_dir = os.path.dirname(os.path.join(library.user_notes_root(USER), "write/one.md"))
    check("the staging file is created in the target's own directory",
          seen_dirs and os.path.realpath(seen_dirs[-1]) == os.path.realpath(target_dir),
          seen_dirs)
    check("the tmp directory is a different filesystem target",
          os.path.realpath(config.tmp_dir) != os.path.realpath(target_dir),
          (config.tmp_dir, target_dir))

    # A symlinked write target is refused rather than followed: following it is
    # how a write inside the library ends up outside it.
    outside_file = os.path.join(WORK_DIR, "outside.md")
    with open(outside_file, "w", encoding="utf-8") as handle:
        handle.write("original\n")
    link = os.path.join(library.user_notes_root(USER), "link.md")
    try:
        os.symlink(outside_file, link)
        raises("saving through a symlink is refused", PathInvalid,
               library.save_note, USER, "link.md", "overwritten", None)
        with open(outside_file, encoding="utf-8") as handle:
            check("the symlink target was left untouched", handle.read() == "original\n")
    except (OSError, NotImplementedError):
        print("  [SKIP] symlinks are not available on this host")
    finally:
        try:
            os.unlink(link)
        except OSError:
            pass

    raises("a name without a note extension is refused", NameInvalid,
           library.create_note, USER, "write/notes.bin", "x")

    renamed = library.rename_note(USER, "write/one.md", "write/two.md")
    check("renaming moves the note", renamed["path"].endswith("two.md"), renamed["path"])
    raises("the old path is gone", NoteNotFound, library.read_note, USER, "write/one.md")

    library.delete_note(USER, "write/two.md")
    raises("the deleted note is gone", NoteNotFound, library.read_note, USER, "write/two.md")


def test_capability_probing():
    print("\n4. Read and write are independent bits, measured separately")
    locked = os.path.join(library.user_notes_root(USER), "locked")
    os.makedirs(locked, exist_ok=True)
    library.create_note(USER, "locked/in.md", "content\n")

    readable_before, _ = library.probe_readable(locked)
    writable_before, _ = library.probe_writable(locked)
    check("a normal folder is readable", readable_before is True)
    check("and writable", writable_before is True)

    os.chmod(locked, 0o555)
    try:
        readable_after, _ = library.probe_readable(locked)
        writable_after, reason = library.probe_writable(locked)
        if not hasattr(os, "geteuid"):
            print("  [SKIP] no geteuid on this host; mode bits were not asserted")
        elif os.geteuid() == 0:
            print("  [SKIP] running as root, mode bits are not enforced")
        else:
            check("a read-only folder is still readable", readable_after is True)
            check("but is measured as not writable", writable_after is False, reason)
            raises("and a save there is refused", LibraryNotWritable,
                   library.save_note, USER, "locked/in.md", "x", None)
    finally:
        os.chmod(locked, 0o755)


def test_conflicts():
    print("\n5. Conflicts: a concurrent edit is reported, never overwritten")
    created = library.create_note(USER, "conflict.md", "first\n")
    library.save_note(USER, "conflict.md", "second\n", base_rev=created["rev"])
    check("saving with the current revision succeeds", True)

    # Someone else writes the file - an SMB client, the File Manager, another
    # tab - and the client's revision is now stale. Written as bytes so the
    # newline is exactly what is asserted, whatever the host does with text mode.
    path = os.path.join(library.user_notes_root(USER), "conflict.md")
    with open(path, "wb") as handle:
        handle.write(b"third\n")

    try:
        library.save_note(USER, "conflict.md", "from the stale tab\n", base_rev=created["rev"])
        check("a stale revision is refused", False, "the save went through")
    except ConflictDetected as exc:
        check("a stale revision is refused", True)
        detail = exc.detail or {}
        check("the conflict carries the current content",
              detail.get("current_content") == "third\n", repr(detail.get("current_content")))
        check("and the current revision", bool(detail.get("current_rev")))

    with open(path, "rb") as handle:
        check("the concurrent edit survived", handle.read() == b"third\n")


def test_search():
    print("\n6. Search: both engines agree, and % and _ are literal")
    library.create_note(USER, "s/tax.md", "# Tax\n\nrate is 100% for 2024\n")
    library.create_note(USER, "s/other.md", "# Other\n\nnothing here\n")
    library.create_note(OTHER, "s/tax.md", "# Bob tax\n\nsecret 100% rate\n")
    index.scan(USER, force=True)
    index.scan(OTHER, force=True)

    hits = db.store.search(USER, "100%", 50)
    check("a literal percent sign is matched", any("tax.md" in h["path"] for h in hits), hits)
    check("and it does not reach another user's notes",
          all(OTHER not in h["path"] for h in hits), hits)

    underscore = db.store.search(USER, "100_", 50)
    check("an underscore is literal, not a single-character wildcard",
          not any("tax.md" in h["path"] for h in underscore), underscore)

    english = db.store.search(USER, "nothing", 50)
    check("a plain word is found", any("other.md" in h["path"] for h in english), english)

    check("the engine reports itself", db.store.search(USER, "rate", 5)[0]["engine"]
          in ("fts5", "scan"))

    # The fallback has to produce the same answers, so it is exercised even on a
    # host whose SQLite does have FTS5.
    if db.store.fts:
        saved = db.store.fts
        try:
            db.store.fts = False
            fallback = db.store.search(USER, "100%", 50)
            check("the scan fallback finds the same note",
                  any("tax.md" in h["path"] for h in fallback), fallback)
            check("the fallback reports itself as the engine",
                  all(h["engine"] == "scan" for h in fallback), fallback)
            check("the fallback also treats _ literally",
                  not any("tax.md" in h["path"]
                          for h in db.store.search(USER, "100_", 50)))
        finally:
            db.store.fts = saved
    else:
        print("  [SKIP] FTS5 is unavailable here, only the fallback was exercised")


def test_index_freshness():
    print("\n7. The index follows the files, including changes made behind it")
    library.create_note(USER, "i/one.md", "# One\n\noriginal text\n")
    index.scan(USER, force=True)
    check("a new note is indexed", db.store.count(USER) >= 1)

    # Written by something that is not this process: an SMB client, the File
    # Manager, an editor in another window.
    path = os.path.join(library.user_notes_root(USER), "i/one.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# One\n\nrevised wording\n")
    check("the stale body is what the index still holds",
          db.store.search(USER, "original", 10) != [])

    index.scan(USER, force=True)
    check("a rescan notices the change",
          db.store.search(USER, "revised", 10) != [])
    check("and drops the stale text",
          db.store.search(USER, "original", 10) == [])

    os.unlink(path)
    index.scan(USER, force=True)
    row = db.store.get(USER, "i/one.md")
    check("a note deleted behind the app leaves the index", row is None)

    # Staging files must never be indexed as notes.
    staging = os.path.join(library.user_notes_root(USER), ".marknest-one.md.abc.tmp")
    with open(staging, "w", encoding="utf-8") as handle:
        handle.write("transient\n")
    index.scan(USER, force=True)
    check("a staging file is not indexed",
          db.store.search(USER, "transient", 10) == [])
    os.unlink(staging)


def test_recent():
    print("\n8b. Recent notes come from the index, newest first, own user only")
    library.create_note(USER, "r/old.md", "# Old\n")
    index.scan(USER, force=True)
    # mtime granularity can be coarse; nudge the clock so the order is real.
    time.sleep(0.02)
    library.create_note(USER, "r/new.md", "# New\n")
    index.scan(USER, force=True)
    library.create_note(OTHER, "r/other.md", "# Other\n")
    index.scan(OTHER, force=True)

    rows = db.store.recent(USER, 10)
    paths = [row["path"] for row in rows]
    check("the newest note comes first", paths and paths[0] == "r/new.md", paths)
    check("an older note follows", "r/old.md" in paths, paths)
    check("another user's note never appears", "r/other.md" not in paths, paths)
    check("rows carry what the home screen shows",
          all(set(("path", "title", "mtime_ns", "size")) <= set(row) for row in rows), rows[:1])
    check("the limit is honoured", len(db.store.recent(USER, 1)) == 1)


def test_identity_validation():
    print("\n8. Identity: the cookie is treated as untrusted input")
    from lib import auth

    class FakeRequest:
        def __init__(self, cookie=None):
            self.headers = {"Cookie": "tos_current_username=%s;" % cookie} if cookie else {}
            self.query = {}

        def cookies(self):
            from http.cookies import SimpleCookie

            jar = SimpleCookie()
            if "Cookie" in self.headers:
                jar.load(self.headers["Cookie"])
            return jar

    saved = config.require_system_user

    def resolve(cookie):
        return auth.resolve_identity(FakeRequest(cookie))

    from lib.errors import IdentityRequired

    raises("a missing cookie is refused", IdentityRequired, resolve, None)
    raises("a path separator is refused", IdentityRequired, resolve, "../../etc")
    raises("a dot-only name is refused", IdentityRequired, resolve, "..")
    raises("an over-long name is refused", IdentityRequired, resolve, "a" * 200)

    check("a plausible name is accepted", resolve("alice") == "alice")

    config.require_system_user = True
    try:
        if sys.platform.startswith("win"):
            print("  [SKIP] no pwd module on this host")
        else:
            raises("a name that is not a system account is refused",
                   IdentityRequired, resolve, "definitely-not-a-user-xyzzy")
    finally:
        config.require_system_user = saved


def test_limits():
    print("\n9. Limits")
    saved = config.max_note_bytes
    config.max_note_bytes = 64
    try:
        raises("a note over the limit is refused", NoteTooLarge,
               library.create_note, USER, "big.md", "x" * 200)
    finally:
        config.max_note_bytes = saved

    raises("an empty path is refused", NoteNotFound, library.read_note, USER, "")


def main():
    print("MarkNest backend self test")
    print("work directory: %s" % WORK_DIR)
    print("share root    : %s" % SHARE)
    print("search engine : %s" % ("fts5" if db.store.fts else "scan (fallback)"))

    from lib.logging_setup import setup_logging

    setup_logging("ERROR", config.log_dir, False)

    try:
        test_containment()
        test_cross_user_isolation()
        test_write_path()
        test_capability_probing()
        test_conflicts()
        test_search()
        test_index_freshness()
        test_recent()
        test_identity_validation()
        test_limits()
    finally:
        print("\n" + "-" * 62)
        print("passed: %d   failed: %d" % (PASSED, FAILED))
        if FAILURES:
            for item in FAILURES:
                print("  failed: %s" % item)
        try:
            shutil.rmtree(WORK_DIR, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
