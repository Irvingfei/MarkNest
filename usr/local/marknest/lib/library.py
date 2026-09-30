"""The note library: a user's own .md files inside a shared folder.

Why the files are the storage
-----------------------------
Notes are ordinary files in an ordinary TOS shared folder, and nothing here
keeps a second copy anywhere. That is the point of the application: the operator
sees the notes in the File Manager, reaches them over SMB, and gets version
history from the volume snapshots without this code implementing any of it. The
SQLite index is a derived cache that can be deleted and rebuilt at any time.

Read and write are measured, never inferred
-------------------------------------------
TOS 7 gates shared folders with an SPC managed ACL kept in the ``system.tm_acl``
extended attribute. The POSIX mode bits therefore no longer describe reality, so
every "can this be read" and "can this be written" answer below comes from
actually attempting the operation. The two are also probed separately: they are
independent bits, and a folder that reads perfectly well can still refuse a save.

Writing has two traps this module exists to avoid
-------------------------------------------------
The staging file is created in the *target's own directory*, never in the
application's tmp directory. ``/usr/local/marknest/data`` is a different
filesystem from ``/Volume*``, and a rename across filesystems is not atomic -
and worse, it does not fail loudly: ``mv`` and friends fall back to copy, so a
half-written note is possible where a raised error would at least have been
visible.

A write target that is a symbolic link is refused outright rather than followed.
Following it is how a write inside the library ends up outside it.
"""

import errno
import hashlib
import os
import stat
import tempfile
import unicodedata

from .config import config
from .errors import (
    LibraryNotWritable,
    LibraryUnavailable,
    NameInvalid,
    NoteExists,
    NoteNotFound,
    NoteTooLarge,
    PathDenied,
    PathInvalid,
)
from .logging_setup import get_logger

log = get_logger("library")

#: Characters that cannot appear in a name, on any platform the volume may be
#: shared with. The backslash is included even though the filesystem allows it,
#: because a name containing one is a name some SMB client will mangle.
_BAD_NAME_CHARS = frozenset("/\\\x00")

#: The staging prefix for atomic writes. The leading dot keeps a staging file
#: out of the tree listing and out of the indexer while it exists.
_TMP_PREFIX = ".marknest-"

_BOM = "﻿"


# --------------------------------------------------------------- capability


def probe_readable(path):
    """Return ``(readable, reason)`` by actually opening the directory.

    The single-entry consumption is deliberate rather than decorative:
    ``os.scandir`` is lazy, so a permission failure surfaces on the first
    ``next()`` and not when the context manager exits. An empty-looking loop
    that never iterates would report a denied folder as readable.
    """
    try:
        with os.scandir(path) as entries:
            for _ in entries:
                break
    except PermissionError:
        return False, "denied"
    except FileNotFoundError:
        return False, "missing"
    except OSError as exc:
        log.info("cannot probe %s: %s", path, exc)
        return False, "unreadable"
    return True, ""


def probe_writable(path):
    """Return ``(writable, reason)`` by actually creating a file in ``path``.

    ``path`` must be a *directory*, because that is what the ACL gates: creating
    an entry depends on the parent's bit, not the target's. Probing an existing
    file's own writability would answer a different question and could easily
    answer it the other way round.
    """
    handle_fd = None
    tmp = None
    try:
        handle_fd, tmp = tempfile.mkstemp(prefix=_TMP_PREFIX, dir=path)
        os.write(handle_fd, b"0")
        return True, ""
    except PermissionError:
        return False, "denied"
    except FileNotFoundError:
        return False, "missing"
    except OSError as exc:
        # EROFS and EDQUOT land here, and both mean "you cannot save here" just
        # as surely as EACCES does.
        log.info("cannot write in %s: %s", path, exc)
        return False, "unwritable"
    finally:
        if handle_fd is not None:
            try:
                os.close(handle_fd)
            except OSError:
                pass
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ------------------------------------------------------------------ paths


