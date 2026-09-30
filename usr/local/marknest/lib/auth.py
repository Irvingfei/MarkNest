"""Platform authentication checks for requests arriving through the TOS proxy.

The TOS platform proxy injects the session into the request. The documented
contract for iframe applications is:

* the frontend reads ``TMSESSNAME`` and ``X-Csrf-Token`` from ``document.cookie``
* it sends ``X-Csrf-Token: <token>`` and, because browsers forbid writing the
  standard ``Cookie`` header from JavaScript, a custom header literally named
  ``Cookie`` containing ``TMSESSNAME=...; X-Csrf-Token=...;``
* the backend rejects the request with ``401`` when the session is missing or
  the two tokens disagree, and the frontend then redirects to the TOS login page

An optional, stricter mode verifies the session against the TOS daemon when
``MARKNEST_VERIFY_URL`` is configured. That check is opt-in because the
verification endpoint is not part of the public app specification.
"""

import http.client
import re
import unicodedata
import urllib.parse

from .config import config
from .errors import AuthRequired, IdentityRequired
from .logging_setup import get_logger

log = get_logger("auth")

SESSION_COOKIE = "TMSESSNAME"
CSRF_COOKIE = "X-Csrf-Token"

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._~+/=\-]{8,256}$")

#: A TOS user name as this application is willing to use it. Deliberately
#: narrower than what the platform might allow: no separators, no leading dot,
#: nothing that could become a path component, and short enough that no
#: filesystem will complain.
_USER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_ALLOWED_HEADERS = "Content-Type, X-Csrf-Token, X-MarkNest-User, Cookie"
_ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS"


def parse_cookie_header(raw):
    """Parse a cookie string into a dictionary without rejecting odd entries."""
    result = {}
    for chunk in (raw or "").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        if key:
            result[key] = value.strip().strip('"')
    return result


def collect_credentials(request):
    """Gather the session token and CSRF token from both header styles."""
    header_token = (request.headers.get("X-Csrf-Token") or "").strip()

    # 1. The custom ``Cookie`` header mandated by the TOS specification.
    custom_cookie = parse_cookie_header(request.headers.get("Cookie") or "")

    # 2. A regular cookie jar, when the proxy forwards it as a real cookie.
    jar = request.cookies()

    session = custom_cookie.get(SESSION_COOKIE) or jar.get(SESSION_COOKIE) or ""
    cookie_token = custom_cookie.get(CSRF_COOKIE) or jar.get(CSRF_COOKIE) or ""
    return session, header_token or cookie_token, cookie_token


def cors_headers():
    """CORS headers required for the platform proxy preflight."""
    return {
        "Access-Control-Allow-Origin": "same-origin",
        "Access-Control-Allow-Methods": _ALLOWED_METHODS,
        "Access-Control-Allow-Headers": _ALLOWED_HEADERS,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin, Access-Control-Request-Headers",
    }


def verify_request(request, *, require=True):
    """Validate the platform credentials. Raises :class:`AuthRequired` on failure."""
    session, token, cookie_token = collect_credentials(request)

    if not require:
        return {"session": session, "token": token, "enforced": False}

    if not session or not token:
        raise AuthRequired("missing platform session credentials")

    if not _SAFE_TOKEN.match(token):
        raise AuthRequired("malformed CSRF token")

    if cookie_token and cookie_token != token:
        raise AuthRequired("CSRF token mismatch")

    verify_url = (config.env_verify_url or "").strip()
    if verify_url and not _verify_remote(verify_url, session, token):
        raise AuthRequired("platform session is no longer valid")

    return {"session": session, "token": token, "enforced": True}


