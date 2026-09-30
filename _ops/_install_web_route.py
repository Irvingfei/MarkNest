#!/usr/bin/env python3
"""Give the application a web route, the way the App Center does.

The platform creates /etc/nginx/AppAccessControl/AppAccessControl-<appid>.conf
when it installs an application from the App Center. A .deb installed by hand
gets none of it, so the application ends up in a strange half-state: the service
runs, the web directory is unpacked and linked, and nothing on the web can reach
any of it.

This writes that file by deriving it from an application the platform already
installed - the same shape, the same auth integration, only the identifier
changed - and reloads nginx. It is additive and reversible: one new file, and
removing it plus a reload puts things back.

    python _ops/_install_web_route.py            # dry run
    python _ops/_install_web_route.py --commit
"""

import argparse
import os
import sys

import paramiko

from _device import setting  # noqa: E402  (same directory)

APPID = "marknest"
TEMPLATE_APP = "printcenter"
TARGET = "/etc/nginx/AppAccessControl/AppAccessControl-%s.conf" % APPID
SOURCE = "/etc/nginx/AppAccessControl/AppAccessControl-%s.conf" % TEMPLATE_APP


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

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
        _, out, _ = client.exec_command("cat %s" % SOURCE, timeout=60)
        template = out.read().decode("utf-8", "replace")
        if not template.strip():
            raise SystemExit("template %s not found on the device" % SOURCE)

        rendered = template.replace(TEMPLATE_APP, APPID)
        print("template : %s (%d bytes)" % (SOURCE, len(template)))
        print("target   : %s" % TARGET)
        print("substitutions: %d occurrence(s) of %r -> %r"
              % (template.count(TEMPLATE_APP), TEMPLATE_APP, APPID))
        print()
        print(rendered[:600])
        print("...")

        if not args.commit:
            print("\nDRY RUN - re-run with --commit")
            return 0

        sftp = client.open_sftp()
        try:
            with sftp.open(TARGET, "w") as handle:
                handle.write(rendered)
        finally:
            sftp.close()

        _, out, _ = client.exec_command(
            "chmod 0644 %s && nginx -t 2>&1 && systemctl reload nginx && echo RELOADED" % TARGET,
            timeout=120)
        print(out.read().decode("utf-8", "replace"))

        print("checking the route")
        _, out, _ = client.exec_command(
            "echo '--- where a redirect goes ---'; "
            "curl -s -o /dev/null -m 10 -w '%{http_code} -> %{redirect_url}\\n' http://127.0.0.1/marknest/; "
            "echo '--- port 8181, the desktop''s own ---'; "
            "for p in /marknest/ /marknest/index.html; do "
            "printf '%-24s ' \"$p\"; "
            "curl -s -o /dev/null -m 10 -w '%{http_code} -> %{redirect_url}\\n' \"http://127.0.0.1:8181$p\"; done; "
            "echo '--- does the file itself come back ---'; "
            "curl -s -m 10 http://127.0.0.1/marknest/index.html 2>&1 | head -c 160; echo",
            timeout=120)
        print(out.read().decode("utf-8", "replace"))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
