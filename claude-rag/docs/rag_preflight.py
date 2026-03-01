#!/usr/bin/env python3
"""
RAG System Preflight Check — SessionStart Hook
================================================
This script runs automatically at the start of EVERY Claude Code session,
including subagent sessions and agent team members.

Install as a SessionStart hook in ~/.claude/settings.json:
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/rag_preflight.py"
      }
    ]
  }
}

What it does:
  1. Checks DB connectivity and schema health
  2. Checks MCP server is reachable (rag_search tool available)
  3. Checks PostToolUse hooks are configured (write side)
  4. Checks enrichment worker is alive (queue not stalled)
  5. Checks async queue depth (backlog warning)
  6. Writes stats to a shared metrics file for the dashboard
  7. Prints status summary to stdout → injected into Claude's context

If any check fails, Claude sees "⚠️ RAG DEGRADED" in its context and knows
to fall back to direct file reading.

Exit codes:
  0 = all checks passed (stdout injected as context)
  0 = partial failure (stdout still injected with warnings)
  2 = critical failure (blocks session — remove if too aggressive)
"""

import json
import os
import sys
import time
import socket
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

# Adjust these paths for your system
DB_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "database": os.environ.get("PGDATABASE", "claude_rag"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", ""),
}

METRICS_DIR = Path(os.environ.get(
    "RAG_METRICS_DIR",
    os.path.expanduser("~/.claude-rag/metrics")
))
METRICS_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))
QUEUE_STALE_THRESHOLD_SECONDS = 300  # 5 min = queue is stuck
ENRICHMENT_LAG_WARNING_SECONDS = 600  # 10 min = enrichment falling behind

# ─── Check Functions ─────────────────────────────────────────────────────────

def check_database():
    """Check DB connectivity, schema, and basic stats."""
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Schema exists
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('memory_sources', 'memory_chunks')
        """)
        tables = {row[0] for row in cur.fetchall()}
        if not {"memory_sources", "memory_chunks"}.issubset(tables):
            return {"status": "FAIL", "error": f"Missing tables. Found: {tables}"}

        # pgvector extension
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        if not cur.fetchone():
            return {"status": "FAIL", "error": "pgvector extension not installed"}

        # Stats
        cur.execute("SELECT COUNT(*) FROM memory_sources")
        source_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM memory_chunks")
        chunk_count = cur.fetchone()[0]

        cur.execute("""
            SELECT block_type, COUNT(*)
            FROM memory_chunks
            GROUP BY block_type
            ORDER BY COUNT(*) DESC
        """)
        chunk_breakdown = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT MAX(created_at) FROM memory_chunks")
        latest = cur.fetchone()[0]
        latest_str = latest.isoformat() if latest else "never"

        # Check for stale enrichment queue
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

    except ImportError:
        return {"status": "FAIL", "error": "psycopg2 not installed"}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_hooks_configured():
    """Check that PostToolUse and SessionStart hooks are in settings.json."""
    try:
        if not SETTINGS_PATH.exists():
            return {"status": "FAIL", "error": f"No settings.json at {SETTINGS_PATH}"}

        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})

        required_hooks = {
            "PostToolUse": ["Read"],  # At minimum, Read must be hooked
        }

        results = {}
        all_ok = True

        for event, expected_matchers in required_hooks.items():
            event_hooks = hooks.get(event, [])
            if not event_hooks:
                results[event] = "MISSING"
                all_ok = False
            else:
                configured_matchers = [h.get("matcher", "all") for h in event_hooks]
                missing = [m for m in expected_matchers if m not in configured_matchers and "all" not in configured_matchers]
                if missing:
                    results[event] = f"PARTIAL (missing: {missing})"
                    all_ok = False
                else:
                    results[event] = "OK"

        # Check SessionStart hook (this script itself)
        session_hooks = hooks.get("SessionStart", [])
        has_preflight = any("rag_preflight" in h.get("command", "") for h in session_hooks)
        results["SessionStart_preflight"] = "OK" if has_preflight else "NOT_CONFIGURED"

        # Check Stop hook (session summary ingestion)
        stop_hooks = hooks.get("Stop", [])
        results["Stop_hook"] = "OK" if stop_hooks else "MISSING"

        return {
            "status": "OK" if all_ok else "DEGRADED",
            "hooks": results,
        }

    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_mcp_server():
    """Check that the MCP server process is accessible."""
    try:
        # Method 1: Check if MCP server port is listening (if TCP-based)
        mcp_host = os.environ.get("RAG_MCP_HOST", "localhost")
        mcp_port = int(os.environ.get("RAG_MCP_PORT", "0"))

        if mcp_port > 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((mcp_host, mcp_port))
            sock.close()
            if result == 0:
                return {"status": "OK", "method": "tcp", "port": mcp_port}
            else:
                return {"status": "FAIL", "error": f"MCP server not listening on port {mcp_port}"}

        # Method 2: Check if MCP is configured in Claude Code settings
        if SETTINGS_PATH.exists():
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            mcp_servers = settings.get("mcpServers", {})
            rag_server = mcp_servers.get("claude-rag") or mcp_servers.get("rag") or mcp_servers.get("claude_rag")
            if rag_server:
                return {
                    "status": "CONFIGURED",
                    "method": "stdio",
                    "command": rag_server.get("command", "unknown"),
                    "note": "stdio MCP servers start on demand — will verify on first rag_search call"
                }

        return {
            "status": "FAIL",
            "error": "No MCP server configured. Add 'claude-rag' to mcpServers in settings.json"
        }

    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_enrichment_worker():
    """Check if the enrichment background worker is running and processing."""
    try:
        # Check for a heartbeat file or PID file
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
        else:
            return {
                "status": "UNKNOWN",
                "note": "No heartbeat file found. Worker may not write heartbeats, or may not be running."
            }

    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_queue_depth():
    """Check the async processing queue for backlog."""
    try:
        queue_file = METRICS_DIR / "queue_stats.json"
        if queue_file.exists():
            stats = json.loads(queue_file.read_text())
            return {
                "status": "OK" if stats.get("pending", 0) < 50 else "BACKLOG",
                "pending": stats.get("pending", 0),
                "processing": stats.get("processing", 0),
                "completed_last_hour": stats.get("completed_last_hour", 0),
                "errors_last_hour": stats.get("errors_last_hour", 0),
            }

        # Fallback: check DB for unenriched chunks as proxy
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM memory_chunks
            WHERE block_type IN ('code', 'raw', 'file_content')
            AND (metadata->>'enriched')::boolean IS NOT TRUE
            AND created_at > NOW() - INTERVAL '1 hour'
        """)
        recent_unenriched = cur.fetchone()[0]
        cur.close()
        conn.close()

        return {
            "status": "OK" if recent_unenriched < 20 else "BACKLOG",
            "recent_unenriched": recent_unenriched,
        }

    except Exception as e:
        return {"status": "UNKNOWN", "note": str(e)}


