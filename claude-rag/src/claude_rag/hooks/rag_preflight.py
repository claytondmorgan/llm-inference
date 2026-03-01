#!/usr/bin/env python3
"""RAG System Preflight Check — SessionStart Hook.

Runs automatically at the start of EVERY Claude Code session (including
subagents and agent team members).

Install as a SessionStart hook in ``~/.claude/settings.json``::

    {
      "hooks": {
        "SessionStart": [{
          "hooks": [{
            "type": "command",
            "command": "python -m claude_rag.hooks.rag_preflight",
            "timeout": 10
          }]
        }]
      }
    }

Checks performed:
    1. DB connectivity, schema health, chunk/source stats
    2. MCP server configured (``claude-rag`` in settings)
    3. PostToolUse hooks configured (write side)
    4. Enrichment worker heartbeat
    5. Async queue depth / backlog

Exit codes:
    0 — all checks passed or partial failure (stdout injected as context)
    2 — critical failure (blocks session; remove if too aggressive)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_rag.config import Config
from claude_rag.monitoring.event_logger import log_event

# ─── Configuration ──────────────────────────────────────────────────────────

_config = Config()

METRICS_DIR: Path = _config.STATE_DIR / "metrics"
METRICS_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))
QUEUE_STALE_THRESHOLD_SECONDS = 300  # 5 min → worker is stuck


# ─── Check Functions ────────────────────────────────────────────────────────

def check_database() -> dict[str, Any]:
    """Check DB connectivity, schema, and basic stats."""
    try:
        from claude_rag.db.manager import DatabaseManager

        db = DatabaseManager(_config)
        if not db.test_connection():
            return {"status": "FAIL", "error": "Connection test returned False"}

        conn = db._get_connection()
        cur = conn.cursor()

        # Schema validation
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('memory_sources', 'memory_chunks')
        """)
        tables = {row[0] for row in cur.fetchall()}
        if not {"memory_sources", "memory_chunks"}.issubset(tables):
            cur.close()
            conn.close()
            return {"status": "FAIL", "error": f"Missing tables. Found: {tables}"}

        # pgvector extension
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        if not cur.fetchone():
            cur.close()
            conn.close()
            return {"status": "FAIL", "error": "pgvector extension not installed"}

        # Counts
        source_count = db.get_source_count()
        chunk_count = db.get_chunk_count()

        # Breakdown by block_type
        cur.execute("""
            SELECT block_type, COUNT(*)
            FROM memory_chunks
            GROUP BY block_type
            ORDER BY COUNT(*) DESC
        """)
        chunk_breakdown = {row[0]: row[1] for row in cur.fetchall()}

        # Most recent chunk
        cur.execute("SELECT MAX(created_at) FROM memory_chunks")
        latest = cur.fetchone()[0]
        latest_str = latest.isoformat() if latest else "never"

        # Unenriched queue (chunks awaiting enrichment)
        cur.execute("""
            SELECT COUNT(*) FROM memory_chunks
            WHERE block_type IN ('code', 'raw', 'file_content')
            AND (metadata->>'enriched')::boolean IS NOT TRUE
        """)
        unenriched = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "status": "OK",
            "sources": source_count,
            "chunks": chunk_count,
            "breakdown": chunk_breakdown,
            "latest_chunk": latest_str,
            "unenriched_queue": unenriched,
        }

    except ImportError as exc:
        return {"status": "FAIL", "error": f"Import error: {exc}"}
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def check_hooks_configured() -> dict[str, Any]:
    """Check that PostToolUse and SessionStart hooks are in settings.json."""
    try:
        if not SETTINGS_PATH.exists():
            return {"status": "FAIL", "error": f"No settings.json at {SETTINGS_PATH}"}

        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})

        results: dict[str, str] = {}
        all_ok = True

        # Check PostToolUse hooks for Read
        post_tool = hooks.get("PostToolUse", [])
        if not post_tool:
            results["PostToolUse"] = "MISSING"
            all_ok = False
        else:
            matchers = [h.get("matcher", "all") for h in post_tool]
            if "Read" in matchers or any("Read" in m for m in matchers):
                results["PostToolUse"] = "OK"
            else:
                results["PostToolUse"] = "PARTIAL (no Read matcher)"
                all_ok = False

        # Check SessionStart hook (this script itself)
        session_hooks = hooks.get("SessionStart", [])
        has_preflight = any(
            "rag_preflight" in json.dumps(h)
            for h in session_hooks
        )
        results["SessionStart_preflight"] = "OK" if has_preflight else "NOT_CONFIGURED"

        # Check Stop hook (session summary)
        stop_hooks = hooks.get("Stop", [])
        results["Stop_hook"] = "OK" if stop_hooks else "MISSING"

        # Check UserPromptSubmit
        prompt_hooks = hooks.get("UserPromptSubmit", [])
        results["UserPromptSubmit"] = "OK" if prompt_hooks else "MISSING"

        return {
            "status": "OK" if all_ok else "DEGRADED",
            "hooks": results,
        }

    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def check_mcp_server() -> dict[str, Any]:
    """Check that the MCP server is configured in Claude Code settings."""
    try:
        if not SETTINGS_PATH.exists():
            return {"status": "FAIL", "error": "No settings.json found"}

        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        mcp_servers = settings.get("mcpServers", {})

        rag_server = (
            mcp_servers.get("claude-rag")
            or mcp_servers.get("rag")
            or mcp_servers.get("claude_rag")
        )
        if rag_server:
            return {
                "status": "CONFIGURED",
                "method": "stdio",
                "command": rag_server.get("command", "unknown"),
                "note": "stdio MCP servers start on demand",
            }

        return {
            "status": "FAIL",
            "error": "No 'claude-rag' MCP server in settings.json",
        }

    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def check_enrichment_worker() -> dict[str, Any]:
    """Check if the enrichment background worker is running."""
    try:
        heartbeat_file = METRICS_DIR / "enrichment_heartbeat.json"
        if heartbeat_file.exists():
            heartbeat = json.loads(heartbeat_file.read_text())
            last_beat = datetime.fromisoformat(heartbeat.get("timestamp", "2000-01-01"))
            age_seconds = (datetime.now() - last_beat).total_seconds()

            if age_seconds < 60:
                return {
                    "status": "OK",
                    "last_heartbeat": f"{age_seconds:.0f}s ago",
                    "processed_last_hour": heartbeat.get("processed_last_hour", "unknown"),
                }
            elif age_seconds < QUEUE_STALE_THRESHOLD_SECONDS:
                return {"status": "SLOW", "last_heartbeat": f"{age_seconds:.0f}s ago"}
            else:
                return {"status": "STALE", "last_heartbeat": f"{age_seconds:.0f}s ago"}

        return {
            "status": "UNKNOWN",
            "note": "No heartbeat file found. Worker may not be running.",
        }

    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)}


