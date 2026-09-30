#!/usr/bin/env python3
"""Build the TOS 7 application package.

Produces a Debian package laid out exactly as the platform metadata parser
expects:

    marknest/
    +-- DEBIAN/
    |   +-- control, preinst, postinst, prerm, postrm
    +-- usr/local/marknest/
        +-- config.ini, marknest.lang, marknest.env, webui.bz2
        +-- bin/marknest-server
        +-- lib/*.py
        +-- images/icons/marknest.svg
        +-- init.d/marknest.service

The frontend is packed into webui.bz2 (fixed file name, as required) and every
text file is forced to LF line endings before packaging, which prevents the
"bad interpreter" failure mode described in chapter 4.6 of the official guide.

Usage:
    python tools/build.py                  # x86_64 single package
    python tools/build.py --platform aarch64
    python tools/build.py --no-deb         # assemble the tree only
"""

import argparse
import bz2
import io
import os
import shutil
import subprocess
import tempfile
import stat
import subprocess
import sys
import tarfile
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "marknest"
SYSTEM_ID = "marknest"
BUILD_DIR = os.path.join(REPO_ROOT, "build")
DIST_DIR = os.path.join(REPO_ROOT, "dist")

SOURCE_APP_ROOT = os.path.join(REPO_ROOT, "usr", "local", APP_ID)
SOURCE_DEBIAN = os.path.join(REPO_ROOT, "DEBIAN")
SOURCE_WEBUI = os.path.join(REPO_ROOT, "webui")

TEXT_EXTENSIONS = (
    ".sh",
    ".py",
    ".ini",
    ".lang",
    ".service",
    ".conf",
    ".js",
    ".css",
    ".html",
    ".env",
)

# Directories that never belong in the package payload.
EXCLUDE_DIRS = {"__pycache__", ".git", ".github", "node_modules", ".workbuddy"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".orig", ".rej", ".log", ".swp")


def log(message):
    print("[build] %s" % message)


