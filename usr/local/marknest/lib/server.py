"""Unix socket HTTP/1.1 server.

The backend owns ``/var/api/marknest.sock``. The TOS platform reverse proxy
speaks HTTP over that socket on behalf of the iframe frontend, so the server
implements its own accept loop on top of the standard library. The built-in
``http.server`` is not used because it assumes a TCP peer and buffers request
bodies in memory.

Design notes:
* one thread per connection, request pipelining handled sequentially, keep-alive
  and a 30 second idle timeout as required by the platform specification
* a bounded semaphore caps concurrently served connections; excess connections
  receive a structured 503 instead of being dropped
* ``SIGTERM`` triggers a graceful shutdown, after which the socket file is
  removed so that a restart starts from a clean state
"""

import os
import signal
import socket
import stat
import sys
import threading
import time

from .api import api
from .auth import cors_headers
from .config import config
from .errors import BadRequest, MarkNestError
from .http_util import (
    ClientDisconnected,
    Request,
    encode_response,
    parse_request_line,
    read_headers,
    wrap_success,
)
from .logging_setup import get_logger, setup_logging

log = get_logger("server")

_MAX_CONNECTIONS = max(1, config.max_concurrency)

# Statuses that may safely keep the connection open.
_KEEP_ALIVE_SAFE_STATUSES = (200, 204, 401, 405)


class ConnectionHandler(threading.Thread):
    """Serves one client connection until it closes or an error occurs."""

    def __init__(self, connection, semaphore):
        super().__init__(daemon=True)
        self.connection = connection
        self.semaphore = semaphore
        self.name = "marknest-conn"

    def run(self):
        try:
            self._serve()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # pragma: no cover - defensive
            log.error("connection handler failed: %r", exc)
        finally:
            try:
                self.connection.close()
            except OSError:
                pass
            self.semaphore.release()

    def _serve(self):
        connection = self.connection
        connection.settimeout(config.idle_timeout)
        try:
            reader = connection.makefile("rb")
        except OSError:
            return
        try:
            while True:
                try:
                    line = reader.readline(8192)
                except socket.timeout:
                    return
                except OSError:
                    return
                if not line:
                    return
                if line in (b"\r\n", b"\n"):
                    continue

                try:
                    method, target, version = parse_request_line(line)
                    headers = read_headers(reader)
                except MarkNestError as exc:
                    self._write(exc.status, exc.to_payload(), close=True)
                    return
                except ClientDisconnected:
                    return

                request = Request(method, target, version, headers, reader)
                close = not _wants_keep_alive(request)
                started = time.time()

                try:
                    status, payload = api.dispatch(request)
                except MarkNestError as exc:
                    status, payload = exc.status, exc.to_payload()
                    if status >= 500:
                        log.error("%s %s -> %s %s", method, target, status, exc.message)
                    else:
                        log.info("%s %s -> %s %s", method, target, status, exc.message)
                except ClientDisconnected:
                    return
                except Exception as exc:  # pragma: no cover - defensive
                    log.exception("unhandled error for %s %s: %s", method, target, exc)
                    status = 500
                    payload = {"code": 1000, "message": "internal error", "data": None}
                else:
                    elapsed_ms = (time.time() - started) * 1000.0
                    if status == 204 or payload is None:
                        log.info("%s %s -> %s (%.0f ms)", method, target, status, elapsed_ms)
                    else:
                        payload = wrap_success(payload)
                        log.info("%s %s -> %s (%.0f ms)", method, target, status, elapsed_ms)

                if status >= 400 and status not in _KEEP_ALIVE_SAFE_STATUSES:
                    close = True

                try:
                    self._write(status, payload, close=close)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

                try:
                    request.cleanup()
                except Exception:
                    pass

                if close:
                    return
        finally:
            try:
                reader.close()
            except Exception:
                pass

    def _write(self, status, payload, close=False):
        extra = {}
        if status in (204, 401):
            extra.update(cors_headers())
        if close:
            extra["Connection"] = "close"
        else:
            extra["Connection"] = "keep-alive"
            extra["Keep-Alive"] = "timeout=%d" % int(config.idle_timeout)
        self.connection.sendall(encode_response(status, payload, extra_headers=extra))