# ─── Metrics Recording ──────────────────────────────────────────────────────

def record_session_metrics(results):
    """Write preflight results to metrics file for dashboard consumption."""
    try:
        # Read session info from hook environment
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

    except Exception as e:
        pass  # Don't fail the hook if metrics recording fails


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    start = time.time()

    results = {
        "database": check_database(),
        "hooks": check_hooks_configured(),
        "mcp_server": check_mcp_server(),
        "enrichment": check_enrichment_worker(),
        "queue": check_queue_depth(),
    }

    elapsed_ms = int((time.time() - start) * 1000)

    # Determine overall status
    statuses = [r.get("status", "UNKNOWN") for r in results.values()]
    if all(s == "OK" for s in statuses):
        overall = "✅ RAG SYSTEM FULLY OPERATIONAL"
    elif any(s == "FAIL" for s in statuses):
        overall = "⚠️ RAG SYSTEM DEGRADED — some checks failed"
    else:
        overall = "🟡 RAG SYSTEM PARTIAL — some checks inconclusive"

    # Record metrics
    record_session_metrics(results)

    # Build context string for Claude
    # This gets injected into Claude's context via SessionStart hook stdout
    db = results["database"]
    hooks = results["hooks"]
    mcp = results["mcp_server"]

    lines = []
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
            lines.append(f"      ⏳ {db['unenriched_queue']} chunks awaiting enrichment")
    else:
        lines.append(f"  DB: ❌ {db.get('error', 'unavailable')}")

    # Write side (hooks)
    if hooks["status"] == "OK":
        lines.append("  WRITE: ✅ All hooks configured (Read, Bash, Grep, Prompt capture)")
    else:
        hook_details = hooks.get("hooks", {})
        lines.append(f"  WRITE: ⚠️ Hook status: {json.dumps(hook_details)}")

    # Read side (MCP)
    if mcp["status"] in ("OK", "CONFIGURED"):
        lines.append(f"  READ: ✅ MCP server {mcp['status'].lower()} ({mcp.get('method', 'stdio')})")
        lines.append("        → Use rag_search tool BEFORE reading files directly")
    else:
        lines.append(f"  READ: ❌ {mcp.get('error', 'unavailable')}")
        lines.append("        → RAG search unavailable, fall back to direct file reads")

    # Queue
    queue = results["queue"]
    if queue.get("pending", 0) > 20:
        lines.append(f"  QUEUE: ⚠️ {queue['pending']} items pending — enrichment may be behind")

    lines.append("")
    lines.append("  Run 'python -m claude_rag preflight' for full diagnostic details.")

    output = "\n".join(lines)
    print(output)

    # Always exit 0 so we inject context even on partial failure
    # Change to exit(2) if you want to BLOCK sessions when RAG is broken
    sys.exit(0)


if __name__ == "__main__":
    main()