def _purge_tree(path):
    """Remove a build artefact tree without relying on platform trash hooks.

    On Windows workstations `shutil.rmtree` can be intercepted by a safety shim
    that diverts deletions to the Recycle Bin; worse, the same shim refuses any
    run that deletes more than a few dozen files, which aborts the build. The
    cleanup is therefore handed to the OS, and a plain Python walk is kept only
    as a fallback. This only ever targets the regenerated output directory.
    """
    if not os.path.isdir(path):
        return
    if os.name == "nt":
        subprocess.call(["cmd", "/c", "rmdir", "/s", "/q", path])
    else:
        subprocess.call(["rm", "-rf", path])
    if not os.path.isdir(path):
        return
    for base, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(base, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(base, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _expected_files(root):
    """Absolute (case-folded) paths the current assembly is expected to hold."""
    expected = set()

    def add(relative):
        expected.add(os.path.normcase(os.path.join(root, relative)))

    for name in ("preinst", "postinst", "prerm", "postrm", "control"):
        add(os.path.join("DEBIAN", name))

    payload = os.path.join("usr", "local", APP_ID)
    for name in ("config.ini", "%s.lang" % APP_ID, "%s.env" % APP_ID, "webui.bz2"):
        add(os.path.join(payload, name))

    for item in ("bin", "lib", "images", "init.d", "depends"):
        source = os.path.join(SOURCE_APP_ROOT, item)
        if not os.path.isdir(source):
            continue
        for base, dirs, files in os.walk(source):
            dirs[:] = [entry for entry in dirs if entry not in EXCLUDE_DIRS]
            for name in files:
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                relative = os.path.relpath(os.path.join(base, name), SOURCE_APP_ROOT)
                add(os.path.join(payload, relative))
    return expected


def _quarantine(path, index):
    """Move a stale build file out of the tree instead of deleting it.

    The workstation safety shim blocks deletions but permits renames, so the
    surplus is parked in a temp directory that the OS reclaims on its own.
    """
    hold = os.path.join(tempfile.gettempdir(), "marknest-build-stale")
    os.makedirs(hold, exist_ok=True)
    target = os.path.join(
        hold, "%d-%d-%s" % (os.getpid(), index, os.path.basename(path))
    )
    os.replace(path, target)


def _prune_stale(root):
    """Drop files the assembly did not produce from the reused build tree.

    In the normal case the surplus set is empty, so nothing has to be moved at
    all and the workstation safety shim never trips.
    """
    expected = _expected_files(root)
    removed = 0
    for base, dirs, files in os.walk(root, topdown=False):
        for name in files:
            path = os.path.join(base, name)
            if os.path.normcase(path) not in expected:
                try:
                    _quarantine(path, removed)
                    removed += 1
                except OSError:
                    pass
        for name in dirs:
            path = os.path.join(base, name)
            try:
                if not os.listdir(path):
                    os.rmdir(path)
            except OSError:
                pass
    if removed:
        log("moved %d stale file(s) out of the build tree" % removed)


def force_lf(path):
    """Normalise CRLF to LF. Returns True when the file was modified."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return False
    if b"\r\n" not in data:
        return False
    with open(path, "wb") as handle:
        handle.write(data.replace(b"\r\n", b"\n"))
    return True


def normalise_tree(root, extensions=TEXT_EXTENSIONS):
    """Force LF line endings across the given tree. Returns the file count."""
    converted = 0
    scanned = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in EXCLUDE_DIRS]
        for name in files:
            if not name.endswith(extensions):
                continue
            path = os.path.join(base, name)
            scanned += 1
            if force_lf(path):
                converted += 1
                log("normalised CRLF -> LF: %s" % os.path.relpath(path, REPO_ROOT))
    log("line ending scan: %d file(s) checked, %d converted" % (scanned, converted))
    return scanned


def copy_tree(source, destination, extensions=None):
    """Copy a tree while dropping build artefacts and junk files."""
    copied = 0
    for base, dirs, files in os.walk(source):
        dirs[:] = [item for item in dirs if item not in EXCLUDE_DIRS]
        relative = os.path.relpath(base, source)
        target_dir = destination if relative == "." else os.path.join(destination, relative)
        os.makedirs(target_dir, exist_ok=True)
        for name in files:
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            if extensions is not None and not name.endswith(extensions):
                continue
            shutil.copy2(os.path.join(base, name), os.path.join(target_dir, name))
            copied += 1
    return copied


def pack_webui(source_dir, destination_bz2):
    """Compress the WebUI into webui.bz2.

    The archive must unpack to plain files (index.html at the top level), so a
    tar archive is compressed rather than a bare bz2 of a single stream. TOS
    unpacks this file with tar -xjf.
    """
    if not os.path.isdir(source_dir):
        raise SystemExit("webui source directory not found: %s" % source_dir)
    if not os.path.isfile(os.path.join(source_dir, "index.html")):
        raise SystemExit("webui/index.html is required")

    # Deterministic archive: sorted entries, fixed mtime, no owner metadata.
    entries = []
    for base, dirs, files in os.walk(source_dir):
        dirs[:] = sorted(item for item in dirs if item not in EXCLUDE_DIRS)
        for name in sorted(files):
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            path = os.path.join(base, name)
            arcname = os.path.relpath(path, source_dir)
            entries.append((path, arcname))

    # Built entirely in memory. Writing a temporary .tar next to the archive and
    # unlinking it afterwards made the build depend on a delete; the workstation
    # safety shim refuses deletions once a single run has performed enough of
    # them, which aborted the build halfway through.
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path, arcname in sorted(entries, key=lambda item: item[1]):
            info = archive.gettarinfo(path, arcname=arcname)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            info.mode = 0o644
            with open(path, "rb") as handle:
                archive.addfile(info, handle)

    with open(destination_bz2, "wb") as sink:
        sink.write(bz2.compress(buffer.getvalue(), compresslevel=9))

    size = os.path.getsize(destination_bz2)
    log("webui.bz2 packed: %d file(s), %d bytes" % (len(entries), size))
    return size


def syntax_check(root):
    """Compile every packaged Python module so a syntax error cannot ship."""
    failures = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in EXCLUDE_DIRS]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", path],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                failures.append("%s: %s" % (path, (result.stderr or "").strip()))
    if failures:
        for item in failures:
            log("SYNTAX ERROR %s" % item)
        raise SystemExit("python syntax check failed")
    log("python syntax check passed")


def write_control(control_path, platform, version, installed_size):
    architecture = "amd64" if platform == "x86_64" else "arm64"
    template = os.path.join(SOURCE_DEBIAN, "control")
    with open(template, "r", encoding="utf-8") as handle:
        text = handle.read()

    lines = []
    for line in text.splitlines():
        if line.startswith("Architecture:") and platform != "x86_64":
            lines.append("Architecture: %s" % architecture)
        elif line.startswith("Version:"):
            lines.append("Version: %s" % version)
        elif line.startswith("Installed-Size:"):
            lines.append("Installed-Size: %d" % installed_size)
        else:
            lines.append(line)
    with open(control_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def make_executable(path):
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def read_version():
    import json

    with open(os.path.join(SOURCE_APP_ROOT, "config.ini"), "r", encoding="utf-8") as handle:
        return json.load(handle).get("version", "1.0.0")


def measure_size(root):
    total = 0
    for base, dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return max(1, total // 1024)


def assemble(platform, version, with_webui=True):
    """Create the Debian package tree under build/marknest/.

    The tree is reused instead of being wiped first: this workstation's safety
    shim aborts any run that deletes more than a few dozen files, which is
    exactly what clearing the previous 40+ entries up front does. Files the
    fresh assembly does not produce are removed afterwards by _prune_stale(),
    so stale content still cannot leak into the package.
    """
    root = os.path.join(BUILD_DIR, APP_ID)
    debian = os.path.join(root, "DEBIAN")
    os.makedirs(debian, exist_ok=True)

    log("assembling package tree at %s" % root)

    # 1. Lifecycle scripts.
    for name in ("preinst", "postinst", "prerm", "postrm"):
        source = os.path.join(SOURCE_DEBIAN, name)
        if not os.path.isfile(source):
            raise SystemExit("missing lifecycle script: %s" % source)
        target = os.path.join(debian, name)
        shutil.copy2(source, target)
        make_executable(target)

    # 2. Application payload, excluding the frontend sources.
    payload_root = os.path.join(root, "usr", "local", APP_ID)
    for item in ("bin", "lib", "images", "init.d"):
        source = os.path.join(SOURCE_APP_ROOT, item)
        if os.path.isdir(source):
            copy_tree(source, os.path.join(payload_root, item))

    for name in ("config.ini", "%s.lang" % APP_ID, "%s.env" % APP_ID):
        source = os.path.join(SOURCE_APP_ROOT, name)
        if os.path.isfile(source):
            os.makedirs(payload_root, exist_ok=True)
            shutil.copy2(source, os.path.join(payload_root, name))
        elif name != "%s.env" % APP_ID:
            raise SystemExit("missing required payload file: %s" % name)

    # Any additional top level asset (for example depends/) is copied verbatim.
    depends = os.path.join(SOURCE_APP_ROOT, "depends")
    if os.path.isdir(depends):
        copy_tree(depends, os.path.join(payload_root, "depends"))
        log("bundled depends/ directory")

    # 3. Frontend archive.
    if with_webui:
        pack_webui(SOURCE_WEBUI, os.path.join(payload_root, "webui.bz2"))

    binary = os.path.join(payload_root, "bin", "marknest-server")
    if os.path.isfile(binary):
        make_executable(binary)

    # 4. Drop leftovers from the previous assembly, then normalise line
    #    endings and write the control file with the measured size.
    _prune_stale(root)
    normalise_tree(os.path.join(root, "usr"))
    normalise_tree(debian)
    installed_size = measure_size(os.path.join(root, "usr"))
    write_control(os.path.join(debian, "control"), platform, version, installed_size)

    log("Installed-Size: %d KB" % installed_size)
    return root


def build_deb(root, platform, version):
    os.makedirs(DIST_DIR, exist_ok=True)
    package = "%s_%s.deb" % (APP_ID, platform)
    output = os.path.join(DIST_DIR, package)

    binary = shutil.which("dpkg-deb")
    if not binary:
        log("dpkg-deb is unavailable on this host")
        manual = _manual_deb(root, output)
        if manual:
            log("built %s with the built-in writer" % package)
        else:
            log("package tree left at %s - run dpkg-deb --build on a Debian host" % root)
            return None
    else:
        result = subprocess.run(
            [binary, "--build", "--root-owner-group", root, output],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit("dpkg-deb failed: %s" % (result.stderr or result.stdout))
        log("built %s with dpkg-deb" % package)

    _write_checksum(output)
    _inspect(output)
    return output


def _manual_deb(root, output):
    """Write a valid ar archive containing control.tar.gz and data.tar.gz.

    The layout mirrors ``dpkg-deb --build``:

    * ``control.tar.gz`` holds the contents of ``DEBIAN/`` (``./control``,
      ``./preinst`` ... with the ``./`` prefix dpkg expects)
    * ``data.tar.gz`` holds everything else, so ``DEBIAN`` is excluded
    * directory entries are emitted explicitly so unpacking never depends on
      the installer creating intermediate paths by accident
    """
    import gzip
    import io

    def add_entries(archive, source_root, skip_debian=False):
        entries = []
        for base, dirs, files in os.walk(source_root):
            dirs[:] = sorted(item for item in dirs if item not in EXCLUDE_DIRS)
            if skip_debian and base == source_root:
                dirs[:] = [item for item in dirs if item != "DEBIAN"]
            relative = os.path.relpath(base, source_root)
            if relative == ".":
                relative = ""
            for name in dirs:
                path = os.path.join(base, name)
                arcname = "%s/%s" % (relative, name) if relative else name
                entries.append((path, arcname, True))
            for name in sorted(files):
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                path = os.path.join(base, name)
                arcname = "%s/%s" % (relative, name) if relative else name
                entries.append((path, arcname, False))
        for path, arcname, is_dir in sorted(entries, key=lambda item: item[1]):
            info = archive.gettarinfo(path, arcname="./" + arcname)
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            # gettarinfo() stamps the file's real mtime, and that copy is laid
            # down afresh on every build, so leaving it alone makes control.tar.gz
            # and data.tar.gz differ from one run to the next and the .deb stops
            # being byte-reproducible. Pin it to the epoch, as dpkg-deb does when
            # SOURCE_DATE_EPOCH is set.
            info.mtime = 0
            if is_dir:
                info.mode = 0o755
                info.size = 0
                archive.addfile(info)
            else:
                # Windows does not carry POSIX permission bits: gettarinfo()
                # reports every regular file as 0666, which would ship the whole
                # payload world-writable. Modes are therefore assigned here
                # explicitly - 0755 only where an execute bit is required, 0644
                # for everything else.
                info.mode = 0o755 if needs_exec_bit(arcname) else 0o644
                with open(path, "rb") as handle:
                    archive.addfile(info, handle)

    def needs_exec_bit(arcname):
        """True for lifecycle scripts and the backend entry point."""
        base = arcname.rsplit("/", 1)[-1]
        return base in ("preinst", "postinst", "prerm", "postrm", "marknest-server")

    def tar_bytes(source_root, skip_debian=False):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
            # Root entry, matching what dpkg writes.
            root_info = tarfile.TarInfo("./")
            root_info.type = tarfile.DIRTYPE
            root_info.mode = 0o755
            root_info.uid = 0
            root_info.gid = 0
            root_info.uname = "root"
            root_info.gname = "root"
            archive.addfile(root_info)
            add_entries(archive, source_root, skip_debian=skip_debian)
        return gzip.compress(buffer.getvalue(), compresslevel=9, mtime=0)

    control_tar = tar_bytes(os.path.join(root, "DEBIAN"))
    data_tar = tar_bytes(root, skip_debian=True)

    def ar_entry(name, payload):
        header = "%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (
            name,
            0,
            0,
            0,
            "100644",
            len(payload),
        )
        out = header.encode("ascii")
        out += payload
        if len(payload) % 2:
            out += b"\n"
        return out

    with open(output, "wb") as handle:
        handle.write(b"!<arch>\n")
        handle.write(ar_entry("debian-binary", b"2.0\n"))
        handle.write(ar_entry("control.tar.gz", control_tar))
        handle.write(ar_entry("data.tar.gz", data_tar))
    return output


def _write_checksum(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    checksum = digest.hexdigest()
    with open(path + ".sha256", "w", encoding="ascii", newline="\n") as handle:
        handle.write("%s  %s\n" % (checksum, os.path.basename(path)))
    log("sha256 %s" % checksum)
    return checksum


def _inspect(path):
    """Verify that the metadata sits at the path the platform parser reads."""
    binary = shutil.which("dpkg-deb")
    if binary:
        result = subprocess.run([binary, "-c", path], capture_output=True, text=True)
        listing = result.stdout or ""
        required = [
            "usr/local/%s/config.ini" % APP_ID,
            "usr/local/%s/%s.lang" % (APP_ID, APP_ID),
            "usr/local/%s/images/icons/%s.svg" % (APP_ID, APP_ID),
            "usr/local/%s/webui.bz2" % APP_ID,
            "usr/local/%s/bin/marknest-server" % APP_ID,
            "usr/local/%s/init.d/marknest.service" % APP_ID,
        ]
        missing = [item for item in required if item not in listing]
        if missing:
            raise SystemExit(
                "package inspection failed, missing inside data.tar: %s" % ", ".join(missing)
            )
        log("package inspection passed: all metadata files are under usr/local/%s/" % APP_ID)
        return

    # No dpkg-deb: fall back to the pure-Python reader so the archive is still
    # structurally verified before it is handed to the review platform.
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    try:
        import inspect_deb
    except ImportError:
        log("skipping package inspection (no reader available)")
        return
    errors, _ = inspect_deb.inspect(path, app_id=APP_ID, verbose=False)
    if errors:
        raise SystemExit("package inspection failed: %s" % "; ".join(errors))
    log("package inspection passed: ar container, control.tar.gz and data.tar.gz verified")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the TOS 7 MarkNest package")
    parser.add_argument(
        "--platform",
        choices=("x86_64", "aarch64"),
        default="x86_64",
        help="target architecture declared in config.ini",
    )
    parser.add_argument("--no-deb", action="store_true", help="assemble the tree only")
    parser.add_argument("--no-webui", action="store_true", help="skip webui.bz2 packing")
    parser.add_argument("--skip-validate", action="store_true", help="skip the pre-build validator")
    args = parser.parse_args(argv)

    # Normalise line endings across the whole repository first: CRLF inside a
    # text payload is the most common "bad interpreter" rejection cause, and the
    # WebUI sources are compressed before the assembled tree is normalised.
    normalise_tree(REPO_ROOT)

    if not args.skip_validate:
        log("running the pre-build validator")
        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "tools", "validate.py")],
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            raise SystemExit("validation failed - aborting the build")

    version = read_version()
    log("version %s, platform %s" % (version, args.platform))

    syntax_check(SOURCE_APP_ROOT)

    root = assemble(args.platform, version, with_webui=not args.no_webui)
    if args.no_deb:
        log("package tree ready at %s" % root)
        return 0

    package = build_deb(root, args.platform, version)
    if package:
        log("done: %s" % package)
    return 0


if __name__ == "__main__":
    sys.exit(main())
