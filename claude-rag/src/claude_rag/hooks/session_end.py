"""Stop hook handler — session summary ingestion (T-H4).

When a Claude Code session ends, this hook locates the AI-generated
session summary and enqueues it for ingestion as a high-value
``session_summary`` chunk.

The summary file lives at::

    ~/.claude/projects/<hash>/<session-id>/session-memory/summary.md

Usage (configured in ``.claude/settings.json``)::

    python -m claude_rag.hooks.session_end
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import time
from pathlib import Path

from claude_rag.config import Config
from claude_rag.hooks.queue import HookQueue
from claude_rag.monitoring.activity_logger import log_activity

logger = logging.getLogger(__name__)


def _find_summary(session_id: str, transcript_path: str | None) -> str | None:
    """Locate the session-memory summary.md for a given session.

    Searches in the same project directory that contains the transcript.

    Args:
        session_id: Claude Code session id.
        transcript_path: Absolute path to the session transcript JSONL.

    Returns:
        Absolute path to ``summary.md`` if found, else ``None``.
    """
    if transcript_path:
        # transcript_path looks like:
        #   ~/.claude/projects/<encoded>/<uuid>.jsonl
        # The summary lives at:
        #   ~/.claude/projects/<encoded>/<uuid>/session-memory/summary.md
        transcript = Path(transcript_path)
        # Try deriving from transcript filename (uuid.jsonl -> uuid/)
        session_dir = transcript.parent / transcript.stem / "session-memory" / "summary.md"
        if session_dir.exists():
            return str(session_dir)

    # Fallback: search by session_id under ~/.claude/projects/
    claude_dir = Path(os.environ.get("USERPROFILE", Path.home())) / ".claude" / "projects"
    pattern = str(claude_dir / "**" / session_id / "session-memory" / "summary.md")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return matches[0]

    return None


def handle(event: dict) -> None:
    """Process a Stop hook event.

    Finds the session summary and enqueues it for ingestion.

    Args:
        event: The full JSON object read from stdin.
    """
    session_id = event.get("session_id", "unknown")
    transcript_path = event.get("transcript_path")
    stop_hook_active = event.get("stop_hook_active", False)

    _component = "hook.session_end"

    # -- hook_fired ------------------------------------------------------------
    log_activity(
        _component, "hook_fired",
        f"Stop hook fired for session {session_id}. Searching for summary...",
        session_id=session_id,
        data={"transcript_path": transcript_path, "stop_hook_active": stop_hook_active},
    )

    # Prevent infinite loops — if stop_hook_active, a previous Stop hook
    # blocked and Claude continued.  Let it stop now.
    if stop_hook_active:
        # -- reentry_skip ------------------------------------------------------
        log_activity(
            _component, "reentry_skip",
            "stop_hook_active=True. Allowing stop to prevent infinite loop.",
            session_id=session_id,
        )
        logger.debug("stop_hook_active=True, allowing stop without action")
        return

    # The summary may not be written yet when the Stop hook fires.
    # Wait briefly for it to appear.
    summary_path: str | None = None
    retries = 0
    for _ in range(5):
        summary_path = _find_summary(session_id, transcript_path)
        if summary_path:
            break
        retries += 1
        time.sleep(1)

    if not summary_path:
        # -- summary_not_found -------------------------------------------------
        log_activity(
            _component, "summary_not_found",
            f"No summary found after {retries} retries. Falling back to transcript.",
            session_id=session_id,
            data={"retries": retries, "transcript_path": transcript_path},
        )
        logger.debug("No session summary found for session %s", session_id)
        # Still enqueue the transcript_path for ingestion if available
        if transcript_path and Path(transcript_path).exists():
            config = Config()
            queue = HookQueue(config.STATE_DIR / "hook_queue.db")
            try:
                item_id = queue.enqueue(
                    event_type="session_end",
                    payload={"transcript_path": transcript_path},
                    session_id=session_id,
                    staging_path=transcript_path,
                )
            finally:
                queue.close()
            # -- item_enqueued (transcript fallback) ---------------------------
            log_activity(
                _component, "item_enqueued",
                f"Enqueued session_end (transcript fallback) as queue item #{item_id}.",
                session_id=session_id,
                correlation_id=str(item_id),
                data={"item_id": item_id, "staging_path": transcript_path, "fallback": True},
            )
            logger.debug("Enqueued transcript for session %s", session_id)
        return

    # -- summary_found ---------------------------------------------------------
    log_activity(
        _component, "summary_found",
        f"Found summary at {summary_path} after {retries} retries.",
        session_id=session_id,
        data={"summary_path": summary_path, "retries": retries},
    )

    config = Config()
    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        item_id = queue.enqueue(
            event_type="session_end",
            payload={"summary_path": summary_path, "transcript_path": transcript_path},
            session_id=session_id,
            staging_path=summary_path,
        )
    finally:
        queue.close()

    # -- item_enqueued ---------------------------------------------------------
    log_activity(
        _component, "item_enqueued",
        f"Enqueued session_end as queue item #{item_id}.",
        session_id=session_id,
        correlation_id=str(item_id),
        data={"item_id": item_id, "summary_path": summary_path},
    )

    logger.debug("Enqueued session summary for session %s -> %s", session_id, summary_path)


def main() -> None:
    """Entry point when invoked as ``python -m claude_rag.hooks.session_end``."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw)
        handle(event)
    except Exception:
        logger.exception("session_end hook failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