def validate_name(name):
    """Normalise a single path segment, or raise ``NameInvalid``."""
    if not isinstance(name, str) or not name:
        raise NameInvalid("a name is required")
    if name in (".", ".."):
        raise NameInvalid("the name %r is reserved" % name)
    if name.startswith("."):
        raise NameInvalid("the name %r may not start with a dot" % name)
    if any(ch in _BAD_NAME_CHARS for ch in name):
        raise NameInvalid("the name %r contains an illegal character" % name)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise NameInvalid("the name contains a control character")
    if len(name.encode("utf-8")) > 255:
        raise NameInvalid("the name is longer than 255 bytes")
    return unicodedata.normalize("NFC", name)


def normalise_rel(rel):
    """Turn a client-supplied relative path into validated segments.

    Rejects the shapes that would otherwise be resolved away silently: an
    absolute path, a drive-like prefix, an empty segment, and any ``..``. Doing
    this before touching the filesystem means the containment check afterwards
    is a second line of defence rather than the only one.
    """
    if rel is None:
        rel = ""
    if not isinstance(rel, str):
        raise PathInvalid("the path must be a string")
    if "\x00" in rel:
        raise PathInvalid("the path contains an invalid character")
    text = rel.strip().replace("\\", "/")
    if text.startswith("/"):
        raise PathInvalid("the path must be relative to your notes library")
    segments = []
    for raw in text.split("/"):
        if not raw or raw == ".":
            continue
        if raw == "..":
            raise PathInvalid("the path must not contain '..'")
        segments.append(validate_name(raw))
    return segments


def _resolve_under(root, segments):
    """Prove that ``root/segments`` really lands inside ``root``.

    ``realpath`` is applied to both sides, so a symbolic link anywhere along the
    way is judged by where it points rather than by how it was spelled. The
    trailing separator on the prefix comparison is what stops ``/lib-backup``
    from counting as being inside ``/lib``.
    """
    if not root:
        raise LibraryUnavailable("the notes library is not available")
    root_real = os.path.realpath(root)
    target = os.path.join(root_real, *segments) if segments else root_real
    resolved = os.path.realpath(target)
    if resolved != root_real and not resolved.startswith(root_real + os.sep):
        raise PathInvalid("the path is outside your notes library")
    return resolved, root_real


def user_notes_root(user):
    """The directory holding one user's notes, created on first use.

    Each user gets their own subtree under the library the package owns. The
    service runs as a single account, so this separation is enforced here rather
    than by the operating system - see the identity notes in ``auth.py`` for
    what that does and does not guarantee.
    """
    if not user:
        raise LibraryUnavailable("no user was resolved for this request")
    base = config.user_notes_root(user)
    if not base:
        raise LibraryUnavailable("the notes library is not available")
    try:
        os.makedirs(base, exist_ok=True)
    except FileExistsError:
        pass
    except PermissionError:
        raise LibraryNotWritable("your notes folder could not be created")
    except OSError as exc:
        log.warning("cannot create %s: %s", base, exc)
        raise LibraryUnavailable("your notes folder could not be created")
    return base


def resolve_note(user, rel, *, must_exist=False):
    """Return ``(absolute_path, notes_root)`` for a client-supplied path."""
    root = user_notes_root(user)
    segments = normalise_rel(rel)
    path, root_real = _resolve_under(root, segments)
    if must_exist:
        if not os.path.exists(path):
            raise NoteNotFound("the note does not exist")
        if os.path.islink(path):
            raise PathInvalid("the path is a symbolic link")
    return path, root_real


def resolve_dir(user, rel):
    """Return the absolute path of a directory inside the user's library."""
    root = user_notes_root(user)
    segments = normalise_rel(rel)
    path, root_real = _resolve_under(root, segments)
    if not os.path.isdir(path):
        raise NoteNotFound("the folder does not exist")
    return path, root_real


# ------------------------------------------------------------------ reading


def _decode(raw):
    """Return ``(text, had_bom)``; notes are UTF-8 and may carry a BOM."""
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", "replace")
    return text, had_bom


def _detect_eol(text):
    return "crlf" if "\r\n" in text else "lf"


