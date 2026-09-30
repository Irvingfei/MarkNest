#!/usr/bin/env python3
"""Why is /marknest/ a 403 when the application itself answers fine?

The service responds on its socket, but the browser gets a 403 with an empty
body - which is an nginx answer, not the application's envelope. Something in
front of the application does not know it exists. Read-only.
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

    steps = [
        ("AppAccessControl configs",
         "ls -la /etc/nginx/AppAccessControl/ 2>&1"),
        ("what a working app's config looks like (printcenter)",
         "head -40 /etc/nginx/AppAccessControl/AppAccessControl-printcenter.conf 2>&1"),
        ("is there one for marknest?",
         "ls -la /etc/nginx/AppAccessControl/*marknest* 2>&1 || echo '(none)'"),
        ("who includes them",
         "grep -rn 'AppAccessControl' /etc/nginx/ 2>/dev/null | head -10"),
        ("the /usr/www link",
         "ls -la /usr/www/ 2>&1 | grep -i -E 'marknest|printcenter' || echo '(no link)'"),
        ("what the web server actually answers",
         "for p in /marknest/ /marknest/index.html /v2/proxy/marknest/health; do "
         "printf '%-32s ' \"$p\"; "
         "curl -s -o /dev/null -m 10 -w '%{http_code}\\n' \"http://127.0.0.1$p\"; done"),
        ("through the socket, for comparison",
         "curl -s -m 10 -o /dev/null -w 'socket /health -> %{http_code}\\n' "
         "--unix-socket /var/api/" + APPID + ".sock http://localhost/health"),
        ("is marknest in the platform's app registry?",
         "grep -o marknest /etc/tos/config/test/allAppIconSort.json 2>/dev/null || echo '(not in allAppIconSort)'; "
         "grep -l marknest /etc/tos/config/test/*.json 2>/dev/null | head -5 || echo '(no registry entry)'"),
        ("how printcenter is registered",
         "grep -o printcenter /etc/tos/config/test/allAppIconSort.json 2>/dev/null; "
         "grep -rl printcenter /etc/tos/config/ 2>/dev/null | head -5"),
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
