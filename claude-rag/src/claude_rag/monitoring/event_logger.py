"""Structured event logger for hook and search telemetry.

Hooks and the MCP server call :func:`log_event` to append JSON lines to
``<STATE_DIR>/metrics/events.jsonl``.  The stats server tails this file
to build real-time counters for the dashboard.

Usage from any hook or module::

    from claude_rag.monitoring.event_logger import log_event

    log_event("hook_read", file_path="/foo/bar.py", latency_ms=42, dedup=False)
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_rag.config import Config

logger = logging.getLogger(__name__)

_config = Config()
METRICS_DIR: Path = _config.STATE_DIR / "metrics"

# Thread lock to prevent interleaved writes to the JSONL file.
# Without this, concurrent threads can corrupt lines (partial writes).
_write_lock = threading.Lock()


def log_event(event_type: str, **kwargs: Any) -> None:
    """Append a structured event to the metrics event log.

    The event is a single JSON line with ``type``, ``timestamp``, and any
    additional keyword arguments merged in.  Uses a thread lock to ensure
    atomic writes under concurrent access.

    Args:
        event_type: Event category string.  Conventions:
            ``hook_read``, ``hook_bash``, ``hook_grep``, ``hook_prompt``,
            ``rag_search``, ``enrichment``, ``session_start``,
            ``session_end``.
        **kwargs: Arbitrary key-value pairs included in the event.
    """
    event = {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        **kwargs,
    }
    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        events_file = METRICS_DIR / "events.jsonl"
        with _write_lock:
            with open(events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
    except Exception:
        # Never let metrics recording break a hook or request.
        logger.debug("Failed to write event: %s", event_type, exc_info=True)
