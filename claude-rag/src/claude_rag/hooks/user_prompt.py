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
from claude_rag.monitoring.activity_logger import log_activity
from claude_rag.monitoring.event_logger import log_event

logger = logging.getLogger(__name__)


def handle(event: dict) -> None:
    """Process a UserPromptSubmit hook event.

    Writes a staging markdown file with the user's prompt and enqueues it.

    Args:
        event: The full JSON object read from stdin.
    """
    t0 = time.monotonic()
    prompt = event.get("prompt", "")
    session_id = event.get("session_id", "unknown")

    _component = "hook.user_prompt"

    # -- hook_fired ------------------------------------------------------------
    prompt_preview = prompt[:80].replace("\n", " ")
    log_activity(
        _component, "hook_fired",
        f"UserPromptSubmit fired. Prompt: '{prompt_preview}...' ({len(prompt)} chars)",
        session_id=session_id,
        data={"prompt_length": len(prompt), "prompt_preview": prompt_preview},
    )

    if not prompt.strip():
        # -- prompt_empty ------------------------------------------------------
        log_activity(
            _component, "prompt_empty",
            "Ignoring empty prompt. No content to index.",
            session_id=session_id,
        )
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

    # -- staging_written -------------------------------------------------------
    staging_size = staging_path.stat().st_size
    log_activity(
        _component, "staging_written",
        f"Wrote staging file {staging_path.name} ({staging_size} bytes).",
        session_id=session_id,
        data={"staging_path": str(staging_path), "size_bytes": staging_size},
    )

    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        item_id = queue.enqueue(
            event_type="user_prompt",
            payload={"prompt": prompt},
            session_id=session_id,
            staging_path=str(staging_path),
        )
    finally:
        queue.close()

    latency_ms = int((time.monotonic() - t0) * 1000)

    # -- item_enqueued ---------------------------------------------------------
    log_activity(
        _component, "item_enqueued",
        f"Enqueued user_prompt as queue item #{item_id}. Hook latency: {latency_ms}ms.",
        session_id=session_id,
        correlation_id=str(item_id),
        data={"item_id": item_id, "prompt_length": len(prompt)},
        duration_ms=latency_ms,
    )

    log_event(
        "hook_prompt",
        session_id=session_id,
        prompt_length=len(prompt),
    )

    logger.debug("Enqueued user_prompt event -> %s", staging_path)


def main() -> None:
    """Entry point when invoked as ``python -m claude_rag.hooks.user_prompt``."""
    debug_log = Path.home() / ".claude-rag" / "hook_debug.log"
    debug_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = sys.stdin.read()
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"[user_prompt] raw={raw[:200]!r}\n")
        event = json.loads(raw)
        handle(event)
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"[user_prompt] SUCCESS session={event.get('session_id')}\n")
    except Exception as exc:
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"[user_prompt] ERROR: {exc}\n")
        logger.exception("user_prompt hook failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
