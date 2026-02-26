"""Structured JSON logging configuration for the Claude Code RAG system.

Provides a :class:`JSONFormatter` that emits one JSON object per log record
and a :func:`configure_logging` helper that wires up the root logger for
the entire application.

Usage::

    from claude_rag.logging_config import configure_logging, get_logger

    configure_logging(level="DEBUG", log_format="json")
    logger = get_logger(__name__)
    logger.info("Ingested file", extra={"source_id": 42, "chunks": 5})
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Logging formatter that outputs structured JSON log entries.

    Each log record is serialised as a single JSON object with the fields:

    * ``timestamp`` -- ISO 8601 UTC timestamp
    * ``level`` -- log level name (e.g. ``"INFO"``)
    * ``logger`` -- logger name (e.g. ``"claude_rag.ingestion.pipeline"``)
    * ``message`` -- the formatted log message
    * ``extra`` -- any additional key/value pairs passed via *extra*
    * ``exception`` -- formatted traceback string (only when ``exc_info`` is set)
    """

    # Keys that are part of the standard LogRecord and should NOT be
    # forwarded into the ``extra`` bucket.
    _BUILTIN_ATTRS: frozenset[str] = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON-encoded string for *record*.

        Args:
            record: The log record to format.

        Returns:
            A single-line JSON string.
        """
        # Build the structured payload.
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Collect user-supplied extra fields.
        extra: dict[str, Any] = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._BUILTIN_ATTRS
        }
        if extra:
            payload["extra"] = extra

        # Include exception info when present.
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return json.dumps(payload, default=str)


_TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"

# Loggers that are excessively chatty at INFO level.
_NOISY_LOGGERS: tuple[str, ...] = (
    "transformers",
    "sentence_transformers",
    "torch",
    "urllib3",
    "httpx",
)


def configure_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """Configure the root logger for the application.

    This function is **idempotent** -- calling it multiple times will not
    add duplicate handlers.  Existing handlers on the root logger are
    removed before new ones are attached.

    Args:
        level: Log level name (e.g. ``"INFO"``, ``"DEBUG"``).
        log_format: Either ``"json"`` for structured JSON output or
            ``"text"`` for a human-friendly single-line format.
        log_file: Optional path to a log file.  When provided a
            :class:`logging.FileHandler` is added in addition to the
            stderr :class:`logging.StreamHandler`.
    """
    root = logging.getLogger()

    # Resolve the level string to a numeric constant.
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # Build the appropriate formatter.
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(_TEXT_FORMAT)

    # Idempotent: remove all existing handlers before attaching new ones.
    root.handlers.clear()

    # Always write to stderr so log output never intermixes with tool
    # data on stdout.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    # Optional file output.
    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Suppress noisy third-party loggers.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a :class:`logging.Logger` for *name*.

    This is a thin convenience wrapper so that application modules can
    write::

        from claude_rag.logging_config import get_logger
        logger = get_logger(__name__)

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
