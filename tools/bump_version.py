#!/usr/bin/env python3
"""Single source of truth for the application version.

The version literal is needed in several places that cannot import each other:
the Debian control file, the app metadata read by the TOS desktop, the backend
package header used by `/health`, the lifecycle script banner, the cache buster
query strings in the WebUI, and the badge rendered on the page itself. Keeping
them in sync by hand is how a stale `?v=` parameter survives a deploy and the
browser keeps serving the previous stylesheet - which makes a real fix look like
it never shipped - or how the page keeps advertising the previous release.

So: `VERSION` at the repository root is the only place the number is authored.
Every other occurrence is generated from it by this script.

Usage:
    python tools/bump_version.py --bump patch     # 1.0.1 -> 1.0.2, then sync
    python tools/bump_version.py --set 2.0.0      # explicit version, then sync
    python tools/bump_version.py --sync           # rewrite derived files only
    python tools/bump_version.py --check          # verify, non-zero on drift
"""

import argparse
import io
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)

VERSION_FILE = os.path.join(REPO_ROOT, "VERSION")
CONFIG_INI = os.path.join(REPO_ROOT, "usr", "local", "marknest", "config.ini")
BACKEND_INIT = os.path.join(REPO_ROOT, "usr", "local", "marknest", "lib", "__init__.py")
CONTROL = os.path.join(REPO_ROOT, "DEBIAN", "control")
POSTINST = os.path.join(REPO_ROOT, "DEBIAN", "postinst")
INDEX_HTML = os.path.join(REPO_ROOT, "webui", "index.html")

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_version():
    with io.open(VERSION_FILE, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def parse(version):
    match = SEMVER.match(version)
    if not match:
        raise SystemExit("VERSION must be MAJOR.MINOR.PATCH, found %r" % version)
    return tuple(int(part) for part in match.groups())


def bump(version, level):
    major, minor, patch = parse(version)
    if level == "major":
        return "%d.0.0" % (major + 1)
    if level == "minor":
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


# --------------------------------------------------------------------------- #
# Derived writers. Each returns the number of replacements it performed, or
# raises when the anchor it depends on has disappeared - a silent no-op here
# would reintroduce exactly the drift this module exists to prevent.
# --------------------------------------------------------------------------- #

def write_config_ini(version):
    text = io.open(CONFIG_INI, "r", encoding="utf-8").read()
    new, count = re.subn(
        r'("version"\s*:\s*")[^"]*(")', r"\g<1>%s\g<2>" % version, text
    )
    if count != 1:
        raise SystemExit("config.ini: expected exactly one \"version\" key, found %d" % count)
    io.open(CONFIG_INI, "w", encoding="utf-8", newline="\n").write(new)
    return count


def write_backend_init(version):
    text = io.open(BACKEND_INIT, "r", encoding="utf-8").read()
    new, count = re.subn(
        r'^(__version__\s*=\s*")[^"]*(")', r"\g<1>%s\g<2>" % version, text, flags=re.M
    )
    if count != 1:
        raise SystemExit("lib/__init__.py: expected exactly one __version__, found %d" % count)
    io.open(BACKEND_INIT, "w", encoding="utf-8", newline="\n").write(new)
    return count


def write_control(version):
    text = io.open(CONTROL, "r", encoding="utf-8").read()
    new, count = re.subn(r"^(Version:\s*)\S+\s*$", r"\g<1>%s" % version, text, flags=re.M)
    if count != 1:
        raise SystemExit("DEBIAN/control: expected exactly one Version field, found %d" % count)
    io.open(CONTROL, "w", encoding="utf-8", newline="\n").write(new)
    return count


def write_postinst(version):
    text = io.open(POSTINST, "r", encoding="utf-8").read()
    new, count = re.subn(
        r"(Upgrading marknest from version \$2 to )[0-9]+\.[0-9]+\.[0-9]+",
        r"\g<1>%s" % version,
        text,
    )
    if count != 1:
        raise SystemExit("DEBIAN/postinst: upgrade banner not found (%d matches)" % count)
    io.open(POSTINST, "w", encoding="utf-8", newline="\n").write(new)
    return count


def write_index_html(version):
    text = io.open(INDEX_HTML, "r", encoding="utf-8").read()
    new, count = re.subn(r"\?v=[0-9]+\.[0-9]+\.[0-9]+", "?v=%s" % version, text)
    if count < 5:
        raise SystemExit("webui/index.html: only %d cache-buster(s) found" % count)
    io.open(INDEX_HTML, "w", encoding="utf-8", newline="\n").write(new)
    return count


def write_index_badge(version):
    """The version badge the user actually reads on the page.

    It is a *separate* location from the `?v=` cache busters and it is the one
    requirement "the page must show the version" is about, so it gets its own
    writer and its own verification entry: a bump that updates the cache busters
    while leaving the badge stale is exactly the silent drift this module exists
    to prevent.
    """
    text = io.open(INDEX_HTML, "r", encoding="utf-8").read()
    new, count = re.subn(
        r'(id="app-version"[^>]*>\s*v)[0-9]+\.[0-9]+\.[0-9]+',
        r"\g<1>%s" % version,
        text,
    )
    if count != 1:
        raise SystemExit(
            "webui/index.html: expected exactly one #app-version badge, found %d" % count
        )
    io.open(INDEX_HTML, "w", encoding="utf-8", newline="\n").write(new)
    return count


SYNCERS = [
    ("usr/local/marknest/config.ini", write_config_ini),
    ("usr/local/marknest/lib/__init__.py", write_backend_init),
    ("DEBIAN/control", write_control),
    ("DEBIAN/postinst", write_postinst),
    ("webui/index.html (?v=)", write_index_html),
    ("webui/index.html (#app-version)", write_index_badge),
]


# --------------------------------------------------------------------------- #
# Verification: every derived literal must equal VERSION.
# --------------------------------------------------------------------------- #

def collect():
    """Return {label: (found_version, detail)} for every derived location."""
    found = {}

    config = io.open(CONFIG_INI, "r", encoding="utf-8").read()
    match = re.search(r'"version"\s*:\s*"([^"]*)"', config)
    found["usr/local/marknest/config.ini"] = (match.group(1) if match else None, "")

    backend = io.open(BACKEND_INIT, "r", encoding="utf-8").read()
    match = re.search(r'^__version__\s*=\s*"([^"]*)"', backend, flags=re.M)
    found["usr/local/marknest/lib/__init__.py"] = (match.group(1) if match else None, "")

    control = io.open(CONTROL, "r", encoding="utf-8").read()
    match = re.search(r"^Version:\s*(\S+)\s*$", control, flags=re.M)
    found["DEBIAN/control"] = (match.group(1) if match else None, "")

    postinst = io.open(POSTINST, "r", encoding="utf-8").read()
    match = re.search(r"to ([0-9]+\.[0-9]+\.[0-9]+)", postinst)
    found["DEBIAN/postinst"] = (match.group(1) if match else None, "")

    index = io.open(INDEX_HTML, "r", encoding="utf-8").read()
    tags = sorted(set(re.findall(r"\?v=([0-9]+\.[0-9]+\.[0-9]+)", index)))
    found["webui/index.html (?v=)"] = (
        tags[0] if len(tags) == 1 else (None if not tags else ",".join(tags)),
        "%d reference(s)" % len(re.findall(r"\?v=", index)),
    )
    badge = re.search(r'id="app-version"[^>]*>\s*v([0-9]+\.[0-9]+\.[0-9]+)', index)
    found["webui/index.html (#app-version)"] = (
        badge.group(1) if badge else None,
        "badge shown on the page",
    )

    return found


def check(quiet=False):
    version = read_version()
    parse(version)
    drift = []
    for label, (value, detail) in collect().items():
        if value != version:
            drift.append((label, value, detail))
    if not quiet:
        print("VERSION (source of truth): %s" % version)
        for label, (value, detail) in collect().items():
            mark = "OK " if value == version else "BAD"
            print("  [%s] %-42s %s %s" % (mark, label, value, detail))
    for label, value, detail in drift:
        print("  drift: %s carries %r, expected %r %s" % (label, value, version, detail))
    return version, drift


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bump", choices=["major", "minor", "patch"])
    group.add_argument("--set", dest="explicit", metavar="X.Y.Z")
    group.add_argument("--sync", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        _version, drift = check()
        if drift:
            print("\nRESULT: FAILED - run `python tools/bump_version.py --sync`.")
            return 1
        print("\nRESULT: PASSED - every derived version literal matches VERSION.")
        return 0

    current = read_version()
    if args.bump:
        target = bump(current, args.bump)
        io.open(VERSION_FILE, "w", encoding="utf-8", newline="\n").write(target + "\n")
        print("VERSION: %s -> %s" % (current, target))
    elif args.explicit:
        target = args.explicit
        parse(target)
        io.open(VERSION_FILE, "w", encoding="utf-8", newline="\n").write(target + "\n")
        print("VERSION: %s -> %s" % (current, target))
    else:
        target = current
        print("VERSION: %s (--sync)" % target)

    for label, writer in SYNCERS:
        count = writer(target)
        print("  synced %-42s (%d replacement(s))" % (label, count))

    _version, drift = check(quiet=True)
    if drift:
        for label, value, detail in drift:
            print("  STILL DRIFTED: %s -> %r %s" % (label, value, detail))
        return 1
    print("all derived version literals now read %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
