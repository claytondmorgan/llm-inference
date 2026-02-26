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

    # Prevent infinite loops — if stop_hook_active, a previous Stop hook
    # blocked and Claude continued.  Let it stop now.
    if stop_hook_active:
        logger.debug("stop_hook_active=True, allowing stop without action")
        return

    # The summary may not be written yet when the Stop hook fires.
    # Wait briefly for it to appear.
    summary_path: str | None = None
    for _ in range(5):
        summary_path = _find_summary(session_id, transcript_path)
        if summary_path:
            break
        time.sleep(1)

    if not summary_path:
        logger.debug("No session summary found for session %s", session_id)
        # Still enqueue the transcript_path for ingestion if available
        if transcript_path and Path(transcript_path).exists():
            config = Config()
            queue = HookQueue(config.STATE_DIR / "hook_queue.db")
            try:
                queue.enqueue(
                    event_type="session_end",
                    payload={"transcript_path": transcript_path},
                    session_id=session_id,
                    staging_path=transcript_path,
                )
            finally:
                queue.close()
            logger.debug("Enqueued transcript for session %s", session_id)
        return

    config = Config()
    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        queue.enqueue(
            event_type="session_end",
            payload={"summary_path": summary_path, "transcript_path": transcript_path},
            session_id=session_id,
            staging_path=summary_path,
        )
    finally:
        queue.close()

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
