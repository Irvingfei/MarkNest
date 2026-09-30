"""HTTP primitives: request parsing, streaming multipart decoding and responses.

Only the standard library is used so that the backend stays dependency free on
the TOS platform. The multipart decoder is memory mapped, which keeps uploads of
several hundred megabytes from being buffered in RAM.
"""

import email.utils
import http.client
import json
import mmap
import os
import re
import socket
import tempfile
import urllib.parse
from http.cookies import SimpleCookie

from .config import config
from .errors import BadRequest, PayloadTooLarge
from .logging_setup import get_logger

log = get_logger("http")

MAX_HEADER_BYTES = 64 * 1024
_FIELD_LIMIT = 256 * 1024

_STATUS_TEXT = {
    200: "OK",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}

_TOKEN_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$")
_DISPOSITION_RE = re.compile(
    r"""([A-Za-z0-9_\-]+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;\s]+))""",
    re.IGNORECASE,
)
_RFC2231_RE = re.compile(r"([A-Za-z0-9_\-]+)\*=\s*([^;]+)", re.IGNORECASE)


class Headers:
    """Case insensitive header container preserving the original spelling."""

    def __init__(self, items=None):
        self._items = []
        self._index = {}
        if items is None:
            return
        source = items.items() if hasattr(items, "items") else items
        for key, value in source:
            self.add(key, value)

    def add(self, key, value):
        self._items.append((key, value))
        self._index.setdefault(key.lower(), []).append(value)

    def get(self, key, default=None):
        values = self._index.get(key.lower())
        return values[-1] if values else default

    def get_all(self, key):
        return list(self._index.get(key.lower(), ()))

    def __contains__(self, key):
        return key.lower() in self._index

    def to_dict(self):
        return {key: self.get_all(key)[-1] for key in {k.lower() for k, _ in self._items}}

    def items(self):
        return list(self._items)


