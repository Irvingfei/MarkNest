#!/usr/bin/env python3
"""Deploy MarkNest to the live TOS device and check the installation end to end.

  0. Report the pre-state, including whether the notes share already exists and
     who owns it - the share is created once and never deleted, so a leftover
     from an earlier experiment is the most likely reason a fresh install finds
     itself unable to write.
  1. SFTP the built .deb to /tmp and verify the digest on the far side.
  2. `dpkg -i` it.
  3. Unpack webui.bz2 into /usr/local/marknest/webui the way the TOS app
     framework does (dpkg alone only replaces the archive, so the served tree
     would otherwise stay on the previous release).
  4. Restart and assert version, service state and /health.
  5. Compare every served frontend file against the repository byte for byte.
  6. Run the application's own environment check on the device.
  7. Probe the notes library as the application user: can it, in fact, read and
     write without anyone having granted anything?

Credentials come from PRINT_HOST / PRINT_PORT / PRINT_USER / PRINT_PASS.
"""

import hashlib
import os
import sys

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEB = os.path.join(REPO, "dist", "marknest_x86_64.deb")
REMOTE_DEB = "/tmp/marknest_x86_64.deb"
ROOT = "/usr/local/marknest"
APPID = "marknest"
SERVICE = "marknest.service"
SHARE = "marknest-data"
EXPECTED_VERSION = open(os.path.join(REPO, "VERSION"), encoding="utf-8").read().strip()

from _device import setting  # noqa: E402  (same directory)


def sh(client, cmd, timeout=300, echo=True):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    if echo:
        if o.strip():
            print(o.rstrip())
        if e.strip():
            print("--- stderr ---\n%s" % e.rstrip())
    return code, o, e


def local_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if not os.path.isfile(DEB):
        raise SystemExit("missing build artifact: %s" % DEB)

    digest = local_sha256(DEB)
    print("local deb: %s bytes  sha256=%s" % (os.path.getsize(DEB), digest))

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
        print("\n================ 0. pre-state ================")
        sh(client,
           "echo -n 'installed : '; dpkg -s %s 2>/dev/null | grep -E '^Version' || echo '(not installed)'; "
           "echo '--- the notes share ---'; "
           "ls -ld /Volume*/%s 2>&1; "
           "echo '--- who owns it (the app runs as %s) ---'; "
           "getent passwd %s 2>&1 | head -1 || echo '(app user not created yet)'; "
           "echo '--- web UI directory ---'; ls %s/webui 2>&1 | head -5"
           % (APPID, SHARE, APPID, APPID, ROOT),
           timeout=120)

        print("\n================ 1. upload ================")
        sftp = client.open_sftp()
        try:
            sftp.put(DEB, REMOTE_DEB)
        finally:
            sftp.close()
        _, out, _ = sh(client, "sha256sum %s" % REMOTE_DEB, echo=False)
        remote = out.split()[0] if out.split() else ""
        print("uploaded, digest verified: %s" % (remote == digest))

        print("\n================ 2. dpkg -i ================")
        code, out, _ = sh(client, "dpkg -i %s 2>&1" % REMOTE_DEB, timeout=300)
        print("dpkg exit=%s" % code)

        print("\n================ 3. unpack webui.bz2 ================")
        # postinst already does this; repeating it here is harmless and keeps
        # the step visible in the deploy log. mkdir first, because a plain
        # dpkg -i on a machine that never saw the platform installer leaves the
        # directory absent - which is exactly what happened the first time.
        code, out, _ = sh(
            client,
            "cd %s && mkdir -p webui && tar -xjf webui.bz2 -C webui && "
            "chown -R root:root webui && "
            "chmod -R a+rX webui && find webui -type f | wc -l" % ROOT,
            timeout=120,
        )
        print("unpack exit=%s" % code)

        print("\n================ 4. restart + version/service/health ================")
        sh(client,
           "systemctl restart %s; sleep 4; "
           "echo -n 'is-enabled : '; systemctl is-enabled %s; "
           "echo -n 'is-active  : '; systemctl is-active %s; "
           "echo -n 'NRestarts  : '; systemctl show -p NRestarts --value %s; "
           "echo '--- version markers ---'; "
           "dpkg -s %s 2>/dev/null | grep -E '^Version'; "
           "grep -o '\"version\": *\"[^\"]*\"' %s/config.ini; "
           "grep -o '__version__ *= *\"[^\"]*\"' %s/lib/__init__.py; "
           "grep -o '?v=[0-9.]*' %s/webui/index.html | sort -u; "
           "grep -o 'id=\"app-version\"[^>]*>v[0-9.]*' %s/webui/index.html; "
           "echo '--- /health ---'; "
           "curl -s -m 20 --unix-socket /var/api/%s.sock http://localhost/health"
           % (SERVICE, SERVICE, SERVICE, SERVICE, APPID, ROOT, ROOT, ROOT, ROOT, APPID),
           timeout=180)

        print("\n================ 5. served frontend vs repository ================")
        _, out, _ = sh(client, "cd %s/webui && find . -type f | sort | xargs sha256sum" % ROOT,
                       timeout=120, echo=False)
        remote_files = {}
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                remote_files[parts[1].lstrip("./")] = parts[0]
        bad = 0
        local_dir = os.path.join(REPO, "webui")
        for base, _dirs, files in os.walk(local_dir):
            for name in files:
                path = os.path.join(base, name)
                rel = os.path.relpath(path, local_dir).replace(os.sep, "/")
                if remote_files.get(rel) != local_sha256(path):
                    bad += 1
                    print("  DIFF %s" % rel)
        print("files compared: %d, mismatches: %d" % (len(remote_files), bad))
        print("editor bundle served: %s" % ("js/vendor.editor.js" in remote_files))

        print("\n================ 6. the application's own environment check ================")
        sh(client, "%s/bin/marknest-server --check 2>&1" % ROOT, timeout=180)

        print("\n================ 7. the notes library, as the application user ================")
        # The point of ter_share_add is that the application account can write
        # with nobody having granted anything, so this is measured rather than
        # assumed - and measured as that account, not as root.
        sh(client,
           "SHARE=\"$(ls -d /Volume*/%s 2>/dev/null | head -1)\"; "
           "echo \"share: $SHARE\"; "
           "ls -ld \"$SHARE\" 2>&1; "
           "echo '--- users/ subtree ---'; ls -ld \"$SHARE/users\" 2>&1; "
           "echo '--- write as %s ---'; "
           "su -s /bin/sh %s -c \"mkdir -p $SHARE/users/__probe/notes && "
           "printf '# probe\\n' > $SHARE/users/__probe/notes/p.md && "
           "cat $SHARE/users/__probe/notes/p.md && rm -rf $SHARE/users/__probe\" 2>&1; "
           "echo \"exit=$?\""
           % (SHARE, APPID, APPID),
           timeout=180)

        print("\n================ 8. final state ================")
        sh(client,
           "echo -n 'service   : '; systemctl is-active %s; "
           "echo '--- unit log tail ---'; journalctl -u %s --no-pager -n 12 2>&1 | tail -12"
           % (SERVICE, SERVICE),
           timeout=120)

        client.exec_command("rm -f %s" % REMOTE_DEB)
    finally:
        client.close()

    print("\nexpected version on the device: %s" % EXPECTED_VERSION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
