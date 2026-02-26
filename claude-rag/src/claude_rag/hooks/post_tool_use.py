"""PostToolUse hook handler for Read, Bash, and Grep events (T-H1, T-H2).

Reads the hook JSON from stdin, writes a staging markdown file, and
enqueues it for the background worker.  Designed to exit in <500 ms.

Usage (configured in ``.claude/settings.json``)::

    python -m claude_rag.hooks.post_tool_use
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

# Minimum output length to index for Bash/Grep (skip trivial commands)
_MIN_OUTPUT_LENGTH = 50


def _staging_dir(config: Config) -> Path:
    """Return the staging directory, creating it if necessary."""
    d = config.STATE_DIR / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_read_staging(
    tool_input: dict,
    tool_response: dict | str,
    session_id: str,
    staging_dir: Path,
) -> str:
    """Write a staging .md file for a Read tool event.

    Args:
        tool_input: The tool input containing ``file_path`` and optionally
            ``offset``/``limit``.
        tool_response: The file content returned by Read.
        session_id: Claude Code session id.
        staging_dir: Directory to write the staging file.

    Returns:
        Absolute path to the staging file.
    """
    file_path = tool_input.get("file_path", "unknown")
    content = tool_response if isinstance(tool_response, str) else json.dumps(tool_response)
    offset = tool_input.get("offset", "")
    limit = tool_input.get("limit", "")
    line_range = ""
    if offset:
        line_range = f" (lines {offset}"
        if limit:
            line_range += f"-{int(offset) + int(limit)}"
        line_range += ")"

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    slug = Path(file_path).name.replace(" ", "_")
    staging_path = staging_dir / f"read_{slug}_{int(time.time() * 1000)}.md"

    md = (
        f"# File Read: {file_path}{line_range}\n\n"
        f"- Session: {session_id}\n"
        f"- Timestamp: {ts}\n"
        f"- Source: PostToolUse/Read\n\n"
        f"## Content\n\n"
        f"```\n{content}\n```\n"
    )
    staging_path.write_text(md, encoding="utf-8")
    return str(staging_path)


def _write_bash_staging(
    tool_input: dict,
    tool_response: dict | str,
    session_id: str,
    staging_dir: Path,
) -> str | None:
    """Write a staging .md file for a Bash tool event.

    Returns ``None`` if the output is too short to index.
    """
    command = tool_input.get("command", "")
    output = tool_response if isinstance(tool_response, str) else json.dumps(tool_response)

    if len(output) < _MIN_OUTPUT_LENGTH:
        return None

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    staging_path = staging_dir / f"bash_{int(time.time() * 1000)}.md"

    md = (
        f"# Command Execution\n\n"
        f"- Session: {session_id}\n"
        f"- Timestamp: {ts}\n"
        f"- Source: PostToolUse/Bash\n\n"
        f"## Command\n\n"
        f"```bash\n{command}\n```\n\n"
        f"## Output\n\n"
        f"```\n{output}\n```\n"
    )
    staging_path.write_text(md, encoding="utf-8")
    return str(staging_path)


def _write_grep_staging(
    tool_input: dict,
    tool_response: dict | str,
    session_id: str,
    staging_dir: Path,
) -> str | None:
    """Write a staging .md file for a Grep tool event.

    Returns ``None`` if the output is too short to index.
    """
    pattern = tool_input.get("pattern", "")
    path = tool_input.get("path", "")
    output = tool_response if isinstance(tool_response, str) else json.dumps(tool_response)

    if len(output) < _MIN_OUTPUT_LENGTH:
        return None

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    staging_path = staging_dir / f"grep_{int(time.time() * 1000)}.md"

    md = (
        f"# Code Search: `{pattern}`\n\n"
        f"- Session: {session_id}\n"
        f"- Timestamp: {ts}\n"
        f"- Source: PostToolUse/Grep\n"
        f"- Search path: {path}\n\n"
        f"## Results\n\n"
        f"```\n{output}\n```\n"
    )
    staging_path.write_text(md, encoding="utf-8")
    return str(staging_path)


def handle(event: dict) -> None:
    """Process a PostToolUse hook event.

    Args:
        event: The full JSON object read from stdin.
    """
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    tool_response = event.get("tool_response", "")
    session_id = event.get("session_id", "unknown")

    config = Config()
    staging_dir = _staging_dir(config)
    staging_path: str | None = None

    if tool_name == "Read":
        staging_path = _write_read_staging(tool_input, tool_response, session_id, staging_dir)
    elif tool_name == "Bash":
        staging_path = _write_bash_staging(tool_input, tool_response, session_id, staging_dir)
    elif tool_name == "Grep":
        staging_path = _write_grep_staging(tool_input, tool_response, session_id, staging_dir)
    else:
        logger.debug("Ignoring PostToolUse for unhandled tool: %s", tool_name)
        return

    if staging_path is None:
        logger.debug("Skipping %s event (output too short)", tool_name)
        return

    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        queue.enqueue(
            event_type=tool_name.lower(),
            payload={"tool_name": tool_name, "tool_input": tool_input},
            session_id=session_id,
            staging_path=staging_path,
        )
    finally:
        queue.close()

    logger.debug("Enqueued %s event -> %s", tool_name, staging_path)


def main() -> None:
    """Entry point when invoked as ``python -m claude_rag.hooks.post_tool_use``."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw)
        handle(event)
    except Exception:
        # Hooks must not crash Claude Code — log and exit cleanly.
        logger.exception("post_tool_use hook failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