def check_queue_depth() -> dict[str, Any]:
    """Check the async processing queue for backlog."""
    try:
        from claude_rag.hooks.queue import HookQueue

        queue_path = _config.STATE_DIR / "hook_queue.db"
        if not queue_path.exists():
            return {"status": "OK", "pending": 0, "note": "No queue DB yet"}

        queue = HookQueue(queue_path)
        try:
            stats = queue.stats()
            pending = stats.get("pending", 0)
            processing = stats.get("processing", 0)
            done = stats.get("done", 0)
            errors = stats.get("error", 0)

            return {
                "status": "OK" if pending < 50 else "BACKLOG",
                "pending": pending,
                "processing": processing,
                "done": done,
                "errors": errors,
            }
        finally:
            queue.close()

    except Exception as exc:
        return {"status": "UNKNOWN", "note": str(exc)}


# ─── Metrics Recording ─────────────────────────────────────────────────────

def record_session_metrics(results: dict[str, Any]) -> None:
    """Write preflight results to metrics file for dashboard consumption."""
    try:
        session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
        transcript_path = os.environ.get("CLAUDE_TRANSCRIPT_PATH", "")

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "transcript_path": transcript_path,
            "preflight_results": results,
        }

        # Append to session log
        sessions_log = METRICS_DIR / "sessions.jsonl"
        with open(sessions_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics) + "\n")

        # Write latest status for dashboard
        latest_file = METRICS_DIR / "latest_preflight.json"
        latest_file.write_text(json.dumps(metrics, indent=2))

        # Also record as an event for the stats server
        log_event("session_start", session_id=session_id, results=results)

    except Exception:
        pass  # Don't fail the hook if metrics recording fails


