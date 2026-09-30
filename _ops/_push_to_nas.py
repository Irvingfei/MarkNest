#!/usr/bin/env python3
"""Copy the built .deb to the team share, and prove the copy is identical."""

import hashlib
import os
import sys

import paramiko

from _device import setting  # noqa: E402  (same directory)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VERSION = open(os.path.join(REPO, "VERSION"), encoding="utf-8").read().strip()
LOCAL = os.path.join(REPO, "dist", "marknest_x86_64.deb")
REMOTE = "/Volume1/public/claude/marknest_x86_64_%s.deb" % VERSION


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if not os.path.isfile(LOCAL):
        raise SystemExit("missing artifact: %s" % LOCAL)

    digest = sha256(LOCAL)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        setting("PRINT_HOST"),
        port=int(setting("PRINT_PORT")),
        username=setting("PRINT_USER"),
        password=setting("PRINT_PASS"),
        timeout=20, banner_timeout=30, auth_timeout=30,
        look_for_keys=False, allow_agent=False,
    )
    try:
        sftp = client.open_sftp()
        try:
            sftp.put(LOCAL, REMOTE)
        finally:
            sftp.close()
        _, out, _ = client.exec_command(
            "ls -la %s; sha256sum %s" % (REMOTE, REMOTE), timeout=120)
        print(out.read().decode("utf-8", "replace"))
        print("local sha256: %s" % digest)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