def _apply_eol(text, eol):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "\r\n") if eol == "crlf" else text


def revision_of(path, *, stat_result=None):
    """A token that changes whenever the content does.

    Content hashing is what makes conflict detection trustworthy: an editor
    writing a file to the same length leaves mtime and size alone on a
    filesystem with coarse timestamps. Above ``hash_max_bytes`` the cheaper
    mtime+size pair is used instead, and that weakness is stated here rather
    than left to be discovered.
    """
    st = stat_result or os.stat(path)
    if st.st_size > config.hash_max_bytes:
        return "m:%d:%d" % (st.st_mtime_ns, st.st_size)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_note(user, rel):
    """Return the note's content and everything needed to save it back safely."""
    path, _root = resolve_note(user, rel, must_exist=True)
    if not os.path.isfile(path):
        raise NoteNotFound("the note does not exist")
    try:
        st = os.stat(path)
        if st.st_size > config.max_note_bytes:
            raise NoteTooLarge(
                "this note is larger than the %d MB limit"
                % (config.max_note_bytes // (1024 * 1024))
            )
        with open(path, "rb") as handle:
            raw = handle.read()
    except PermissionError:
        raise PathDenied("the notes library refused access to that note")
    except FileNotFoundError:
        raise NoteNotFound("the note does not exist")
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        raise PathDenied("the note could not be read")

    text, had_bom = _decode(raw)
    writable, _reason = probe_writable(os.path.dirname(path))
    return {
        "path": rel,
        "name": os.path.basename(path),
        "content": text,
        "rev": revision_of(path, stat_result=st),
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "eol": _detect_eol(text),
        "bom": had_bom,
        "writable": writable,
    }


# ------------------------------------------------------------------ listing


def list_tree(user, rel="", depth=1):
    """List one directory of the user's library. Folders come first."""
    path, root = resolve_dir(user, rel)
    entries = []
    truncated = False
    try:
        with os.scandir(path) as scanned:
            for entry in scanned:
                name = entry.name
                if name.startswith("."):
                    # Dot entries are staging files and platform bookkeeping far
                    # more often than content, and a notes app has no reason to
                    # offer them.
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                rel_child = _rel_of(entry.path, root)
                item = {
                    "name": name,
                    "path": rel_child,
                    "type": "dir" if is_dir else "file",
                    "note": (not is_dir) and _is_note(name),
                    "size": 0,
                    "mtime_ns": 0,
                }
                if not is_dir:
                    try:
                        info = entry.stat()
                    except OSError:
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        # Sockets, FIFOs and device nodes are not notes and must
                        # never be offered as one.
                        continue
                    item["size"] = int(info.st_size)
                    item["mtime_ns"] = int(info.st_mtime_ns)
                    if not item["note"]:
                        # Present, but not something this editor will open.
                        item["type"] = "other"
                entries.append(item)
                if len(entries) >= config.tree_max_entries:
                    truncated = True
                    break
    except PermissionError:
        raise PathDenied("the notes library refused access to that folder")
    except FileNotFoundError:
        raise NoteNotFound("the folder does not exist")
    except OSError as exc:
        log.warning("cannot list %s: %s", path, exc)
        raise PathDenied("the folder could not be read")

    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))
    readable, _r = probe_readable(path)
    writable, _w = probe_writable(path)
    return {
        "path": rel,
        "root": config.user_notes_root(user),
        "readable": readable,
        "writable": writable,
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
    }


def _rel_of(path, root):
    rel = os.path.relpath(path, root)
    return "" if rel == "." else rel.replace(os.sep, "/")


def _is_note(name):
    return name.lower().endswith(config.note_extensions)


# ------------------------------------------------------------------ writing


