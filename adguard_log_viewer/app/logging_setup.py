"""Logging configuration.

DNS query content is sensitive. The application therefore never writes domain
names or client addresses to its own log at ``info`` level or above; anything
that touches query content goes through :func:`query_logger` and is emitted at
``debug`` level only.
"""

from __future__ import annotations

import logging
import sys

_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
    "critical": logging.CRITICAL,
}


def setup_logging(level: str = "info") -> None:
    """Install a single stdout handler with a compact, greppable format."""
    resolved = _LEVELS.get(level.lower(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved)

    # uvicorn installs its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # Access logs would contain query strings with domain filters in them.
    logging.getLogger("uvicorn.access").setLevel(
        logging.INFO if resolved <= logging.DEBUG else logging.WARNING
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def query_logger(name: str) -> logging.Logger:
    """Logger for messages that may contain DNS query content.

    Callers must only use ``debug`` on the returned logger.
    """
    return logging.getLogger(f"query.{name}")
