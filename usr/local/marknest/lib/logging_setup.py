"""Logging setup.

The log format follows the TOS 7 specification:

    [YYYY-MM-DD HH:MM:SS] [LEVEL] [component] message

systemd journal captures stdout/stderr, so no log file is required by default.
When MARKNEST_LOG_DIR is writable and MARKNEST_LOG_TO_FILE is enabled,
records are additionally appended to ``logs/server.log``.
"""

import logging
import os
import sys
import threading

_CONFIGURED = False
_LOCK = threading.Lock()

_FORMAT = "[%(asctime)s] [%(levelname)s] [%(component)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class _ComponentFilter(logging.Filter):
    """Derives the ``component`` field from the child logger name.

    ``get_logger("cups")`` returns ``marknest.cups``; each record is then
    rendered as ``[INFO] [cups] ...`` without forcing call sites to pass the
    component on every log call.
    """

    _ROOT_NAME = "marknest"

    def filter(self, record):
        name = record.name
        if name == self._ROOT_NAME:
            record.component = "main"
        else:
            record.component = name.split(".")[-1] or "main"
        return True


def setup_logging(level=None, log_dir=None, to_file=False):
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED:
            return logging.getLogger("marknest")

        level_name = (level or os.environ.get("MARKNEST_LOG_LEVEL") or "INFO").upper()
        root_level = _LEVELS.get(level_name, logging.INFO)

        root = logging.getLogger("marknest")
        root.setLevel(root_level)
        root.handlers.clear()
        root.propagate = False

        formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
        component_filter = _ComponentFilter()

        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        stream.addFilter(component_filter)
        root.addHandler(stream)

        resolved_dir = log_dir or os.environ.get("MARKNEST_LOG_DIR")
        if to_file and resolved_dir:
            try:
                os.makedirs(resolved_dir, exist_ok=True)
                path = os.path.join(resolved_dir, "server.log")
                file_handler = logging.FileHandler(path, encoding="utf-8")
                file_handler.setFormatter(formatter)
                file_handler.addFilter(component_filter)
                root.addHandler(file_handler)
            except OSError as exc:  # pragma: no cover - depends on host volume
                root.warning("cannot open log file in %s: %s", resolved_dir, exc)

        _CONFIGURED = True
        return root


def get_logger(component):
    """Return a logger that renders the given component name in each record."""
    return logging.getLogger("marknest").getChild(component)
