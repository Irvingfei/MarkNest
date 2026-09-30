#!/usr/bin/env python3
"""Is the user cookie reaching the application at all?

Two very different faults look the same from the browser:

  * the application cannot read the cookie it was given, or
  * the platform proxy never forwards that cookie to the application's socket.

Talking to the socket directly separates them: if the same request works there,
the proxy is the one dropping something, and the application is fine.

Also dumps the journal around the request, which is where the application says
what it decided. Read-only.
"""

import os
import sys

import paramiko

from _device import setting  # noqa: E402  (same directory)

APPID = "marknest"


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

    socket_path = "/var/api/%s.sock" % APPID

    steps = [
        ("identity, straight at the socket, with the real cookie names",
         "curl -s -m 15 --unix-socket %s "
         "-H 'Cookie: TMSESSNAME=0123456789abcdef; X-Csrf-Token=0123456789abcdef; tos_current_username=test;' "
         "http://localhost/me; echo" % socket_path),
        ("the same, but only the two auth cookies",
         "curl -s -m 15 --unix-socket %s "
         "-H 'Cookie: TMSESSNAME=0123456789abcdef; X-Csrf-Token=0123456789abcdef;' "
         "http://localhost/me; echo" % socket_path),
        ("a user name that is not a system account",
         "curl -s -m 15 --unix-socket %s "
         "-H 'Cookie: TMSESSNAME=0123456789abcdef; X-Csrf-Token=0123456789abcdef; tos_current_username=nosuchuser;' "
         "http://localhost/me; echo" % socket_path),
        ("/health, which needs no user",
         "curl -s -m 15 --unix-socket %s http://localhost/health; echo" % socket_path),
        ("what the application logged",
         "journalctl -u %s.service --no-pager -n 30 2>&1 | tail -20" % APPID),
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
