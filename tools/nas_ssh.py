#!/usr/bin/env python3
"""Run a diagnostic command set on the TOS device over SSH.

This is a maintainer utility. It is NOT part of the .deb payload and must never
contain a device credential in the source, because the repository is the input
to the packaging pipeline and its secret scanner treats any inline credential as
a release blocker.

Credentials are taken from the environment:
    PRINT_HOST, PRINT_PORT, PRINT_USER, PRINT_PASS

Usage:
    PRINT_HOST=10.0.0.10 PRINT_USER=admin PRINT_PASS=... python tools/nas_ssh.py
    python tools/nas_ssh.py --cmd "id"
    python tools/nas_ssh.py --script file.sh
"""

import argparse
import os
import sys


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


def run(client, command, timeout=60):
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


DIAGNOSTICS = [
    ("host", "uname -a; cat /etc/os-release 2>/dev/null | head -3"),
    ("install", "ls -la /usr/local/marknest/ 2>&1; echo '--- dpkg ---'; dpkg -l | grep -i marknest"),
    ("service", "systemctl status marknest --no-pager -l 2>&1 | head -40"),
    ("service-enabled", "systemctl is-enabled marknest 2>&1; systemctl is-active marknest 2>&1"),
    ("journal", "journalctl -u marknest --no-pager -n 80 2>&1"),
    ("socket", "ls -la /var/api/ 2>&1"),
    ("user", "id marknest 2>&1; getent group lpadmin 2>&1"),
    ("binary", "file /usr/local/marknest/bin/marknest-server 2>&1; head -c 200 /usr/local/marknest/bin/marknest-server 2>&1 | cat -A | head -5"),
    ("python", "which python3; python3 --version 2>&1; python3 -c 'import sqlite3,zlib;print(\"stdlib ok\")' 2>&1"),
    ("manual-run", "cd /usr/local/marknest && timeout 8 ./bin/marknest-server 2>&1 | head -40"),
    ("cups", "which lpstat lp lpadmin cupsd 2>&1; systemctl is-active cups 2>&1"),
    ("webui", "ls -la /usr/local/marknest/webui* 2>&1; ls -la /usr/local/marknest/data 2>&1"),
    ("proxy-health", "curl -s -m 10 -o /dev/null -w '%{http_code}' --unix-socket /var/api/marknest.sock http://localhost/health 2>&1"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", help="run one command")
    parser.add_argument("--script", help="run a local shell script")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    client = connect()
    try:
        if args.cmd:
            code, out, err = run(client, args.cmd, args.timeout)
            sys.stdout.write("exit=%s\n--- stdout ---\n%s\n--- stderr ---\n%s\n" % (code, out, err))
            return 0

        if args.script:
            with open(args.script, "r", encoding="utf-8") as handle:
                command = handle.read()
            code, out, err = run(client, command, args.timeout)
            sys.stdout.write("exit=%s\n--- stdout ---\n%s\n--- stderr ---\n%s\n" % (code, out, err))
            return 0

        for label, command in DIAGNOSTICS:
            code, out, err = run(client, command, args.timeout)
            sys.stdout.write("\n" + "=" * 70 + "\n")
            sys.stdout.write("### %s (exit=%s)\n" % (label, code))
            sys.stdout.write("=" * 70 + "\n")
            sys.stdout.write(out)
            if err.strip():
                sys.stdout.write("--- stderr ---\n" + err)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
