"""UserPromptSubmit hook handler (T-H3).

Captures every user prompt as an "intent" memory — recording WHAT Claude
was asked to do, which is critical context for future RAG queries.

Usage (configured in ``.claude/settings.json``)::

    python -m claude_rag.hooks.user_prompt
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from claude_rag.config import Config
from claude_rag.hooks.queue import HookQueue

logger = logging.getLogger(__name__)


def handle(event: dict) -> None:
    """Process a UserPromptSubmit hook event.

    Writes a staging markdown file with the user's prompt and enqueues it.

    Args:
        event: The full JSON object read from stdin.
    """
    prompt = event.get("prompt", "")
    session_id = event.get("session_id", "unknown")

    if not prompt.strip():
        logger.debug("Ignoring empty prompt")
        return

    config = Config()
    staging_dir = config.STATE_DIR / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    staging_path = staging_dir / f"prompt_{int(time.time() * 1000)}.md"

    md = (
        f"# User Prompt\n\n"
        f"- Session: {session_id}\n"
        f"- Timestamp: {ts}\n"
        f"- Source: UserPromptSubmit\n"
        f"- Block type: user_intent\n\n"
        f"## Intent\n\n"
        f"{prompt}\n"
    )
    staging_path.write_text(md, encoding="utf-8")

    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        queue.enqueue(
            event_type="user_prompt",
            payload={"prompt": prompt},
            session_id=session_id,
            staging_path=str(staging_path),
        )
    finally:
        queue.close()

    logger.debug("Enqueued user_prompt event -> %s", staging_path)


def main() -> None:
    """Entry point when invoked as ``python -m claude_rag.hooks.user_prompt``."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw)
        handle(event)
    except Exception:
        logger.exception("user_prompt hook failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