def _fsync_dir(path):
    """Best effort; a directory that cannot be fsynced is not a failed save."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(target, data):
    """Replace ``target`` with ``data`` without ever leaving it half-written.

    The staging file is created in the target's own directory on purpose. A
    staging file in the application's tmp directory is on a different
    filesystem, and replacing across filesystems is not atomic - and does not
    raise either, because the tools fall back to copy. Same-directory staging
    keeps ``os.replace`` a real rename.
    """
    parent = os.path.dirname(target)
    handle_fd = None
    tmp = None
    try:
        handle_fd, tmp = tempfile.mkstemp(
            prefix=_TMP_PREFIX + os.path.basename(target) + ".", dir=parent
        )
        with os.fdopen(handle_fd, "wb") as handle:
            handle_fd = None  # the file object owns it now
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        tmp = None
        _fsync_dir(parent)
    finally:
        if handle_fd is not None:
            try:
                os.close(handle_fd)
            except OSError:
                pass
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _encode(content, eol, bom):
    text = _apply_eol(content, eol)
    data = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if bom else data


def _check_size(data):
    if len(data) > config.max_note_bytes:
        raise NoteTooLarge(
            "this note is larger than the %d MB limit"
            % (config.max_note_bytes // (1024 * 1024))
        )


def _require_writable_directory(path):
    ok, reason = probe_writable(path)
    if not ok:
        if reason == "missing":
            raise NoteNotFound("the folder does not exist")
        raise LibraryNotWritable("that folder cannot be written to")


def _note_extension_message():
    return "a note name must end with one of %s" % ", ".join(config.note_extensions)


def create_folder(user, rel):
    """Create a folder, creating any missing parents with it."""
    root = user_notes_root(user)
    segments = normalise_rel(rel)
    if not segments:
        raise NameInvalid("a folder needs a name")
    path, root_real = _resolve_under(root, segments)
    try:
        os.makedirs(path, exist_ok=True)
    except PermissionError:
        raise LibraryNotWritable("that folder cannot be created")
    except OSError as exc:
        log.warning("cannot create folder %s: %s", path, exc)
        raise LibraryNotWritable("the folder could not be created")
    if os.path.realpath(path) != path:
        raise PathInvalid("the path is outside your notes library")
    return {"path": _rel_of(path, root_real), "created": True}


def create_note(user, rel, content="", eol="lf"):
    """Create a note, refusing to overwrite anything that is already there.

    Missing parent folders are created along the way, because a person typing
    ``projects/2026/roadmap.md`` into a "new note" box means the tree, not an
    error message. The folders are made before the existence check so that a
    rejected duplicate does not leave a half-built path behind.
    """
    root = user_notes_root(user)
    segments = normalise_rel(rel)
    if not segments:
        raise NameInvalid("a note needs a name")
    path, root_real = _resolve_under(root, segments)
    if not _is_note(segments[-1]):
        raise NameInvalid(_note_extension_message())

    parent = os.path.dirname(path)
    try:
        os.makedirs(parent, exist_ok=True)
    except PermissionError:
        raise LibraryNotWritable("that folder cannot be created")
    except OSError as exc:
        log.warning("cannot create %s: %s", parent, exc)
        raise LibraryNotWritable("the folder could not be created")

    _require_writable_directory(parent)
    if os.path.islink(path):
        raise PathInvalid("the path is a symbolic link")

    data = _encode(content, eol, False)
    _check_size(data)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        raise NoteExists("a note already exists at that path")
    except PermissionError:
        raise LibraryNotWritable("that folder cannot be written to")
    except OSError as exc:
        log.warning("cannot create %s: %s", path, exc)
        raise LibraryNotWritable("the note could not be created")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except OSError as exc:
        log.warning("cannot write %s: %s", path, exc)
        raise LibraryNotWritable("the note could not be written")

    # Re-resolve after the fact: a parent directory swapped for a symlink
    # between the check and the open would otherwise go unnoticed.
    if os.path.realpath(path) != path:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise PathInvalid("the path is outside your notes library")

    return read_note(user, _rel_of(path, root_real))


def save_note(user, rel, content, base_rev=None, eol="lf", force=False):
    """Write an existing note, refusing to clobber a concurrent edit.

    ``base_rev`` is the revision the client loaded. If the file on disk no
    longer matches it, someone else has written since - over SMB, in another
    tab, or from the File Manager - and the answer is a conflict carrying the
    current content, not a silent overwrite of their work.
    """
    path, root_real = resolve_note(user, rel, must_exist=True)
    if not os.path.isfile(path):
        raise NoteNotFound("the note does not exist")
    if os.path.islink(path):
        raise PathInvalid("the path is a symbolic link")

    _require_writable_directory(os.path.dirname(path))

    current_rev = revision_of(path)
    if not force and base_rev and base_rev != current_rev:
        from .errors import ConflictDetected

        try:
            with open(path, "rb") as handle:
                current_text, had_bom = _decode(handle.read())
        except OSError:
            current_text, had_bom = "", False
        raise ConflictDetected(
            "this note was changed by someone else",
            detail={
                "current_rev": current_rev,
                "current_content": current_text,
                "current_eol": _detect_eol(current_text),
                "current_bom": had_bom,
            },
        )

    data = _encode(content, eol, False)
    _check_size(data)
    try:
        atomic_write(path, data)
    except PermissionError:
        raise LibraryNotWritable("that note cannot be written to")
    except OSError as exc:
        log.warning("cannot save %s: %s", path, exc)
        raise LibraryNotWritable("the note could not be saved")

    return read_note(user, rel)


def rename_note(user, src_rel, dst_rel, overwrite=False):
    """Rename or move a note inside the same user's library."""
    root = user_notes_root(user)
    src, root_real = resolve_note(user, src_rel, must_exist=True)
    if os.path.islink(src):
        raise PathInvalid("the path is a symbolic link")
    if not os.path.isfile(src):
        raise NoteNotFound("the note does not exist")

    segments = normalise_rel(dst_rel)
    if not segments:
        raise NameInvalid("a note needs a name")
    if not _is_note(segments[-1]):
        raise NameInvalid(_note_extension_message())
    dst, _ = _resolve_under(root, segments)

    if os.path.islink(dst):
        raise PathInvalid("the destination is a symbolic link")
    if os.path.exists(dst) and not overwrite:
        raise NoteExists("something already exists at that path")

    _require_writable_directory(os.path.dirname(dst))
    try:
        os.replace(src, dst)
    except PermissionError:
        raise LibraryNotWritable("that folder cannot be written to")
    except OSError as exc:
        log.warning("cannot rename %s -> %s: %s", src, dst, exc)
        raise LibraryNotWritable("the note could not be moved")

    return read_note(user, _rel_of(dst, root_real))


