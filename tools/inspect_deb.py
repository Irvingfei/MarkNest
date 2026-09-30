#!/usr/bin/env python3
"""Pure-Python inspector for a Debian package (.deb).

``dpkg-deb`` is not available on Windows and is frequently absent from a
developer workstation, so ``tools/build.py`` produces the archive with a small
ar/tar writer. This module reads that archive back and verifies the structure
that the TOS platform parser depends on:

  * the ar container holds exactly ``debian-binary``, ``control.tar.gz`` and
    ``data.tar.gz`` in that order
  * ``debian-binary`` contains ``2.0``
  * ``control.tar.gz`` contains ``./control`` and the lifecycle scripts
  * ``data.tar.gz`` never contains the ``DEBIAN`` directory
  * the metadata files sit under ``usr/local/<appid>/`` inside ``data.tar``

Usage:
    python tools/inspect_deb.py dist/marknest_1.0.0_x86_64.deb
"""

import gzip
import io
import os
import re
import sys
import tarfile

AR_MAGIC = b"!<arch>\n"

REQUIRED_DATA_FILES = (
    "usr/local/marknest/config.ini",
    "usr/local/marknest/marknest.lang",
    "usr/local/marknest/marknest.env",
    "usr/local/marknest/webui.bz2",
    "usr/local/marknest/images/icons/marknest.svg",
    "usr/local/marknest/init.d/marknest.service",
    "usr/local/marknest/bin/marknest-server",
)

REQUIRED_CONTROL_FILES = ("control", "preinst", "postinst", "prerm", "postrm")


class InspectionError(Exception):
    pass


def read_ar(path):
    """Return an ordered list of (name, payload) from an ar archive."""
    with open(path, "rb") as handle:
        data = handle.read()
    if not data.startswith(AR_MAGIC):
        raise InspectionError("not an ar archive (missing !<arch> magic)")
    entries = []
    offset = len(AR_MAGIC)
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        if header[58:60] != b"`\n":
            raise InspectionError("corrupt ar header at offset %d" % offset)
        name = header[0:16].decode("ascii", "replace").strip().rstrip("/")
        try:
            size = int(header[48:58].decode("ascii", "replace").strip() or "0")
        except ValueError:
            raise InspectionError("invalid ar size field for %r" % name)
        start = offset + 60
        payload = data[start : start + size]
        entries.append((name, payload))
        offset = start + size
        if size % 2:
            offset += 1
    if not entries:
        raise InspectionError("ar archive contains no members")
    return entries


def normalise(name):
    """Strip the leading './' and any trailing slash from a tar member name."""
    cleaned = name.replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.rstrip("/")


def tar_members(payload):
    """Return an ordered list of (name, size, mode, is_dir) for a gzipped tar."""
    try:
        raw = gzip.decompress(payload)
    except OSError as exc:
        raise InspectionError("control/data tar is not valid gzip: %s" % exc)
    members = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive.getmembers():
            members.append(
                (
                    normalise(member.name),
                    member.size,
                    member.mode,
                    member.isdir(),
                    member.islnk() or member.issym(),
                )
            )
    return members


def inspect(path, app_id="marknest", verbose=True):
    errors = []
    notes = []

    entries = read_ar(path)
    names = [name for name, _ in entries]
    if names[:1] != ["debian-binary"]:
        errors.append("first ar member must be debian-binary, found %r" % (names[:1] or None))
    if "control.tar.gz" not in names:
        errors.append("control.tar.gz is missing from the ar container")
    if "data.tar.gz" not in names:
        errors.append("data.tar.gz is missing from the ar container")
    if names != ["debian-binary", "control.tar.gz", "data.tar.gz"]:
        errors.append("unexpected ar member order or extra members: %s" % ", ".join(names))
    if errors:
        return errors, notes

    payloads = dict(entries)
    if payloads["debian-binary"].strip() != b"2.0":
        errors.append("debian-binary must contain 2.0, found %r" % payloads["debian-binary"])
    else:
        notes.append("debian-binary version is 2.0")

    control_members = tar_members(payloads["control.tar.gz"])
    control_names = [item[0] for item in control_members if not item[3]]
    for required in REQUIRED_CONTROL_FILES:
        if required not in control_names:
            errors.append("control.tar.gz is missing %s" % required)
    if control_names:
        notes.append("control.tar.gz contains %d file(s): %s" % (len(control_names), ", ".join(sorted(control_names))))
    for name, size, mode, is_dir, is_link in control_members:
        if is_dir:
            continue
        if name in ("preinst", "postinst", "prerm", "postrm") and not (mode & 0o111):
            errors.append("lifecycle script %s is not executable (mode %o)" % (name, mode))

    data_members = tar_members(payloads["data.tar.gz"])
    data_names = [item[0] for item in data_members]
    data_files = [item[0] for item in data_members if not item[3]]

    if any(name == "DEBIAN" or name.startswith("DEBIAN/") for name in data_names):
        errors.append("data.tar.gz must not contain the DEBIAN directory")
    else:
        notes.append("data.tar.gz excludes DEBIAN")

    for required in REQUIRED_DATA_FILES:
        if required not in data_files:
            errors.append("data.tar.gz is missing %s" % required)
    notes.append("data.tar.gz holds %d file(s)" % len(data_files))

    # Metadata must not sit at the archive root.
    for stray in ("config.ini", "%s.lang" % app_id):
        if stray in data_files:
            errors.append("metadata %s is at the package root instead of usr/local/%s/" % (stray, app_id))

    server = "usr/local/%s/bin/marknest-server" % app_id
    for name, size, mode, is_dir, is_link in data_members:
        if name == server and not (mode & 0o111):
            errors.append("%s is not executable (mode %o)" % (name, mode))

    # No payload file may be group- or world-writable. Building on Windows
    # yields 0666 for every regular file unless the writer sets the mode, and a
    # world-writable file inside an installed application is a privilege
    # escalation vector the review checklist rejects.
    world_writable = [
        (name, mode)
        for name, size, mode, is_dir, is_link in data_members
        if not is_dir and mode & 0o022
    ]
    if world_writable:
        for name, mode in world_writable:
            errors.append("payload file %s is group/world-writable (mode %o)" % (name, mode))
    else:
        notes.append("no payload file is group- or world-writable")

    if verbose:
        print("deb inspection - %s" % os.path.basename(path))
        print("=" * 62)
        for note in notes:
            print("  [OK  ] %s" % note)
        for item in errors:
            print("  [FAIL] %s" % item)
        print("-" * 62)
        print("members in data.tar.gz:")
        for name in sorted(data_files):
            print("    %s" % name)
        print("-" * 62)
        print("errors: %d" % len(errors))

    return errors, notes


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dist = os.path.join(here, "dist")
        candidates = []
        if os.path.isdir(dist):
            candidates = [os.path.join(dist, n) for n in sorted(os.listdir(dist)) if n.endswith(".deb")]
        if not candidates:
            print("usage: python tools/inspect_deb.py <package.deb>")
            return 2
        target = candidates[-1]
    else:
        target = argv[0]
    if not os.path.isfile(target):
        print("package not found: %s" % target)
        return 2
    errors, _ = inspect(target)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
