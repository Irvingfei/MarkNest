#!/usr/bin/env python3
"""Report per-language field lengths from <appid>.lang.

The TOS submission form rejects a language block when ``name`` exceeds 64,
``descript`` 512, ``important`` 512 or ``release_note`` 2048 characters. This
tool prints the actual counts so a translation can be trimmed before the
validator turns the overflow into a hard failure.

Usage:
    python tools/lang_stats.py
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "marknest"
LANG_PATH = os.path.join(REPO_ROOT, "usr", "local", APP_ID, "%s.lang" % APP_ID)

# field -> (limit, ...)
LIMITS = {
    "name": 64,
    "auth": 128,
    "descript": 512,
    "important": 512,
    "release_note": 2048,
}

# The platform requires every one of these; a missing block is a rejection.
REQUIRED = (
    "zh-cn", "zh-hk", "en-us", "fr-fr", "de-de", "it-it", "es-es",
    "hu-hu", "ja-jp", "ko-kr", "pl-pl", "ru-ru", "tr-tr", "pt-pt",
)


def parse(text):
    sections = {}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^\[([a-z]{2}-[a-z]{2})\]$", stripped)
        if match:
            current = match.group(1)
            sections[current] = {}
            continue
        if current and "=" in stripped:
            key, _, value = stripped.partition("=")
            sections[current][key.strip()] = value.strip().strip('"')
    return sections


def main():
    if not os.path.isfile(LANG_PATH):
        print("language file not found: %s" % LANG_PATH)
        return 1
    with open(LANG_PATH, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8")

    sections = parse(text)
    english = (sections.get("en-us") or {}).get("descript") or ""

    missing = [tag for tag in REQUIRED if tag not in sections]
    print("%-8s %6s %6s %6s %6s  %s" % ("lang", "name", "descr", "impor", "relno", "status"))
    print("-" * 62)
    problems = 0
    for tag in sorted(sections):
        block = sections[tag]
        row = []
        status = "ok"
        for field in ("name", "descript", "important", "release_note"):
            value = block.get(field) or ""
            limit = LIMITS[field]
            row.append(len(value))
            if len(value) > limit:
                status = "OVER(%s>%d)" % (field, limit)
                problems += 1
            if not value and field in ("name", "auth", "descript"):
                status = "EMPTY(%s)" % field
                problems += 1
        # A block whose description is byte-identical to en-us is not a
        # translation, it is the English text parked in a foreign slot. It
        # passes every length and emptiness check, so without this it ships -
        # and an English paragraph inside a Japanese store page is exactly the
        # class of defect the rest of this tooling exists to catch.
        if tag != "en-us" and english and block.get("descript") == english:
            status = "UNTRANSLATED"
            problems += 1
        print(
            "%-8s %6d %6d %6d %6d  %s"
            % (tag, row[0], row[1], row[2], row[3], status)
        )

    print("-" * 62)
    if missing:
        print("missing language blocks: %s" % ", ".join(missing))
        problems += len(missing)
    print("languages: %d, problems: %d" % (len(sections), problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