def delete_note(user, rel):
    """Delete a note. The caller is responsible for having confirmed it."""
    path, _root = resolve_note(user, rel, must_exist=True)
    if os.path.islink(path):
        raise PathInvalid("the path is a symbolic link")
    if not os.path.isfile(path):
        raise NoteNotFound("the note does not exist")
    _require_writable_directory(os.path.dirname(path))
    try:
        os.unlink(path)
    except PermissionError:
        raise LibraryNotWritable("that note cannot be deleted")
    except OSError as exc:
        log.warning("cannot delete %s: %s", path, exc)
        raise LibraryNotWritable("the note could not be deleted")
    return {"path": rel, "deleted": True}


# ------------------------------------------------------------------ health


def summary():
    """Counts for the health payload. Never raises."""
    try:
        root = config.share_root()
        if not root:
            return {"library_ready": False, "share_root": "", "users": 0}
        readable, _ = probe_readable(root)
        writable, _ = probe_writable(root)
        users = 0
        users_root = config.users_root()
        if readable and os.path.isdir(users_root):
            try:
                with os.scandir(users_root) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir():
                                users += 1
                        except OSError:
                            continue
            except OSError:
                users = 0
        return {
            "library_ready": readable and writable,
            "share_root": root,
            "readable": readable,
            "writable": writable,
            "users": users,
        }
    except Exception as exc:  # pragma: no cover - a health answer must not fail
        log.info("library summary unavailable: %s", exc)
        return {"library_ready": False, "share_root": "", "users": 0}