# ─── Main ───────────────────────────────────────────────────────────────────

def run_preflight() -> dict[str, Any]:
    """Run all preflight checks and return results dict."""
    start = time.time()

    results = {
        "database": check_database(),
        "hooks": check_hooks_configured(),
        "mcp_server": check_mcp_server(),
        "enrichment": check_enrichment_worker(),
        "queue": check_queue_depth(),
    }

    results["elapsed_ms"] = int((time.time() - start) * 1000)
    return results


def format_context(results: dict[str, Any]) -> str:
    """Build the context string injected into Claude's session via stdout."""
    elapsed_ms = results.get("elapsed_ms", 0)

    # Determine overall status
    statuses = [
        v.get("status", "UNKNOWN")
        for k, v in results.items()
        if isinstance(v, dict) and "status" in v
    ]
    if all(s in ("OK", "CONFIGURED") for s in statuses):
        overall = "RAG SYSTEM FULLY OPERATIONAL"
    elif any(s == "FAIL" for s in statuses):
        overall = "RAG SYSTEM DEGRADED — some checks failed"
    else:
        overall = "RAG SYSTEM PARTIAL — some checks inconclusive"

    db = results["database"]
    hooks = results["hooks"]
    mcp = results["mcp_server"]
    queue = results["queue"]

    lines: list[str] = []
    lines.append(f"[RAG PREFLIGHT] {overall} ({elapsed_ms}ms)")
    lines.append("")

    # Database
    if db["status"] == "OK":
        lines.append(f"  DB: {db['sources']} files indexed, {db['chunks']} chunks")
        if db.get("breakdown"):
            parts = [f"{k}={v}" for k, v in sorted(db["breakdown"].items())]
            lines.append(f"      Layers: {', '.join(parts)}")
        lines.append(f"      Latest: {db['latest_chunk']}")
        if db.get("unenriched_queue", 0) > 0:
            lines.append(f"      {db['unenriched_queue']} chunks awaiting enrichment")
    else:
        lines.append(f"  DB: {db.get('error', 'unavailable')}")

    # Write side (hooks)
    if hooks["status"] == "OK":
        lines.append("  WRITE: All hooks configured")
    else:
        hook_details = hooks.get("hooks", {})
        lines.append(f"  WRITE: Hook status: {json.dumps(hook_details)}")

    # Read side (MCP)
    if mcp["status"] in ("OK", "CONFIGURED"):
        lines.append(f"  READ: MCP server {mcp['status'].lower()} ({mcp.get('method', 'stdio')})")
        lines.append("        Use rag_search tool BEFORE reading files directly")
    else:
        lines.append(f"  READ: {mcp.get('error', 'unavailable')}")
        lines.append("        RAG search unavailable, fall back to direct file reads")

    # Queue
    pending = queue.get("pending", 0)
    if isinstance(pending, int) and pending > 20:
        lines.append(f"  QUEUE: {pending} items pending — enrichment may be behind")

    lines.append("")
    lines.append("  Run 'python -m claude_rag preflight' for full diagnostic details.")

    return "\n".join(lines)


def main() -> None:
    """Entry point for the SessionStart hook."""
    results = run_preflight()
    record_session_metrics(results)
    output = format_context(results)
    print(output)

    # Always exit 0 so context gets injected even on partial failure.
    sys.exit(0)


if __name__ == "__main__":
    main()
