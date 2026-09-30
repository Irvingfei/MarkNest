#!/usr/bin/env python3
"""Recreate the notes share with the owner the application actually uses.

The share on this device was created during the feasibility probe, with
``-owner printcenter``. Membership of the SPC ACL is per-object, so the
application account cannot even traverse the root, and postinst's chown of the
``users/`` subtree cannot help: the parent refuses to be entered.

The share holds nothing but the empty ``users/`` directory postinst created, so
it is removed and recreated rather than repaired -- but it is removed, which is
worth saying out loud before running it.

    python _ops/_fix_share_owner.py --commit
"""

import argparse
import os
import sys

import paramiko

from _device import setting  # noqa: E402  (same directory)

SHARE = "marknest-data"
APPID = "marknest"


def sh(client, cmd, timeout=180):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    return out.channel.recv_exit_status(), o + e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if not args.commit:
        print("This would, on the device named by PRINT_HOST:")
        print("  1. ls -la /Volume1/%s      (show what is there)" % SHARE)
        print("  2. rm -rf /Volume1/%s      (it holds only the empty users/ dir)" % SHARE)
        print("  3. ter_share_add -device Volume1 -name %s -owner %s" % (SHARE, APPID))
        print("  4. verify the app user can traverse and write")
        print("  5. re-check smb.conf")
        print("\nDRY RUN - re-run with --commit")
        return 0

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
        print("1. what is in the share now")
        _, out = sh(client, "find /Volume1/%s -maxdepth 3 2>&1 | head -20" % SHARE)
        print(out)

        print("2. removing it")
        _, out = sh(client, "rm -rf /Volume1/%s && echo removed" % SHARE)
        print(out)

        print("3. recreating with the application as owner")
        _, out = sh(client,
                    "ter_share_add -device Volume1 -name %s -owner %s 2>&1; echo exit=$?"
                    % (SHARE, APPID))
        print(out)

        print("4. as the application user: traverse and write")
        _, out = sh(client,
                    "su -s /bin/sh %s -c 'ls -ld /Volume1/%s && "
                    "mkdir -p /Volume1/%s/users/__probe/notes && "
                    "printf \"# probe\\n\" > /Volume1/%s/users/__probe/notes/p.md && "
                    "cat /Volume1/%s/users/__probe/notes/p.md && "
                    "rm -rf /Volume1/%s/users/__probe && echo APP-USER-WRITE-OK' 2>&1; echo exit=$?"
                    % (APPID, SHARE, SHARE, SHARE, SHARE, SHARE))
        print(out)

        print("5. smb.conf entry")
        _, out = sh(client, "grep -A6 -i '%s' /etc/samba/smb.conf 2>/dev/null | head -10" % SHARE)
        print(out)

        print("6. the service's own view (it runs as the application user)")
        _, out = sh(client,
                    "curl -s -m 15 --unix-socket /var/api/%s.sock http://localhost/health" % APPID)
        print(out)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
