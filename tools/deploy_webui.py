#!/usr/bin/env python3
"""Deploy the WebUI to a TOS device over SFTP and restart the app.

TOS unpacks webui.bz2 into /usr/local/<appid>/webui at install time, so a
frontend fix has to be pushed both as the unpacked tree and as the archive,
otherwise the next package upgrade would overwrite the fix.

This is a maintainer utility: it is not part of the .deb payload, and it takes
its credentials from the environment so that no device secret lives in the
repository (the packaging pipeline scans for inline credentials).

Credentials:
    PRINT_HOST, PRINT_PORT, PRINT_USER, PRINT_PASS

Usage:
    PRINT_HOST=10.0.0.10 PRINT_USER=admin PRINT_PASS=... python tools/deploy_webui.py
    python tools/deploy_webui.py --no-restart
"""

import argparse
import bz2
import io
import os
import posixpath
import sys
import tarfile

APP_ID = "marknest"
APP_ROOT = "/usr/local/%s" % APP_ID

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
WEBUI_SRC = os.path.join(REPO_ROOT, "webui")

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", ".workbuddy"}


def _setting(name, default=None):
    value = os.environ.get(name)
    if value:
        return value
    if default is not None:
        return default
    raise SystemExit(
        "%s is not set. Export PRINT_HOST / PRINT_PORT / PRINT_USER / PRINT_PASS "
        "before running this utility." % name
    )


def connect():
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=_setting("PRINT_HOST"),
        port=int(_setting("PRINT_PORT", "22")),
        username=_setting("PRINT_USER"),
        password=_setting("PRINT_PASS"),
        timeout=20,
        banner_timeout=30,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def iter_files(source):
    for base, dirs, files in os.walk(source):
        dirs[:] = sorted(item for item in dirs if item not in EXCLUDE_DIRS)
        for name in sorted(files):
            path = os.path.join(base, name)
            yield path, os.path.relpath(path, source).replace(os.sep, "/")


def build_archive(source):
    """Reproduce the deterministic tar.bz2 layout used by tools/build.py."""
    entries = list(iter_files(source))
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
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
    return bz2.compress(raw.getvalue(), compresslevel=9), len(entries)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()

    import paramiko

    if not os.path.isfile(os.path.join(WEBUI_SRC, "index.html")):
        raise SystemExit("webui/index.html not found at %s" % WEBUI_SRC)

    archive_bytes, count = build_archive(WEBUI_SRC)
    print("packed %d file(s), %d bytes" % (count, len(archive_bytes)))

    client = connect()
    sftp = client.open_sftp()
    try:
        remote_root = posixpath.join(APP_ROOT, "webui")

        def ensure(path):
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current = current + "/" + part
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)

        ensure(remote_root)

        uploaded = 0
        for local, rel in iter_files(WEBUI_SRC):
            remote = posixpath.join(remote_root, rel)
            ensure(posixpath.dirname(remote))
            sftp.put(local, remote)
            uploaded += 1
            print("  put %s" % rel)

        # Refresh the packed archive as well so the fix survives the next
        # package upgrade (postinst does not re-unpack, but a reinstall does).
        remote_archive = posixpath.join(APP_ROOT, "webui.bz2")
        with sftp.open(remote_archive, "wb") as handle:
            handle.write(archive_bytes)
        print("  put webui.bz2 (%d bytes)" % len(archive_bytes))

        # Ownership so nginx can read the files through the proxy.
        stdin, stdout, stderr = client.exec_command(
            "chown -R root:root %s && chmod -R a+rX %s" % (remote_root, remote_root),
            timeout=60,
        )
        stdout.read()
        stderr.read()
        print("uploaded %d file(s)" % uploaded)
    finally:
        sftp.close()

    if not args.no_restart:
        stdin, stdout, stderr = client.exec_command(
            "systemctl restart marknest.service; sleep 3; systemctl is-active marknest.service",
            timeout=90,
        )
        out = stdout.read().decode("utf-8", "replace").strip()
        err = stderr.read().decode("utf-8", "replace").strip()
        print("service after restart: %s" % out)
        if err:
            print("stderr: %s" % err)

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
