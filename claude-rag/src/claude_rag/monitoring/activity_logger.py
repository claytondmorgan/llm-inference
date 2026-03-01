"""Human-readable activity logger for RAG hooks and pipeline.

Appends rich JSONL entries to ``~/.claude-rag/metrics/activity.jsonl`` —
separate from the sparse dashboard metrics in ``events.jsonl``.  Every
entry includes a plain-English ``description`` explaining *what* happened
and *why*, plus structured ``data`` for programmatic filtering.

Usage from any hook or module::

    from claude_rag.monitoring.activity_logger import log_activity

    log_activity(
        component="hook.post_tool_use",
        action="dedup_hit",
        description="Dedup cache HIT for /src/main.py (hash a3b2c1... matched).",
        session_id="abc-123",
        correlation_id="47",
        data={"file_path": "/src/main.py", "cache_hit": True},
        duration_ms=3.0,
    )
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
_ACTIVITY_DIR: Path = _config.STATE_DIR / "metrics"
_ACTIVITY_FILE = "activity.jsonl"

# Thread lock — same pattern as event_logger.py
_write_lock = threading.Lock()


def log_activity(
    component: str,
    action: str,
    description: str,
    *,
    level: str = "info",
    session_id: str | None = None,
    correlation_id: str | None = None,
    data: dict[str, Any] | None = None,
    duration_ms: float | None = None,
) -> None:
    """Append a human-readable activity entry to ``activity.jsonl``.

    Uses the same error-swallowing pattern as :func:`log_event` — this
    function **never** raises, so it is safe to call from hooks that must
    not crash Claude Code.

    Args:
        component: Dotted path identifying the subsystem, e.g.
            ``"hook.post_tool_use"``, ``"worker"``, ``"pipeline.parse"``.
        action: Snake_case verb describing the event, e.g.
            ``"hook_fired"``, ``"dedup_hit"``, ``"item_enqueued"``.
        description: Full English sentence explaining what happened and why.
        level: Log severity — ``"debug"``, ``"info"``, ``"warn"``, or
            ``"error"``.  Defaults to ``"info"``.
        session_id: Claude Code session identifier, if available.
        correlation_id: Queue item ID that traces a single event from
            enqueue through pipeline completion.
        data: Arbitrary structured data for programmatic filtering.
        duration_ms: Wall-clock duration of the logged operation.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "level": level,
        "component": component,
        "action": action,
        "description": description,
    }

    if session_id is not None:
        entry["session_id"] = session_id
    if correlation_id is not None:
        entry["correlation_id"] = correlation_id
    if data is not None:
        entry["data"] = data
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 1)

    try:
        _ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
        activity_file = _ACTIVITY_DIR / _ACTIVITY_FILE
        with _write_lock:
            with open(activity_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception:
        # Never let activity logging break a hook or request.
        logger.debug("Failed to write activity: %s/%s", component, action, exc_info=True)