def _wants_keep_alive(request):
    connection = (request.headers.get("Connection") or "").strip().lower()
    if request.version == "HTTP/1.1":
        return connection != "close"
    return connection == "keep-alive"


class UnixSocketServer:
    """Minimal threaded AF_UNIX HTTP server."""

    def __init__(self, path, backlog=128):
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError("this platform does not provide AF_UNIX sockets")
        self.path = path
        self.backlog = backlog
        self._socket = None
        self._running = False
        self._semaphore = threading.BoundedSemaphore(_MAX_CONNECTIONS)
        self._threads = []

    # ------------------------------------------------------------- life cycle

    def bind(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # A stale socket left behind by a previous run must be removed first.
        if os.path.lexists(self.path):
            try:
                os.unlink(self.path)
                log.info("removed stale socket %s", self.path)
            except OSError as exc:
                raise RuntimeError("cannot remove stale socket %s: %s" % (self.path, exc))

        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.setblocking(False)
        server_socket.bind(self.path)
        server_socket.listen(self.backlog)

        try:
            os.chmod(self.path, stat.S_IMODE(config.socket_mode))
        except OSError as exc:
            log.warning("cannot set mode on %s: %s", self.path, exc)
        self._apply_owner(self.path)

        self._socket = server_socket
        return server_socket

    def _apply_owner(self, path):
        try:
            import pwd

            entry = pwd.getpwnam(config.app_id)
            os.chown(path, entry.pw_uid, entry.pw_gid)
        except Exception:
            # Not running as root, the account does not exist, or not POSIX.
            pass

    def serve_forever(self, poll_interval=0.5):
        if self._socket is None:
            self.bind()
        self._running = True
        socket_ = self._socket
        socket_.settimeout(poll_interval)
        log.info("listening on unix socket %s", self.path)

        while self._running:
            try:
                connection, _ = socket_.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if self._running:
                    log.error("accept failed: %s", exc)
                break

            if not self._semaphore.acquire(blocking=False):
                log.warning("connection limit reached, rejecting a connection")
                try:
                    connection.sendall(
                        encode_response(
                            503,
                            {"code": 1503, "message": "server is busy", "data": None},
                            extra_headers={"Connection": "close"},
                        )
                    )
                except OSError:
                    pass
                try:
                    connection.close()
                except OSError:
                    pass
                continue

            handler = ConnectionHandler(connection, self._semaphore)
            handler.start()
            self._threads = [item for item in self._threads if item.is_alive()]
            self._threads.append(handler)

    def shutdown(self):
        self._running = False
        log.info("shutdown requested")

    def server_close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if os.path.lexists(self.path):
            try:
                os.unlink(self.path)
                log.info("removed socket %s", self.path)
            except OSError:
                pass


def serve_forever():
    """Application entry point used by the systemd unit."""
    from . import __version__

    setup_logging(config.log_level, config.log_dir, config.log_to_file)
    config.ensure_directories()

    log.info("starting MarkNest %s", __version__)
    for key, value in sorted(config.describe().items()):
        log.info("config %s = %s", key, value)

    # A note edited over SMB, or from the File Manager, is invisible to this
    # process until something goes and looks. The sweeper is that something.
    # It is wrapped because an index that cannot start must not stop the
    # service from serving the notes themselves - the files are the storage,
    # and the index is only a cache over them.
    try:
        from . import index as indexer

        indexer.start_sweeper()
    except Exception as exc:  # pragma: no cover - never block startup on this
        log.warning("could not start the index sweeper: %s", exc)

    server = UnixSocketServer(config.socket_path)
    try:
        server.bind()
    except Exception as exc:
        log.error("cannot bind %s: %s", config.socket_path, exc)
        return 1

    def _handle_signal(signum, _frame):
        log.info("received signal %s", signum)
        server.shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):  # pragma: no cover - non main thread
            pass

    try:
        server.serve_forever()
    except Exception as exc:
        log.error("server loop terminated: %s", exc)
        return 1
    finally:
        try:
            from . import index as indexer

            indexer.stop_sweeper()
        except Exception:  # pragma: no cover - shutdown must not raise
            pass
        server.server_close()
        log.info("stopped")
    return 0


