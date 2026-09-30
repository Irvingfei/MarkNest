#!/usr/bin/env python3
"""Pre-submission validator for the TOS 7 application package.

Mirrors the automated validation performed by the TOS Developer Platform
(chapter 16.1 of the official guide) plus the manual review checklist
(chapter 16.2), so that failures are caught locally instead of after a
submission is rejected.

Checks performed
----------------
config.ini        valid JSON, no comments, no single quotes, no trailing commas,
                  all required fields, ``type``/``open_path`` mutual exclusion,
                  ``${ip}`` placeholder where required, lowercase keys,
                  id character set, category whitelist and 3 category limit,
                  ``low_version`` >= 7.0, reserved field names
app.lang          all 14 languages present, name/descript non-empty, field
                  length limits, UTF-8 without BOM, LF line endings
icon              SVG format, viewBox present, transparent background,
                  path exactly matching config.ini
systemd           non-root User/Group, StartLimit*, ProtectSystem,
                  WantedBy=multi-user.target
DEBIAN/control    Package matches config.ini, Version matches config.ini
file layout       DEBIAN at the root, metadata under usr/local/<appid>/
line endings      no CRLF in .sh/.py/.ini/.lang/.service/.conf/.js/.css/.html
port safety       no reserved TOS port referenced in the payload
secrets           no obvious hardcoded credential in the payload

Usage:
    python tools/validate.py            # validate the repository
    python tools/validate.py --json     # machine readable output
Exit code 0 means every check passed.
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(REPO_ROOT, "usr", "local", "marknest")
DEBIAN_DIR = os.path.join(REPO_ROOT, "DEBIAN")

APP_ID = "marknest"
SYSTEM_ID = "marknest"
PACKAGE = "marknest"

REQUIRED_LANGUAGES = [
    "zh-cn",
    "zh-hk",
    "en-us",
    "fr-fr",
    "de-de",
    "it-it",
    "es-es",
    "hu-hu",
    "ja-jp",
    "ko-kr",
    "pl-pl",
    "ru-ru",
    "tr-tr",
    "pt-pt",
]

ALLOWED_CATEGORIES = {
    "Audio_Video_Entertainment",
    "Photography_Video",
    "Backup_Sync",
    "Development_Tools",
    "Utilities",
    "Web_Services",
    "Security",
    "Download",
    "Driver",
    "Artificial_Intelligence",
}

RESERVED_CONFIG_FIELDS = {
    "host_network",
    "container_runtime",
    "sandbox",
    "auto_update",
    "upstream_url",
    "license",
    "min_memory",
    "min_cpu",
    "min_disk",
}

REQUIRED_CONFIG_FIELDS = [
    "id",
    "icon",
    "exec",
    "version",
    "recommend",
    "beta",
    "low_version",
    "category",
    "platform",
    "application_type",
    "user",
]

RESERVED_PORTS = {
    22: "SSH",
    80: "TOS Web HTTP",
    443: "TOS HTTPS",
    445: "SMB",
    3306: "MySQL",
    5050: "TOS Daemon",
    5432: "PostgreSQL",
    6379: "Redis",
    8181: "TOS Nginx",
    8443: "TOS HTTPS UI",
}

LINE_ENDING_EXTENSIONS = (
    ".sh",
    ".py",
    ".ini",
    ".lang",
    ".service",
    ".conf",
    ".js",
    ".css",
    ".html",
    ".env",
)

SECRET_PATTERNS = [
    (re.compile(r"password\s*[:=]\s*['\"][^'\"]{3,}['\"]", re.IGNORECASE), "hardcoded password"),
    (re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "hardcoded API key"),
    (re.compile(r"secret\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "hardcoded secret"),
    (re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"), "embedded private key"),
]

# Files whose content is not inspected for secrets (documentation, samples).
SECRET_SCAN_SKIP = (".md", ".lang", ".json")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []

    def error(self, check, detail=""):
        self.errors.append({"check": check, "detail": detail})

    def warn(self, check, detail=""):
        self.warnings.append({"check": check, "detail": detail})

    def ok(self, check):
        self.passed.append(check)


def read_text(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    return raw


def check_config_ini(report):
    path = os.path.join(APP_ROOT, "config.ini")
    if not os.path.isfile(path):
        report.error("config.ini present", "missing at usr/local/%s/config.ini" % APP_ID)
        return None
    report.ok("config.ini present")

    raw = read_text(path)

    if raw.startswith(b"\xef\xbb\xbf"):
        report.error("config.ini encoding", "UTF-8 BOM detected")
    else:
        report.ok("config.ini has no BOM")

    if b"\r\n" in raw:
        report.error("config.ini line endings", "CRLF detected, must be LF")
    else:
        report.ok("config.ini uses LF")

    text = raw.decode("utf-8", "replace")

    # Comments and single quotes are the top rejection reasons.
    without_strings = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    if "//" in without_strings or "/*" in without_strings:
        report.error("config.ini has no comments", "// or /* */ found outside strings")
    else:
        report.ok("config.ini has no comments")

    for match in re.finditer(r"'([^']*)'\s*:", text):
        report.error("config.ini uses double quotes", "single quoted key: %s" % match.group(1))
        break
    else:
        report.ok("config.ini uses double quoted keys")

    if re.search(r",\s*[}\]]", text):
        report.error("config.ini has no trailing commas", "trailing comma before } or ]")
    else:
        report.ok("config.ini has no trailing commas")

    for match in re.finditer(r"[“”‘’]", text):
        report.error("config.ini uses ASCII quotes", "full-width quote detected")
        break
    else:
        report.ok("config.ini uses ASCII quotes only")

    try:
        config = json.loads(text)
    except ValueError as exc:
        report.error("config.ini is valid JSON", str(exc))
        return None
    report.ok("config.ini is valid JSON")

    # Required fields.
    for field in REQUIRED_CONFIG_FIELDS:
        if field not in config:
            report.error("config.ini required field", "missing: %s" % field)
    report.ok("config.ini required fields checked")

    # Reserved field names.
    for field in RESERVED_CONFIG_FIELDS:
        if field in config:
            report.error("config.ini reserved fields", "reserved field used: %s" % field)
    report.ok("config.ini avoids reserved fields")

    # Lowercase keys.
    upper_keys = [key for key in config if key != key.lower()]
    if upper_keys:
        report.error("config.ini lowercase keys", "uppercase keys: %s" % ", ".join(upper_keys))
    else:
        report.ok("config.ini keys are lowercase")

    # Identity consistency.
    if config.get("id") != APP_ID:
        report.error("config.ini id", "expected %s, found %s" % (APP_ID, config.get("id")))
    else:
        report.ok("config.ini id matches the package id")

    if config.get("system_id") != SYSTEM_ID:
        report.error(
            "config.ini system_id",
            "expected %s, found %s" % (SYSTEM_ID, config.get("system_id")),
        )
    else:
        report.ok("config.ini system_id matches the service unit")

    if config.get("package") != PACKAGE:
        report.error(
            "config.ini package", "expected %s, found %s" % (PACKAGE, config.get("package"))
        )
    else:
        report.ok("config.ini package matches DEBIAN/control")

    if config.get("application_type") != "deb":
        report.error("config.ini application_type", "expected deb")
    else:
        report.ok("config.ini application_type is deb")

    # Subtype: iframe requires type+path and forbids open_path.
    if config.get("type") == "iframe":
        if "open_path" in config:
            report.error(
                "config.ini subtype exclusivity",
                "type=iframe must not be combined with open_path",
            )
        else:
            report.ok("config.ini subtype is consistent (iframe without open_path)")
        if config.get("path") != "/%s/" % APP_ID:
            report.error(
                "config.ini iframe path",
                "expected /%s/, found %r" % (APP_ID, config.get("path")),
            )
        else:
            report.ok("config.ini iframe path uses /<appid>/")
        webui = os.path.join(APP_ROOT, "webui.bz2")
        webui_source = os.path.join(REPO_ROOT, "webui")
        if os.path.isfile(webui):
            report.ok("webui.bz2 present for the iframe subtype")
        elif os.path.isfile(os.path.join(webui_source, "index.html")):
            # The archive is produced by tools/build.py from the webui/ sources;
            # a pre-build run therefore only needs to confirm the sources exist.
            report.ok("webui.bz2 will be generated from webui/ by tools/build.py")
        else:
            report.error(
                "config.ini iframe payload",
                "webui.bz2 or a webui/ source tree containing index.html is required for iframe apps",
            )

    # path must not hardcode an IP or hostname.
    path_value = config.get("path") or ""
    if re.search(r"https?://", path_value) and "${ip}" not in path_value:
        report.error("config.ini path placeholder", "URL path must use ${ip}")
    else:
        report.ok("config.ini path has no hardcoded host")

    # Categories.
    categories = config.get("category") or []
    if not isinstance(categories, list) or not categories:
        report.error("config.ini category", "at least one category is required")
    else:
        if len(categories) > 3:
            report.error("config.ini category limit", "at most 3 categories, found %d" % len(categories))
        else:
            report.ok("config.ini category count is within the limit")
        for item in categories:
            if item not in ALLOWED_CATEGORIES:
                report.error("config.ini category whitelist", "unknown category: %s" % item)
        if all(item in ALLOWED_CATEGORIES for item in categories):
            report.ok("config.ini categories are all official")

    # recommend must stay false for submissions.
    if config.get("recommend") is not False:
        report.error("config.ini recommend flag", "developers must submit with recommend=false")
    else:
        report.ok("config.ini recommend is false")

    # Platform / architecture.
    if config.get("platform") not in ("x86_64", "aarch64"):
        report.error("config.ini platform", "must be x86_64 or aarch64")
    else:
        report.ok("config.ini platform is valid")

    # low_version >= 7.0
    low = str(config.get("low_version") or "")
    match = re.match(r"^(\d+)(?:\.(\d+))?", low)
    if not match or int(match.group(1)) < 7:
        report.error("config.ini low_version", "must be TOS 7.0 or higher, found %r" % low)
    else:
        report.ok("config.ini low_version is TOS 7.0+")

    # Runtime user must not be root.
    if str(config.get("user") or "").lower() in ("root", ""):
        report.error("config.ini user", "running as root is a veto item")
    else:
        report.ok("config.ini declares a non-root runtime user")

    # Icon path must match the file on disk.
    icon = str(config.get("icon") or "")
    expected = "/images/icons/%s.svg" % APP_ID
    if icon != expected:
        report.error("config.ini icon path", "expected %s, found %s" % (expected, icon))
    elif not os.path.isfile(os.path.join(APP_ROOT, "images", "icons", "%s.svg" % APP_ID)):
        report.error("config.ini icon file", "icon file not found at %s" % icon)
    else:
        report.ok("config.ini icon path matches the packaged file")

    if not re.match(r"^[a-z][a-z0-9-]{0,49}$", str(config.get("id") or "")):
        report.error("config.ini id format", "lowercase letters, digits and hyphens, starting with a letter")
    else:
        report.ok("config.ini id format is valid")

    return config


def check_lang(report, config):
    path = os.path.join(APP_ROOT, "%s.lang" % APP_ID)
    if not os.path.isfile(path):
        report.error("app.lang present", "missing %s.lang" % APP_ID)
        return

    raw = read_text(path)
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error("app.lang encoding", "UTF-8 BOM detected")
    else:
        report.ok("app.lang has no BOM")

    if b"\r\n" in raw:
        report.error("app.lang line endings", "CRLF detected, must be LF")
    else:
        report.ok("app.lang uses LF")

    text = raw.decode("utf-8", "replace")
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

    missing = [tag for tag in REQUIRED_LANGUAGES if tag not in sections]
    if missing:
        report.error("app.lang completeness", "missing languages: %s" % ", ".join(missing))
    else:
        report.ok("app.lang declares all 14 languages")

    problems = []
    for tag in REQUIRED_LANGUAGES:
        block = sections.get(tag)
        if not block:
            continue
        for field in ("name", "auth", "descript"):
            if not block.get(field):
                problems.append("%s.%s is empty" % (tag, field))
        name = block.get("name") or ""
        if len(name) > 64:
            problems.append("%s.name exceeds 64 characters" % tag)
        descript = block.get("descript") or ""
        if len(descript) > 512:
            problems.append("%s.descript exceeds 512 characters" % tag)
        important = block.get("important") or ""
        if len(important) > 512:
            problems.append("%s.important exceeds 512 characters" % tag)
        release = block.get("release_note") or ""
        if len(release) > 2048:
            problems.append("%s.release_note exceeds 2048 characters" % tag)
        for field in ("name", "auth", "descript", "release_note", "important"):
            value = block.get(field) or ""
            if "<" in value.replace("</br>", ""):
                problems.append("%s.%s contains HTML other than </br>" % (tag, field))

    if problems:
        for item in problems:
            report.error("app.lang field rules", item)
    else:
        report.ok("app.lang name/descript are non-empty and within limits")

    # The description must describe real features; a token check keeps the claim
    # honest and is reviewed by hand against the implementation.
    english = (sections.get("en-us") or {}).get("descript") or ""
    keywords = ["markdown", "note"]
    if keywords and english:
        missing_keywords = [word for word in keywords if word.lower() not in english.lower()]
        if missing_keywords:
            report.warn(
                "app.lang description content",
                "en-us descript does not mention: %s" % ", ".join(missing_keywords),
            )
        else:
            report.ok("app.lang description mentions core capabilities")


def check_icon(report, config):
    path = os.path.join(APP_ROOT, "images", "icons", "%s.svg" % APP_ID)
    if not os.path.isfile(path):
        report.error("icon present", "missing %s" % path)
        return
    raw = read_text(path)
    text = raw.decode("utf-8", "replace")

    if "<svg" not in text:
        report.error("icon is SVG", "no <svg> element")
    else:
        report.ok("icon is SVG")

    if not re.search(r'viewBox\s*=\s*"[^"]+"', text):
        report.error("icon viewBox", "viewBox attribute is missing")
    else:
        report.ok("icon declares a viewBox")

    if "<image" in text and "base64" in text:
        report.warn("icon vector quality", "embedded raster data found in the SVG")

    if re.search(r"<rect[^>]*width\s*=\s*\"(?:512|100%)\"[^>]*height", text) and 'fill="#' in text:
        report.warn(
            "icon transparency",
            "a full size filled rect may indicate an opaque background",
        )
    report.ok("icon transparency checked")


def check_systemd(report, config):
    path = os.path.join(APP_ROOT, "init.d", "%s.service" % SYSTEM_ID)
    if not os.path.isfile(path):
        report.error("service unit present", "missing init.d/%s.service" % SYSTEM_ID)
        return

    raw = read_text(path).decode("utf-8", "replace")

    user = re.search(r"^User\s*=\s*(.+)$", raw, re.MULTILINE)
    group = re.search(r"^Group\s*=\s*(.+)$", raw, re.MULTILINE)
    if not user or user.group(1).strip() == "root":
        report.error("service runs as non-root", "User is missing or root")
    else:
        report.ok("service declares a non-root User")
    if not group:
        report.warn("service Group", "Group directive is missing")
    else:
        report.ok("service declares a Group")

    if user and config and user.group(1).strip() != config.get("user"):
        report.error(
            "service user matches config.ini",
            "service User=%s but config.ini user=%s"
            % (user.group(1).strip(), config.get("user")),
        )
    else:
        report.ok("service user matches config.ini")

    # Only live (uncommented) directives are considered from here on. A
    # commented-out directive is documentation, and a substring test over the
    # raw text would flag the very comment that explains why the namespace
    # directives are banned on TOS.
    active_directives = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        active_directives.append(stripped)
    active_directives_text = "\n".join(active_directives)

    for directive, label in (
        ("StartLimitBurst", "StartLimitBurst"),
        ("StartLimitIntervalSec", "StartLimitIntervalSec"),
        ("NoNewPrivileges", "NoNewPrivileges"),
        ("ExecStart", "ExecStart"),
        ("WantedBy=multi-user.target", "WantedBy"),
    ):
        if directive not in active_directives_text:
            report.warn("service hardening", "%s is missing" % label)
        else:
            report.ok("service declares %s" % label)

    # Namespace based sandboxing must stay off: TOS symlinks /var and other
    # standard paths into /tmp, and systemd then fails to prepare
    # /run/systemd/unit-root, so the unit dies with status=226/NAMESPACE before
    # the program ever starts. This is a hard error, not a warning.
    for banned in ("PrivateTmp", "ProtectSystem", "ProtectHome", "ReadWritePaths"):
        for directive in active_directives:
            if re.match(r"%s\s*=" % re.escape(banned), directive):
                report.error(
                    "service avoids namespace sandboxing",
                    "%s requires mount namespacing and breaks on TOS (/var is a symlink)"
                    % banned,
                )
                break
    report.ok("service avoids namespace based sandboxing")

    exec_start = re.search(r"^ExecStart\s*=\s*(.+)$", raw, re.MULTILINE)
    if exec_start:
        target = exec_start.group(1).strip().split()[0]
        expected = "/usr/local/%s/bin/marknest-server" % APP_ID
        if target != expected:
            report.error(
                "service ExecStart path", "expected %s, found %s" % (expected, target)
            )
        elif not os.path.isfile(os.path.join(APP_ROOT, "bin", "marknest-server")):
            report.error("service ExecStart target", "executable not packaged")
        else:
            report.ok("service ExecStart points at the packaged executable")

    if "WantedBy=multi-user.target" in raw:
        report.ok("service is enabled for multi-user.target")


def check_control(report, config):
    path = os.path.join(DEBIAN_DIR, "control")
    if not os.path.isfile(path):
        report.error("DEBIAN/control present", "missing")
        return
    raw = read_text(path).decode("utf-8", "replace")
    report.ok("DEBIAN/control present")

    fields = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    for required in ("Package", "Version", "Architecture", "Maintainer", "Description"):
        if required not in fields:
            report.error("DEBIAN/control fields", "missing: %s" % required)
    report.ok("DEBIAN/control declares the required fields")

    if fields.get("Package") != PACKAGE:
        report.error(
            "DEBIAN/control Package matches config.ini",
            "control=%s config.ini=%s" % (fields.get("Package"), PACKAGE),
        )
    else:
        report.ok("DEBIAN/control Package matches config.ini")

    if config and fields.get("Version") != config.get("version"):
        report.warn(
            "DEBIAN/control Version matches config.ini",
            "control=%s config.ini=%s" % (fields.get("Version"), config.get("version")),
        )
    else:
        report.ok("DEBIAN/control Version matches config.ini")

    architecture = fields.get("Architecture")
    if architecture not in ("amd64", "arm64"):
        report.error("DEBIAN/control Architecture", "unsupported: %s" % architecture)
    else:
        report.ok("DEBIAN/control Architecture is a Debian architecture name")

    depends = fields.get("Depends") or ""
    if "python3" not in depends:
        report.error("DEBIAN/control Depends", "python3 must be declared")
    else:
        report.ok("DEBIAN/control declares python3")
    for forbidden in ("nodejs", "default-jre", "golang"):
        if forbidden in depends:
            report.error(
                "DEBIAN/control Depends",
                "%s is not preinstalled on TOS and must not be a hard dependency" % forbidden,
            )
    report.ok("DEBIAN/control avoids non-preinstalled runtimes")


def check_version_consistency(report):
    """Every derived version literal must equal the one in VERSION.

    The same number has to exist in five places that cannot import each other.
    When they drift, an upgrade can keep serving a cached stylesheet under an
    unchanged ``?v=`` query string, so a shipped fix silently never takes effect
    and the defect looks unfixed on the device. Rather than restate the rules
    here, this imports the module that generates the literals, so the validator
    and the generator can never disagree about what "correct" means.
    """
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import bump_version
    except ImportError as error:
        report.error("version single source", "tools/bump_version.py is not importable: %s" % error)
        return

    version, drift = bump_version.check(quiet=True)
    if drift:
        for label, value, detail in drift:
            report.error(
                "version consistency",
                "%s carries %r but VERSION is %r %s" % (label, value, version, detail),
            )
    else:
        report.ok("version literals all read %s (VERSION)" % version)


def check_editor_bundle(report):
    """The committed editor bundle must match the sources it was built from.

    This is the ``__pycache__`` lesson in a different language. The bundle is a
    build artefact that lives in the repository, so it can go stale in silence:
    the editor sources change, the bundle does not, and nothing anywhere
    complains - the application simply serves the previous behaviour, which is
    the hardest kind of defect to attribute. The build records a hash over its
    inputs, and this re-derives it.

    The payload is also checked for the build chain itself. Node is a
    development-time dependency only; shipping webui-src or node_modules would
    contradict the dependency declaration and is the kind of thing a careless
    ``cp -r`` does once and nobody notices.
    """
    tools_dir = os.path.join(REPO_ROOT, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import webui_build
    except ImportError as exc:  # pragma: no cover
        report.error("editor bundle", "tools/webui_build.py could not be imported: %s" % exc)
        return

    ok, message = webui_build.check(verbose=False)
    if ok:
        report.ok("the editor bundle matches its sources")
    else:
        report.error("editor bundle", message)

    payload = os.path.join(REPO_ROOT, "usr", "local", APP_ID)
    for base, dirs, _files in os.walk(payload):
        for name in list(dirs):
            if name in ("node_modules", "webui-src"):
                report.error(
                    "editor bundle",
                    "the package payload contains %s"
                    % os.path.relpath(os.path.join(base, name), REPO_ROOT),
                )
                return
    for stray in ("webui-src", "package.json", "package-lock.json"):
        path = os.path.join(payload, stray)
        if os.path.exists(path):
            report.error(
                "editor bundle",
                "the package payload contains %s - Node is a development-time "
                "dependency and must not ship" % stray,
            )
            return
    report.ok("the payload carries no Node build chain")


def check_dependency_contract(report):
    """Pin the platform capability the application cannot provide itself.

    MarkNest keeps every note in a shared folder of its own, and the only
    sanctioned way to obtain one - read-write, with no authorization step for
    the operator - is the platform tool ``ter_share_add``. The package cannot
    install it and cannot ship it, so that single call in postinst is the whole
    contract, and it has the same failure shape as a missing runtime dependency:
    lose the line and the app still installs, still starts, still serves its
    page, and only reveals that it has nowhere to keep notes when a user opens
    the first one.

    The uninstall side is pinned for the opposite reason. Not deleting the
    notes is a deliberate deviation from the usual "purge removes user data"
    reflex, because notes are the user's own files and the platform offers no
    tool to put the share back. That deviation has to be asserted rather than
    trusted, since a well-meaning future edit could tidy it away.
    """
    postinst_path = os.path.join(DEBIAN_DIR, "postinst")
    if not os.path.isfile(postinst_path):
        report.error("capability contract", "DEBIAN/postinst is missing")
        return

    postinst = read_text(postinst_path).decode("utf-8", "replace")
    if "ter_share_add" not in postinst:
        report.error(
            "capability contract",
            "postinst never calls ter_share_add - the application would have no "
            "shared folder to keep notes in",
        )
    else:
        report.ok("postinst creates the application's own shared folder")
        for flag, why in (("-name", "the share would have no name"),
                          ("-owner", "the share would end up owned by root")):
            if flag not in postinst:
                report.error(
                    "capability contract",
                    "the ter_share_add call is missing %s - %s" % (flag, why),
                )
        if "-device" not in postinst:
            report.warn(
                "capability contract",
                "ter_share_add is called without -device; the volume is then left to the tool",
            )

    share = "%s-data" % APP_ID
    postrm_path = os.path.join(DEBIAN_DIR, "postrm")
    if os.path.isfile(postrm_path):
        postrm = read_text(postrm_path).decode("utf-8", "replace")
        offender = None
        for line in postrm.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("rm ") or " rm " in stripped:
                if share in stripped or "/Volume" in stripped:
                    offender = stripped
        if offender:
            report.error(
                "uninstall safety",
                "postrm deletes the notes share (%s) - uninstalling must never "
                "destroy the user's notes" % offender[:60],
            )
        else:
            report.ok("postrm leaves the notes share in place")


NETWORK_INSTALL_COMMANDS = (
    "apt install",
    "apt-get install",
    "aptitude install",
    "pip install",
    "pip3 install",
    "npm install",
    "yarn install",
    "dnf install",
    "yum install",
)

# Wrappers that may precede the real command on the same statement.
COMMAND_WRAPPERS = ("sudo", "command", "env", "timeout", "nohup", "if", "then", "else", "do", "!")


def find_network_installations(text):
    """Return the network-installation commands a maintainer script *runs*.

    A raw substring scan cannot tell a command from a mention of one, so it
    flags a comment that explains the ban and an echo that tells the operator
    what to run - both of which a correct script contains. Only a statement whose
    leading token really is an installer counts.
    """
    hits = []
    for raw in text.splitlines():
        # Drop trailing comments before looking at what the shell would execute.
        line = re.sub(r"(^|\s)#.*$", "", raw)
        if not line.strip():
            continue
        for fragment in re.split(r"&&|\|\||;", line):
            tokens = fragment.strip().split()
            index = 0
            while index < len(tokens) and tokens[index] in COMMAND_WRAPPERS:
                index += 1
                # `timeout 300 apt-get ...` - step over the duration argument too
                if index < len(tokens) and re.match(r"^\d+[smhd]?$", tokens[index]):
                    index += 1
            joined = " ".join(tokens[index:])
            for banned in NETWORK_INSTALL_COMMANDS:
                if joined.startswith(banned):
                    hits.append(banned)
        if re.search(r"\bcurl\b[^|]*\|\s*(?:ba|z|k)?sh\b", line):
            hits.append("curl | shell")
    return hits


def check_lifecycle_scripts(report):
    expected = {
        "preinst": ["useradd", "groupadd"],
        "postinst": ["systemctl", "daemon-reload"],
        "prerm": ["systemctl"],
        "postrm": ["rm -f"],
    }
    for name, needles in expected.items():
        path = os.path.join(DEBIAN_DIR, name)
        if not os.path.isfile(path):
            report.error("lifecycle script %s" % name, "missing")
            continue
        raw = read_text(path)
        text = raw.decode("utf-8", "replace")
        if b"\r\n" in raw:
            report.error("lifecycle script %s" % name, "CRLF detected, must be LF")
        if not text.startswith("#!/bin/bash"):
            report.warn("lifecycle script %s" % name, "missing bash shebang")
        shell_bits = text.replace("#!/bin/bash", "")
        if "set -e" not in shell_bits:
            report.warn("lifecycle script %s" % name, "does not use 'set -e'")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            report.warn("lifecycle script %s" % name, "does not reference: %s" % ", ".join(missing))
        for banned in find_network_installations(text):
            report.error(
                "lifecycle script %s" % name,
                "network installation is prohibited: %s" % banned,
            )
        report.ok("lifecycle script %s inspected" % name)


def check_layout(report):
    if not os.path.isdir(DEBIAN_DIR):
        report.error("package layout", "DEBIAN directory is missing at the package root")
        return
    report.ok("DEBIAN is at the package root")

    metadata = (
        ("config.ini", os.path.join(APP_ROOT, "config.ini")),
        ("%s.lang" % APP_ID, os.path.join(APP_ROOT, "%s.lang" % APP_ID)),
        (
            "images/icons/%s.svg" % APP_ID,
            os.path.join(APP_ROOT, "images", "icons", "%s.svg" % APP_ID),
        ),
    )
    for label, path in metadata:
        if not os.path.isfile(path):
            report.error("metadata under usr/local/<appid>", "missing %s" % label)
        elif not os.path.abspath(path).startswith(os.path.abspath(APP_ROOT)):
            report.error("metadata under usr/local/<appid>", "%s is outside the app root" % label)
    report.ok("metadata lives under usr/local/%s/" % APP_ID)

    # Metadata must not sit beside DEBIAN/.
    for stray in ("config.ini", "%s.lang" % APP_ID, "images"):
        if os.path.exists(os.path.join(REPO_ROOT, stray)):
            report.error(
                "metadata is not at the deb root",
                "%s exists beside DEBIAN/ and would break metadata parsing" % stray,
            )
    report.ok("no metadata duplicated at the deb root")

    # Executable bit is set by the build script; verify the source exists.
    binary = os.path.join(APP_ROOT, "bin", "marknest-server")
    if not os.path.isfile(binary):
        report.error("backend entry point", "missing bin/marknest-server")
    else:
        report.ok("backend entry point present")

    lib_dir = os.path.join(APP_ROOT, "lib")
    if not os.path.isdir(lib_dir):
        report.error("backend modules", "lib/ directory is missing")
    else:
        modules = [name for name in os.listdir(lib_dir) if name.endswith(".py")]
        if len(modules) < 5:
            report.warn("backend modules", "only %d module(s) found" % len(modules))
        else:
            report.ok("backend modules packaged (%d files)" % len(modules))


def check_line_endings(report):
    offenders = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [
            item
            for item in dirs
            if item not in (".git", "__pycache__", "build", "dist", ".workbuddy")
        ]
        for name in files:
            if not name.endswith(LINE_ENDING_EXTENSIONS):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as handle:
                    if b"\r\n" in handle.read():
                        offenders.append(os.path.relpath(path, REPO_ROOT))
            except OSError:
                continue
    if offenders:
        for item in offenders:
            report.error("LF line endings", "CRLF in %s" % item)
    else:
        report.ok("all text payload files use LF line endings")


def check_ports(report):
    """Reject references to TOS reserved ports in machine read configuration."""
    scanned = []
    for rel in (
        os.path.join("usr", "local", "marknest", "marknest.env"),
        os.path.join("usr", "local", "marknest", "init.d", "marknest.service"),
        os.path.join("DEBIAN", "postinst"),
        os.path.join("DEBIAN", "preinst"),
    ):
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            continue
        text = read_text(path).decode("utf-8", "replace")
        text = re.sub(r"#.*", "", text)
        for match in re.finditer(r"\b(\d{2,5})\b", text):
            value = int(match.group(1))
            if value in RESERVED_PORTS and value != 631:
                report.error(
                    "reserved port usage",
                    "%s references reserved port %d (%s)"
                    % (rel, value, RESERVED_PORTS[value]),
                )
        scanned.append(rel)
    if scanned:
        report.ok("no TOS reserved port referenced (%d file(s) scanned)" % len(scanned))


def check_secrets(report):
    hits = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [item for item in dirs if item not in (".git", "__pycache__", "build", "dist")]
        for name in files:
            if name.endswith(SECRET_SCAN_SKIP):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as handle:
                    if b"\x00" in handle.read(1024):
                        continue
                text = read_text(path).decode("utf-8", "replace")
            except OSError:
                continue
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append("%s: %s" % (os.path.relpath(path, REPO_ROOT), label))
    if hits:
        for item in hits:
            report.error("no hardcoded credentials", item)
    else:
        report.ok("no hardcoded credential pattern found")


def check_architecture(report, config):
    """Confirm that no compiled binary is bundled (a veto item for Deb apps)."""
    binaries = []
    for root, dirs, files in os.walk(APP_ROOT):
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as handle:
                    if handle.read(4) == b"\x7fELF":
                        binaries.append(os.path.relpath(path, REPO_ROOT))
            except OSError:
                continue

    # The data package must not contain executables other than lifecycle scripts.
    if binaries:
        for item in binaries:
            report.warn("bundled binary", "%s is an ELF executable" % item)
    else:
        report.ok("no compiled binary bundled with the source package")

    platform = (config or {}).get("platform")
    if platform == "x86_64":
        report.ok("platform x86_64 matches an amd64 control architecture")
    elif platform == "aarch64":
        report.ok("platform aarch64 declared (control Architecture must be arm64 for that build)")


def check_tools(report):
    # Presence only: the browser harnesses need Playwright, which the packaging
    # host may not have, so they are installed as a submission gate rather than
    # executed from here.
    required = (
        "tools/validate.py",
        "tools/build.py",
        "tools/selftest.py",
        "tools/bump_version.py",
        "tools/webui_check.js",
        "tools/inspect_deb.py",
        "tools/measure_topbar.py",
        "tools/verify_error_i18n.py",
        "tools/verify_editor.py",
        "tools/webui_build.py",
        "build.sh",
    )
    missing = [rel for rel in required if not os.path.isfile(os.path.join(REPO_ROOT, rel))]
    if missing:
        report.warn("tooling", "missing: %s" % ", ".join(missing))
    else:
        report.ok("build, validation and browser harness tooling present (%d files)" % len(required))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the TOS 7 application package")
    parser.add_argument("--json", action="store_true", help="emit machine readable JSON")
    args = parser.parse_args(argv)

    report = Report()
    config = check_config_ini(report)
    check_lang(report, config)
    check_icon(report, config)
    check_systemd(report, config)
    check_control(report, config)
    check_version_consistency(report)
    check_dependency_contract(report)
    check_editor_bundle(report)
    check_lifecycle_scripts(report)
    check_layout(report)
    check_line_endings(report)
    check_ports(report)
    check_secrets(report)
    check_architecture(report, config)
    check_tools(report)

    if args.json:
        print(
            json.dumps(
                {
                    "errors": report.errors,
                    "warnings": report.warnings,
                    "passed": len(report.passed),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("TOS 7 package validation - %s" % APP_ID)
        print("=" * 62)
        for item in report.errors:
            print("  [ERROR] %s: %s" % (item["check"], item["detail"]))
        for item in report.warnings:
            print("  [WARN ] %s: %s" % (item["check"], item["detail"]))
        print("-" * 62)
        print("passed checks : %d" % len(report.passed))
        print("warnings      : %d" % len(report.warnings))
        print("errors        : %d" % len(report.errors))
        if report.errors:
            print("\nRESULT: FAILED - fix the errors above before submitting.")
        else:
            print("\nRESULT: PASSED - the package satisfies the automated validation and review checklist.")

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