def _verify_remote(url, session, token):
    """Optional session check against the TOS daemon."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        log.warning("ignoring invalid MARKNEST_VERIFY_URL: %s", url)
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    connection_class = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    try:
        connection = connection_class(parsed.hostname, port, timeout=5)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "application/json",
                    "X-Csrf-Token": token,
                    "Cookie": "%s=%s; %s=%s" % (SESSION_COOKIE, session, CSRF_COOKIE, token),
                },
            )
            response = connection.getresponse()
            response.read()
            return response.status < 400
        finally:
            connection.close()
    except (OSError, http.client.HTTPException) as exc:
        log.warning("session verification request failed: %s", exc)
        # Fail open: the proxy already validated the session, and locking the
        # user out on a transient error would be worse than the residual risk.
        return True


# ------------------------------------------------------------------ identity


def _cookie_value(request, name):
    """Read one cookie from either the custom header or the real cookie jar."""
    custom = parse_cookie_header(request.headers.get("Cookie") or "")
    if custom.get(name):
        return custom[name].strip()
    try:
        jar = request.cookies()
    except Exception:  # noqa: BLE001 - a malformed jar is simply "no cookie"
        return ""
    if not jar:
        return ""
    morsel = jar.get(name)
    if morsel is None:
        return ""
    return str(getattr(morsel, "value", morsel)).strip()


def claimed_user(request):
    """The user name this request claims to be, from whichever channel has it.

    Two channels, and the order matters only because one of them was measured to
    be unreliable:

      * the dedicated header, which the WebUI fills in from the cookie it can
        read in its own document;
      * the platform cookie itself.

    The header is checked first because the cookie does **not** survive the
    platform's own proxy. Measured on TOS 7 with a signed-in session: the
    browser holds ``tos_current_username``, the session and CSRF cookies reach
    the application (otherwise authentication would fail before identity is
    even considered), and this one does not - a request through
    ``/v2/proxy/<appid>/`` arrives without it, while the identical request made
    directly against the application's socket carries it fine.

    Neither channel is proof of anything. Both are supplied by the client, so
    they have the same trust standing, and the checks below are about keeping a
    malformed or non-existent name from addressing a directory, not about
    establishing who is asking.
    """
    header_name = config.user_header
    if header_name:
        claimed = (request.headers.get(header_name) or "").strip()
        if claimed:
            return claimed
    return _cookie_value(request, config.user_cookie)


def resolve_identity(request):
    """Return the TOS user this request belongs to, or raise ``IdentityRequired``.

    Every user has their own library, so a request that cannot be attributed to
    a user has nothing to answer from. The platform publishes no identity API to
    an embedded application, but it does publish a convention: its own backend
    services read the ``tos_current_username`` cookie, and the browser's cookies
    reach this service (which is why the session and CSRF cookies arrive here at
    all).

    The cookie is client-supplied, so it is treated as untrusted input. It has
    to match a conservative charset, and it has to resolve to a real system
    account - which is what stops a forged name from addressing a directory that
    merely happens to exist.

    What this does NOT do is *prove* the claim, and that is worth stating
    plainly rather than implying otherwise. A person who already holds a valid
    platform session can point the cookie at another user's name and reach that
    user's notes. It is a property of the platform's model rather than of this
    code: the service runs as a single account, so the operating system cannot
    tell the two apart either. The only mitigation available from inside the
    application is to fail closed on anything that does not look exactly like a
    TOS user name, which is what the checks below do. The limitation is recorded
    in the submission notes.
    """
    name = claimed_user(request)
    if not name:
        raise IdentityRequired("your TOS user could not be determined")

    name = unicodedata.normalize("NFC", name)
    if not _USER_NAME.match(name) or name in (".", ".."):
        log.info("rejected an unusable user name from the cookie")
        raise IdentityRequired("the TOS user name is not usable")

    if config.require_system_user:
        try:
            import pwd
        except ImportError:  # pragma: no cover - the packaging host is Windows
            pwd = None
        if pwd is not None:
            try:
                pwd.getpwnam(name)
            except KeyError:
                log.info("rejected a user name that is not a system account")
                raise IdentityRequired("no such TOS user")
            except OSError as exc:
                log.warning("cannot look up user %s: %s", name, exc)
                raise IdentityRequired("the TOS user could not be verified")

    return name
