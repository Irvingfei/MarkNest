#!/usr/bin/env python3
"""Diagnose what the first MarkNest deployment revealed.

Three things went wrong and each needs a different fix:

  1. /usr/local/marknest/webui does not exist, so webui.bz2 was never unpacked.
     The platform normally does this at install time; a plain dpkg -i does not.
  2. The notes share already existed from an earlier experiment and is owned by
     a different account, so the application user may not be able to traverse
     into it even though postinst created and chowned the users/ subtree.
  3. marknest-server --check reported readable/writable "yes" while the app user
     was denied - because the check ran as root. Worth confirming, because a
     capability probe that only works as root is a probe that lies.

Read-only.
"""

import os
import sys

import paramiko

from _device import setting  # noqa: E402  (same directory)

APPID = "marknest"
SHARE = "marknest-data"
ROOT = "/usr/local/" + APPID


def main():
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

    steps = [
        ("web root symlink",
         "ls -la /usr/www/ | grep -i %s || echo '(no /usr/www/%s link)'" % (APPID, APPID)),
        ("webui directory",
         "ls -ld %s/webui 2>&1; ls %s/ 2>&1 | head -20" % (ROOT, ROOT)),
        ("app user",
         "id %s 2>&1" % APPID),
        ("share root and its ACL",
         "ls -ld /Volume1/%s; getfattr -d -m - /Volume1/%s 2>&1 | head -4" % (SHARE, SHARE)),
        ("as the app user: traverse the root",
         "su -s /bin/sh %s -c 'ls -la /Volume1/%s' 2>&1; echo exit=$?" % (APPID, SHARE)),
        ("as the app user: reach users/",
         "su -s /bin/sh %s -c 'ls -la /Volume1/%s/users' 2>&1; echo exit=$?" % (APPID, SHARE)),
        ("as the app user: actually write",
         "su -s /bin/sh %s -c 'touch /Volume1/%s/users/.probe && rm -f /Volume1/%s/users/.probe && echo WRITE-OK' 2>&1; echo exit=$?"
         % (APPID, SHARE, SHARE)),
        ("for comparison: the printcenter share the mechanism was proved on",
         "ls -ld /Volume1/hhhh 2>&1; getfattr -d -m - /Volume1/hhhh 2>&1 | head -3; "
         "su -s /bin/sh printcenter -c 'ls /Volume1/hhhh' 2>&1; echo exit=$?"),
        ("what ter_share_add says about re-running with the right owner",
         "ter_share_add -h 2>&1 | head -12"),
    ]

    try:
        for label, command in steps:
            _, out, err = client.exec_command(command, timeout=180)
            o = out.read().decode("utf-8", "replace")
            e = err.read().decode("utf-8", "replace")
            print("\n" + "=" * 72)
            print("### %s" % label)
            print("=" * 72)
            sys.stdout.write(o)
            if e.strip():
                sys.stdout.write("--- stderr ---\n%s\n" % e)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(sys.exit(main()))
