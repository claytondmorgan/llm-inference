"""PostToolUse hook handler for Read, Bash, and Grep events (T-H1, T-H2).

Reads the hook JSON from stdin, writes a staging markdown file, and
enqueues it for the background worker.  Designed to exit in <500 ms.

Usage (configured in ``.claude/settings.json``)::

    python -m claude_rag.hooks.post_tool_use
"""

from __future__ import annotations

import hashlib
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

# Minimum output length to index for Bash/Grep (skip trivial commands)
_MIN_OUTPUT_LENGTH = 50

# Dedup cache persisted to disk so it survives across hook invocations.
# Each invocation is a separate ``python -m ...`` process, so an in-memory
# dict would be empty every time.  We use a small JSON file instead.
_DEDUP_CACHE_FILENAME = "dedup_cache.json"


def _load_dedup_cache(state_dir: Path) -> dict[str, tuple[str, float]]:
    """Load the dedup cache from disk."""
    cache_file = state_dir / _DEDUP_CACHE_FILENAME
    try:
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return {k: (v[0], v[1]) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_dedup_cache(state_dir: Path, cache: dict[str, tuple[str, float]]) -> None:
    """Persist the dedup cache to disk."""
    cache_file = state_dir / _DEDUP_CACHE_FILENAME
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({k: [h, t] for k, (h, t) in cache.items()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _check_dedup_cache(
    file_path: str, content_hash: str, state_dir: Path, ttl: float = 300.0
) -> bool:
    """Check if a Read event is a duplicate based on content hash and TTL.

    Uses a JSON file on disk so the cache persists across hook process
    invocations.  Expired entries are pruned on every call.

    Args:
        file_path: Absolute path of the file that was read.
        content_hash: SHA-256 hex digest of the file content.
        state_dir: Directory for the cache file.
        ttl: Time-to-live in seconds for cache entries (default 5 min).

    Returns:
        ``True`` if duplicate (skip processing), ``False`` otherwise.
    """
    now = time.time()  # wall-clock time (survives across processes)
    cache = _load_dedup_cache(state_dir)

    # Prune expired entries
    cache = {k: (h, t) for k, (h, t) in cache.items() if (now - t) < ttl}

    is_dup = False
    if file_path in cache:
        prev_hash, prev_time = cache[file_path]
        if prev_hash == content_hash:
            is_dup = True

    cache[file_path] = (content_hash, now)
    _save_dedup_cache(state_dir, cache)
    return is_dup


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
    t0 = time.monotonic()
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    tool_response = event.get("tool_response", "")
    session_id = event.get("session_id", "unknown")

    _component = "hook.post_tool_use"

    # -- hook_fired ------------------------------------------------------------
    _input_summary = tool_input.get("file_path", tool_input.get("command", tool_input.get("pattern", "")))
    log_activity(
        _component, "hook_fired",
        f"PostToolUse fired for {tool_name} tool. Input: {_input_summary}",
        session_id=session_id,
        data={"tool_name": tool_name, "input_summary": str(_input_summary)[:200]},
    )

    config = Config()
    staging_dir = _staging_dir(config)
    staging_path: str | None = None

    # -- Read-event dedup check ------------------------------------------------
    is_dedup = False
    if tool_name == "Read":
        content = tool_response if isinstance(tool_response, str) else json.dumps(tool_response)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        file_path = tool_input.get("file_path", "unknown")
        is_dedup = _check_dedup_cache(file_path, content_hash, config.STATE_DIR)
        if is_dedup:
            latency_ms = int((time.monotonic() - t0) * 1000)
            # -- dedup_hit -----------------------------------------------------
            log_activity(
                _component, "dedup_hit",
                f"Dedup HIT for {file_path} (hash {content_hash[:8]}... matched). Skipping because content unchanged.",
                session_id=session_id,
                data={"file_path": file_path, "content_hash": content_hash[:16], "cache_hit": True},
                duration_ms=latency_ms,
            )
            log_event(
                "hook_read",
                session_id=session_id,
                file_path=file_path,
                latency_ms=latency_ms,
                dedup=True,
            )
            logger.debug("Dedup hit for Read %s — skipping", file_path)
            return
        else:
            # -- dedup_miss ----------------------------------------------------
            log_activity(
                _component, "dedup_miss",
                f"Dedup MISS for {file_path} (new/changed hash {content_hash[:8]}...). Proceeding to staging.",
                session_id=session_id,
                data={"file_path": file_path, "content_hash": content_hash[:16], "cache_hit": False},
            )

    # -- Stage + enqueue -------------------------------------------------------
    if tool_name == "Read":
        staging_path = _write_read_staging(tool_input, tool_response, session_id, staging_dir)
    elif tool_name == "Bash":
        staging_path = _write_bash_staging(tool_input, tool_response, session_id, staging_dir)
    elif tool_name == "Grep":
        staging_path = _write_grep_staging(tool_input, tool_response, session_id, staging_dir)
    else:
        # -- tool_ignored ------------------------------------------------------
        log_activity(
            _component, "tool_ignored",
            f"Ignoring PostToolUse for unhandled tool '{tool_name}'. Only Read/Bash/Grep indexed.",
            session_id=session_id,
            data={"tool_name": tool_name},
        )
        logger.debug("Ignoring PostToolUse for unhandled tool: %s", tool_name)
        return

    if staging_path is None:
        # -- output_too_short --------------------------------------------------
        output = tool_response if isinstance(tool_response, str) else json.dumps(tool_response)
        log_activity(
            _component, "output_too_short",
            f"Skipping {tool_name} event: output {len(output)} chars < minimum {_MIN_OUTPUT_LENGTH}. Too trivial to index.",
            session_id=session_id,
            data={"tool_name": tool_name, "output_length": len(output), "min_length": _MIN_OUTPUT_LENGTH},
        )
        logger.debug("Skipping %s event (output too short)", tool_name)
        return

    # -- staging_written -------------------------------------------------------
    staging_size = Path(staging_path).stat().st_size
    log_activity(
        _component, "staging_written",
        f"Wrote staging file {Path(staging_path).name} ({staging_size} bytes).",
        session_id=session_id,
        data={"staging_path": staging_path, "size_bytes": staging_size},
    )

    queue = HookQueue(config.STATE_DIR / "hook_queue.db")
    try:
        item_id = queue.enqueue(
            event_type=tool_name.lower(),
            payload={"tool_name": tool_name, "tool_input": tool_input},
            session_id=session_id,
            staging_path=staging_path,
        )
    finally:
        queue.close()

    latency_ms = int((time.monotonic() - t0) * 1000)

    # -- item_enqueued ---------------------------------------------------------
    log_activity(
        _component, "item_enqueued",
        f"Enqueued {tool_name.lower()} event as queue item #{item_id}. Hook latency: {latency_ms}ms.",
        session_id=session_id,
        correlation_id=str(item_id),
        data={"tool_name": tool_name, "item_id": item_id, "staging_path": staging_path},
        duration_ms=latency_ms,
    )

    event_type = f"hook_{tool_name.lower()}"
    log_event(
        event_type,
        session_id=session_id,
        file_path=tool_input.get("file_path", tool_input.get("command", "")),
        latency_ms=latency_ms,
        dedup=False,
    )

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