def check_environment():
    """Validate the runtime environment; used by ``--check`` and by CI.

    The library is the one thing this application cannot run without: it holds
    the notes, and every endpoint past ``/health`` reads or writes it. It is
    therefore reported as a problem when missing, while the search engine is
    reported as a capability - a library without FTS5 works, just slower.
    """
    from . import __version__
    from . import index as indexer
    from . import library
    from .db import store

    setup_logging(config.log_level, config.log_dir, config.log_to_file)
    config.ensure_directories()
    problems = []

    summary = library.summary()
    root = summary.get("share_root") or ""
    if not root:
        problems.append(
            "the notes shared folder '%s' was not found on any volume "
            "(postinst creates it with ter_share_add)" % config.share_name
        )
    elif not summary.get("readable"):
        problems.append("the notes shared folder is not readable: %s" % root)
    elif not summary.get("writable"):
        problems.append("the notes shared folder is not writable: %s" % root)

    index_ok = False
    try:
        store.count()
        index_ok = True
    except Exception as exc:  # noqa: BLE001
        problems.append("the search index is unusable: %s" % exc)

    stats = store.stats()

    print("MarkNest %s environment check" % __version__)
    print("  app root        : %s" % config.app_root)
    print("  socket          : %s" % config.socket_path)
    print("  share name      : %s" % config.share_name)
    print("  library         : %s" % (root or "(not found)"))
    print(
        "  readable        : %s"
        % ("yes" if summary.get("readable") else "no")
    )
    print(
        "  writable        : %s"
        % ("yes" if summary.get("writable") else "no")
    )
    print("  libraries       : %d user(s)" % int(summary.get("users") or 0))
    print(
        "  search engine   : %s"
        % ("fts5" if store.fts else "scan (FTS5 unavailable; search still works)")
    )
    print(
        "  index           : %s (%d note(s), %d user(s))"
        % ("ok" if index_ok else "FAILED", stats.get("notes", 0), stats.get("users", 0))
    )
    print("  index database  : %s" % config.index_db)
    print("  sweeper         : %s" % ("enabled" if config.scan_enabled else "disabled"))
    print("  auth enforced   : %s" % ("yes" if config.require_auth else "no"))

    # The probes above ran as whoever invoked this check, and the TOS shared
    # folder ACL is evaluated per account. Run as root they all succeed - which
    # is precisely the answer somebody debugging an installation does not want,
    # because the service itself runs as the unprivileged application account
    # and that is the account whose access decides whether the application
    # works. Measured on a real device: this check said "writable: yes" while
    # the application user could not even enter the folder.
    try:
        running_as_root = os.geteuid() == 0
    except AttributeError:  # pragma: no cover - no geteuid off POSIX
        running_as_root = False
    if running_as_root:
        print("  NOTE            : running as root, so the probes above bypass the")
        print("                    shared folder ACL. What the running service")
        print("                    reports on /health is the answer that counts.")

    if problems:
        for item in problems:
            print("  PROBLEM         : %s" % item)
        print("  result          : DEGRADED (%d issue(s))" % len(problems))
        return 1
    print("  result          : OK")
    return 0


def smoke_main(argv=None):
    """Standalone development server used by ``tools/serve_dev.py``."""
    setup_logging("DEBUG", config.log_dir, False)
    config.ensure_directories()
    server = UnixSocketServer(config.socket_path)
    server.bind()
    return server


if __name__ == "__main__":  # pragma: no cover
    sys.exit(serve_forever())
