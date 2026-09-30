#!/usr/bin/env python3
"""Build the WebUI editor bundle, and record what it was built from.

Why this is a separate tool from build.py
-----------------------------------------
``tools/build.py`` packages the application and must never invoke Node: the
package declares ``Depends: python3, systemd`` and that has to stay true, both
for the review and because a device that cannot reach an npm registry must still
be able to install the result. So the bundle is built here, on a development
machine, and the artefact is committed under ``webui/js/``.

Why it writes a source hash
---------------------------
This is the ``__pycache__`` lesson applied to a JavaScript artefact. A committed
build output silently going stale is exactly the failure that once made a
released fix look like it had never shipped: the sources change, the bundle does
not, and nothing complains. ``tools/validate.py`` re-derives the hash below and
refuses the submission when it no longer matches, which turns "somebody forgot
to rebuild" from an invisible drift into a failed check.

Usage:
    python tools/webui_build.py            # build, then write the marker
    python tools/webui_build.py --check    # verify only, no build
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "webui-src")
EDITOR_DIR = os.path.join(SRC_DIR, "editor")
BUNDLE = os.path.join(REPO_ROOT, "webui", "js", "vendor.editor.js")
MARKER = BUNDLE + ".sha256"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hash():
    """A hash over every source file the bundle is built from.

    Path and content both go in, sorted, so that a rename and an edit are
    equally visible and the answer does not depend on directory order.
    """
    digest = hashlib.sha256()
    if not os.path.isdir(EDITOR_DIR):
        return ""
    entries = []
    for base, dirs, files in os.walk(EDITOR_DIR):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__")]
        for name in files:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, SRC_DIR).replace(os.sep, "/")
            entries.append((rel, sha256_file(path)))
    for rel, value in sorted(entries):
        digest.update(("%s:%s\n" % (rel, value)).encode("utf-8"))
    # package.json decides which libraries are in the bundle, so a dependency
    # change is a change to the build inputs even though no editor source moved.
    package = os.path.join(SRC_DIR, "package.json")
    if os.path.isfile(package):
        digest.update(("package.json:%s\n" % sha256_file(package)).encode("utf-8"))
    return digest.hexdigest()


def read_marker():
    if not os.path.isfile(MARKER):
        return {}
    try:
        with open(MARKER, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def write_marker():
    payload = {
        "bundle_sha256": sha256_file(BUNDLE),
        "source_sha256": source_hash(),
    }
    with open(MARKER, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def check(verbose=True):
    """Return ``(ok, message)``. Used by validate.py as a submission gate."""
    if not os.path.isfile(BUNDLE):
        return False, "webui/js/vendor.editor.js is missing; run tools/webui_build.py"
    marker = read_marker()
    if not marker:
        return False, "webui/js/vendor.editor.js.sha256 is missing; run tools/webui_build.py"
    if marker.get("bundle_sha256") != sha256_file(BUNDLE):
        return False, "the editor bundle does not match its recorded hash"
    current = source_hash()
    if marker.get("source_sha256") != current:
        return False, (
            "the editor sources changed after the bundle was built; "
            "run tools/webui_build.py"
        )
    if verbose:
        print("editor bundle: %s (%d bytes)" % (sha256_file(BUNDLE)[:16], os.path.getsize(BUNDLE)))
        print("source hash  : %s" % current[:16])
    return True, "the editor bundle matches its sources"


def build():
    if not os.path.isdir(SRC_DIR):
        raise SystemExit("webui-src/ is missing")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise SystemExit("npm is required to build the editor bundle")
    env = dict(os.environ)
    # Reproducibility: the artefact is compared by hash, so anything npm might
    # otherwise vary per machine is pinned off.
    env["npm_config_audit"] = "false"
    env["npm_config_fund"] = "false"
    if not os.path.isdir(os.path.join(SRC_DIR, "node_modules")):
        print("installing editor dependencies ...")
        result = subprocess.run([npm, "install"], cwd=SRC_DIR, env=env)
        if result.returncode != 0:
            raise SystemExit("npm install failed")
    print("building the editor bundle ...")
    result = subprocess.run([npm, "run", "build"], cwd=SRC_DIR, env=env)
    if result.returncode != 0:
        raise SystemExit("the editor build failed")
    if not os.path.isfile(BUNDLE):
        raise SystemExit("the build reported success but produced no bundle")
    return write_marker()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify only")
    args = parser.parse_args(argv)

    if args.check:
        ok, message = check()
        print(("OK   " if ok else "FAIL ") + message)
        return 0 if ok else 1

    payload = build()
    print("bundle sha256: %s" % payload["bundle_sha256"])
    print("source sha256: %s" % payload["source_sha256"])
    print("wrote %s" % os.path.relpath(MARKER, REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