class Request:
    """Parsed HTTP request with lazy, boundary aware body access."""

    def __init__(self, method, target, version, headers, reader):
        self.method = method
        self.target = target
        self.version = version
        self.headers = headers
        self._reader = reader
        self._body_file = None
        self._body_size = 0
        self._consumed = False

        split = urllib.parse.urlsplit(target)
        self.raw_path = split.path or "/"
        self.query_string = split.query
        self.query = urllib.parse.parse_qs(split.query, keep_blank_values=True)

    # -------------------------------------------------------------- accessors

    @property
    def content_type(self):
        return (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()

    @property
    def content_length(self):
        raw = self.headers.get("Content-Length")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            raise BadRequest("invalid Content-Length header")

    def param(self, name, default=None):
        values = self.query.get(name)
        return values[0] if values else default

    def param_int(self, name, default, minimum=None, maximum=None):
        raw = self.param(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise BadRequest("parameter %s must be an integer" % name)
        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value

    def cookies(self):
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return {}
        parsed = SimpleCookie()
        try:
            parsed.load(raw)
        except Exception:
            return {}
        return {key: morsel.value for key, morsel in parsed.items()}

    # ------------------------------------------------------------------ body

    def wants_body(self):
        return self.method in ("POST", "PUT", "PATCH") or self.headers.get("Content-Length") not in (
            None,
            "0",
        )

    def json_body(self, max_bytes=None):
        """Parse the request body as JSON, returning a dictionary.

        A body that is not JSON, or that is too large, is the caller's mistake
        rather than a server fault, so both raise ``BadRequest``/``PayloadTooLarge``
        instead of escaping as a 500. The size cap defaults to the note limit:
        the only JSON this service accepts carries note content, and accepting
        more than a note can hold would let a client spool something enormous
        into a temp file before being told no.

        The cap is enforced twice - once against the declared Content-Length as
        a cheap early exit, and once against what was actually read, because a
        declared length is a claim and not a fact.
        """
        limit = config.max_note_bytes if max_bytes is None else max_bytes
        declared = self.content_length
        if declared is not None and declared > limit:
            raise PayloadTooLarge(
                "the request body is larger than %d MB" % (limit // (1024 * 1024))
            )
        path = self.body_file()
        try:
            with open(path, "rb") as handle:
                raw = handle.read(limit + 1)
        except OSError as exc:
            raise BadRequest("the request body could not be read: %s" % exc)
        if len(raw) > limit:
            raise PayloadTooLarge(
                "the request body is larger than %d MB" % (limit // (1024 * 1024))
            )
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise BadRequest("the request body is not valid JSON")
        if not isinstance(payload, dict):
            raise BadRequest("the request body must be a JSON object")
        return payload

    def body_file(self):
        """Stream the request body into a temporary file and return its path.

        The file is registered for removal through :meth:`cleanup`.
        """
        if self._body_file is not None:
            return self._body_file

        # The transport-level cap is the largest body this service will accept
        # at all, which is an attachment. Per-endpoint limits are applied by the
        # handler afterwards; this one only stops a client from making the
        # server spool something enormous into a temporary file before anyone
        # gets the chance to say no.
        limit = config.max_attachment_bytes
        if self.headers.get("Transfer-Encoding", "").lower().strip() == "chunked":
            path, size = _spool_chunked(self._reader, limit)
        else:
            length = self.content_length
            if not length:
                path, size = _spool_empty()
            else:
                if length > limit:
                    raise PayloadTooLarge(
                        "file exceeds the configured limit of %s MB"
                        % (limit // (1024 * 1024))
                    )
                path, size = _spool_exact(self._reader, length, limit)

        self._body_file = path
        self._body_size = size
        return path

    @property
    def body_size(self):
        return self._body_size

    def multipart_parts(self):
        """Yield :class:`Part` objects for a multipart/form-data body."""
        if self.content_type != "multipart/form-data":
            raise BadRequest("expected multipart/form-data")
        boundary = extract_boundary(self.headers.get("Content-Type") or "")
        if not boundary:
            raise BadRequest("multipart boundary is missing")
        body_path = self.body_file()
        if not self._body_size:
            raise BadRequest("request body is empty")
        return iter_multipart_parts(body_path, boundary, config.tmp_dir)

    def cleanup(self):
        if self._body_file:
            try:
                os.unlink(self._body_file)
            except OSError:
                pass
            self._body_file = None
        if self._consumed:
            return


class Part:
    """A single multipart part, either a form field or an uploaded file."""

    __slots__ = (
        "name",
        "filename",
        "content_type",
        "size",
        "value",
        "path",
        "headers",
        "_owner",
    )

    def __init__(self, name, filename, content_type, headers, owner):
        self.name = name
        self.filename = filename
        self.content_type = content_type
        self.headers = headers
        self.size = 0
        self.value = None
        self.path = None
        self._owner = owner

    @property
    def is_file(self):
        return self.path is not None or self.filename is not None

    def open(self):
        if self.path is None:
            raise BadRequest("part %s is not a file upload" % self.name)
        return open(self.path, "rb")

    def read_header_bytes(self, count=32):
        if self.path is None:
            return b""
        with open(self.path, "rb") as handle:
            return handle.read(count)


# ------------------------------------------------------------------ multipart


def extract_boundary(content_type):
    value = content_type or ""
    if "boundary=" not in value.lower():
        return None
    index = value.lower().index("boundary=")
    raw = value[index + len("boundary=") :].strip()
    if raw.startswith('"'):
        raw = raw[1:]
        end = raw.find('"')
        return raw[:end] if end >= 0 else raw
    return raw.split(";")[0].strip() or None


def _parse_disposition(value):
    """Return ``(name, filename)`` from a Content-Disposition header value."""
    name = None
    filename = None
    for match in _DISPOSITION_RE.finditer(value or ""):
        key = match.group(1).lower()
        raw = match.group(2) if match.group(2) is not None else match.group(3) or ""
        raw = raw.replace("\\\\", "\\").replace('\\"', '"')
        if key == "name":
            name = raw
        elif key == "filename":
            filename = raw
    if filename is None:
        match = _RFC2231_RE.search(value or "")
        if match:
            encoded = match.group(2).strip().strip('"')
            if "''" in encoded:
                _charset, _, encoded = encoded.partition("''")
            filename = urllib.parse.unquote(encoded)
    return name, filename


def _parse_header_block(block):
    headers = Headers()
    for raw in re.split(rb"\r\n|\n", block):
        if not raw.strip():
            continue
        line = raw.decode("utf-8", "replace")
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        headers.add(key.strip(), value.strip())
    return headers


def iter_multipart_parts(body_path, boundary, tmp_dir):
    """Yield every part of a multipart body stored at ``body_path``."""
    delimiter = b"--" + boundary.encode("utf-8")
    with open(body_path, "rb") as handle:
        try:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:
            return
        try:
            yield from _scan_parts(mapped, delimiter, tmp_dir)
        finally:
            mapped.close()


def _scan_parts(mapped, delimiter, tmp_dir):
    """Walk the multipart body once, yielding each part.

    The cursor always sits immediately after a ``--boundary`` token. A trailing
    ``--`` closes the body, ``CRLF`` starts the next part header block, and the
    part payload ends at the ``CRLF--boundary`` that follows it.
    """
    length = len(mapped)
    marker = b"\r\n" + delimiter

    start = mapped.find(delimiter)
    if start == -1:
        raise BadRequest("multipart boundary not found")
    position = start + len(delimiter)

    while position <= length:
        if mapped[position : position + 2] == b"--":
            return
        if mapped[position : position + 2] == b"\r\n":
            position += 2
        elif mapped[position : position + 1] == b"\n":
            position += 1

        header_end = mapped.find(b"\r\n\r\n", position)
        if header_end == -1:
            header_end = mapped.find(b"\n\n", position)
            if header_end == -1:
                raise BadRequest("multipart part header is malformed")
            data_start = header_end + 2
        else:
            data_start = header_end + 4

        headers = _parse_header_block(mapped[position:header_end])
        disposition = headers.get("Content-Disposition") or ""
        name, filename = _parse_disposition(disposition)
        content_type = headers.get("Content-Type") or ""

        next_index = mapped.find(marker, data_start)
        if next_index != -1:
            data_end = next_index
            next_position = next_index + len(marker)
        else:
            # Defensive fallback for bodies that omit the CRLF before the boundary.
            next_index = mapped.find(delimiter, data_start)
            if next_index == -1:
                raise BadRequest("multipart body is truncated")
            data_end = next_index
            next_position = next_index + len(delimiter)

        part = Part(name, filename, content_type, headers, None)
        if filename:
            os.makedirs(tmp_dir, exist_ok=True)
            descriptor, target = tempfile.mkstemp(prefix="part_", dir=tmp_dir)
            written = 0
            chunk = 1024 * 1024
            cursor = data_start
            with os.fdopen(descriptor, "wb") as sink:
                while cursor < data_end:
                    upper = min(cursor + chunk, data_end)
                    block = mapped[cursor:upper]
                    sink.write(block)
                    written += len(block)
                    cursor = upper
            part.path = target
            part.size = written
        else:
            size = data_end - data_start
            if size > _FIELD_LIMIT:
                raise BadRequest("form field %s is too large" % (name or "?"))
            part.value = mapped[data_start:data_end].decode("utf-8", "replace")
            part.size = size

        yield part
        position = next_position


def discard_part(part):
    if part.path:
        try:
            os.unlink(part.path)
        except OSError:
            pass


# ------------------------------------------------------------------- spooling


def _spool_empty():
    descriptor, path = tempfile.mkstemp(prefix="body_", dir=config.tmp_dir)
    os.close(descriptor)
    return path, 0


def _spool_exact(reader, length, limit):
    os.makedirs(config.tmp_dir, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="body_", dir=config.tmp_dir)
    remaining = length
    written = 0
    with os.fdopen(descriptor, "wb") as sink:
        while remaining > 0:
            block = reader.read(min(1024 * 1024, remaining))
            if not block:
                raise BadRequest("request body ended prematurely")
            remaining -= len(block)
            written += len(block)
            if written > limit:
                sink.close()
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise PayloadTooLarge(
                    "file exceeds the configured limit of %s MB" % (limit // (1024 * 1024))
                )
            sink.write(block)
    return path, written


def _spool_chunked(reader, limit):
    os.makedirs(config.tmp_dir, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="body_", dir=config.tmp_dir)
    written = 0
    with os.fdopen(descriptor, "wb") as sink:
        while True:
            line = reader.readline(1024)
            if not line:
                break
            size_field = line.strip().split(b";")[0]
            try:
                size = int(size_field, 16)
            except ValueError:
                raise BadRequest("malformed chunked encoding")
            if size == 0:
                # Consume trailers.
                while True:
                    trailer = reader.readline(1024)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break
            remaining = size
            while remaining > 0:
                block = reader.read(min(1024 * 1024, remaining))
                if not block:
                    raise BadRequest("chunked body ended prematurely")
                remaining -= len(block)
                written += len(block)
                if written > limit:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                    raise PayloadTooLarge(
                        "file exceeds the configured limit of %s MB"
                        % (limit // (1024 * 1024))
                    )
                sink.write(block)
            reader.read(2)  # trailing CRLF
    return path, written


def save_part_to(part, destination):
    """Move a multipart file part onto its final destination path."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if part.path:
        with open(part.path, "rb") as source, open(destination, "wb") as sink:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                sink.write(block)
        discard_part(part)
    else:
        with open(destination, "w", encoding="utf-8") as sink:
            sink.write(part.value or "")
    return destination


# ------------------------------------------------------------------ responses


def wrap_success(payload, message="ok"):
    """Wrap a successful handler result in the unified response envelope.

    Every endpoint returns the same shape::

        {"code": 0, "message": "ok", "data": {...}}

    ``code`` is non-zero for errors, in which case ``message`` carries a human
    readable description.
    """
    return {"code": 0, "message": message, "data": payload}


def encode_response(status, payload, extra_headers=None, body=None):
    """Serialise a response with an accurate ``Content-Length``."""
    headers = Headers()
    headers.add("Date", email.utils.formatdate(usegmt=True))
    headers.add("Server", "marknest/%s" % _server_version())
    headers.add("X-Content-Type-Options", "nosniff")
    headers.add("Cache-Control", "no-store")

    if body is None:
        if payload is None:
            body = b""
            headers.add("Content-Type", "text/plain; charset=utf-8")
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers.add("Content-Type", "application/json; charset=utf-8")
    else:
        headers.add("Content-Type", "application/octet-stream")

    headers.add("Content-Length", str(len(body)))
    if extra_headers:
        for key, value in extra_headers.items():
            headers.add(key, value)

    reason = _STATUS_TEXT.get(status, "OK")
    head = "HTTP/1.1 %d %s\r\n" % (status, reason)
    for key, value in headers.items():
        head += "%s: %s\r\n" % (key, value)
    head += "\r\n"
    return head.encode("ascii", "replace") + body


def _server_version():
    from . import __version__

    return __version__


def parse_request_line(line):
    try:
        text = line.decode("latin-1").rstrip("\r\n")
    except Exception:
        raise BadRequest("unable to decode the request line")
    parts = text.split()
    if len(parts) != 3:
        raise BadRequest("malformed request line")
    method, target, version = parts
    if not _TOKEN_RE.match(method):
        raise BadRequest("malformed HTTP method")
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise BadRequest("unsupported HTTP version")
    return method.upper(), target, version


def read_headers(reader):
    headers = Headers()
    total = 0
    while True:
        raw = reader.readline(MAX_HEADER_BYTES)
        if not raw:
            raise BadRequest("connection closed while reading headers")
        total += len(raw)
        if total > MAX_HEADER_BYTES:
            raise BadRequest("request headers are too large")
        if raw in (b"\r\n", b"\n"):
            break
        text = raw.decode("latin-1").rstrip("\r\n")
        if ":" not in text:
            raise BadRequest("malformed header line")
        key, _, value = text.partition(":")
        if not _TOKEN_RE.match(key.strip()):
            raise BadRequest("malformed header name")
        headers.add(key.strip(), value.strip())
    return headers


class ClientDisconnected(Exception):
    """Raised when the peer closes the socket mid-exchange."""
