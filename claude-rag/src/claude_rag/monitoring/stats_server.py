"""RAG Stats Server — live metrics endpoint and standalone dashboard.

Start::

    python -m claude_rag.monitoring.stats_server      # API only
    python -m claude_rag dashboard                     # dashboard + API

Endpoints:
    ``GET /``            — HTML dashboard (self-contained)
    ``GET /dashboard``   — alias for ``/``
    ``GET /stats``       — JSON blob consumed by the dashboard
    ``GET /health``      — plain-text ``ok``
    ``POST /shutdown``   — gracefully stop the server

Data sources:
    * PostgreSQL (chunk counts, layer breakdown, file coverage)
    * ``<STATE_DIR>/metrics/events.jsonl`` (hook counters, latency, queue depth)
    * ``<STATE_DIR>/metrics/benchmark_latest.json`` (comparison data)

Port defaults to **9473** (overridden via ``RAG_STATS_PORT``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from claude_rag.config import Config

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("RAG_STATS_PORT", "9473"))

_config = Config()
METRICS_DIR: Path = _config.STATE_DIR / "metrics"

# Cache stats for this many seconds (avoid hammering DB on every poll)
CACHE_TTL_SECONDS = 5


# ─── Stats Collector ────────────────────────────────────────────────────────

class StatsCollector:
    """Aggregates metrics from DB + event log for the dashboard."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._cache_time: float = 0
        self._lock = threading.Lock()
        self._start_time: float = time.time()

        # In-memory counters updated by event log tailing
        self._hook_counters: dict[str, int] = {
            "hooks_total": 0,
            "hooks_read": 0,
            "hooks_bash": 0,
            "hooks_grep": 0,
            "hooks_prompt": 0,
            "dedup_hits": 0,
        }
        self._search_counters: dict[str, Any] = {
            "searches_total": 0,
            "relevance_sum": 0.0,
            "results_sum": 0,
            "rag_first_count": 0,
            "fallback_count": 0,
            "total_sessions": 0,
            "budget_pct_sum": 0.0,
        }
        # Per-session tracking: did rag_search happen before first hook_read?
        self._session_first_event: dict[str, str] = {}  # session_id -> "search" | "read"
        self._latencies: dict[str, list[float]] = {
            "hook": [],
            "enrich": [],
            "search": [],
        }

        # Counters are rebuilt from events.jsonl on startup (full replay),
        # so we do NOT load persisted counters — that would double-count.
        self._start_log_tailer()

    # ── Persistence ──────────────────────────────────────────────────────

    def _load_persisted_counters(self) -> None:
        """Load counters from the metrics directory."""
        try:
            counters_file = METRICS_DIR / "counters.json"
            if counters_file.exists():
                data = json.loads(counters_file.read_text())
                self._hook_counters.update(data.get("hooks", {}))
                self._search_counters.update(data.get("search", {}))
        except Exception:
            pass

    def _persist_counters(self) -> None:
        """Save current counters to disk."""
        try:
            METRICS_DIR.mkdir(parents=True, exist_ok=True)
            counters_file = METRICS_DIR / "counters.json"
            counters_file.write_text(json.dumps({
                "hooks": self._hook_counters,
                "search": self._search_counters,
                "timestamp": datetime.now().isoformat(),
            }, indent=2))
        except Exception:
            pass

    # ── Event log tailer ─────────────────────────────────────────────────

    def _start_log_tailer(self) -> None:
        """Start a background thread that tails the hook event log.

        On startup the tailer replays the **entire** event log from the
        beginning so that ``_session_first_event`` and all counters are
        rebuilt from the single source of truth.  After the replay catch-up
        it switches to live-tailing new lines.
        """
        def tailer() -> None:
            METRICS_DIR.mkdir(parents=True, exist_ok=True)
            log_file = METRICS_DIR / "events.jsonl"
            if not log_file.exists():
                log_file.touch()

            with open(log_file, "r", encoding="utf-8") as f:
                # Replay from the beginning to rebuild all state
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        self._process_event(event)
                    except json.JSONDecodeError:
                        pass

                # Now live-tail new lines
                while True:
                    line = f.readline()
                    if line:
                        try:
                            event = json.loads(line.strip())
                            self._process_event(event)
                        except json.JSONDecodeError:
                            pass
                    else:
                        time.sleep(0.5)

        t = threading.Thread(target=tailer, daemon=True)
        t.start()

    def _process_event(self, event: dict[str, Any]) -> None:
        """Process a hook event and update counters."""
        etype = event.get("type", "")

        session_id = event.get("session_id", "")

        if etype == "hook_read":
            self._hook_counters["hooks_total"] += 1
            self._hook_counters["hooks_read"] += 1
            if event.get("dedup"):
                self._hook_counters["dedup_hits"] += 1
            if "latency_ms" in event:
                self._latencies["hook"].append(event["latency_ms"])
                self._latencies["hook"] = self._latencies["hook"][-100:]
            # Track per-session: first read before any search = not rag-first
            if session_id and session_id not in self._session_first_event:
                self._session_first_event[session_id] = "read"

        elif etype == "hook_bash":
            self._hook_counters["hooks_total"] += 1
            self._hook_counters["hooks_bash"] += 1

        elif etype == "hook_grep":
            self._hook_counters["hooks_total"] += 1
            self._hook_counters["hooks_grep"] += 1

        elif etype == "hook_prompt":
            self._hook_counters["hooks_total"] += 1
            self._hook_counters["hooks_prompt"] += 1

        elif etype == "rag_search":
            self._search_counters["searches_total"] += 1
            if "relevance" in event:
                self._search_counters["relevance_sum"] += event["relevance"]
            if "result_count" in event:
                self._search_counters["results_sum"] += event["result_count"]
            if event.get("fallback"):
                self._search_counters["fallback_count"] += 1
            if "budget_used_pct" in event:
                self._search_counters["budget_pct_sum"] += event["budget_used_pct"]
            if "latency_ms" in event:
                self._latencies["search"].append(event["latency_ms"])
                self._latencies["search"] = self._latencies["search"][-100:]
            # Track per-session: first search before any read = rag-first
            if session_id and session_id not in self._session_first_event:
                self._session_first_event[session_id] = "search"
                self._search_counters["rag_first_count"] += 1

        elif etype == "enrichment":
            if "latency_ms" in event:
                self._latencies["enrich"].append(event["latency_ms"])
                self._latencies["enrich"] = self._latencies["enrich"][-100:]

        elif etype == "session_start":
            self._search_counters["total_sessions"] += 1

        # Persist every 10 hook events
        if self._hook_counters["hooks_total"] % 10 == 0 and self._hook_counters["hooks_total"] > 0:
            self._persist_counters()

    # ── Stats collection ─────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get current stats, using cache if still fresh."""
        with self._lock:
            now = time.time()
            if self._cache and (now - self._cache_time) < CACHE_TTL_SECONDS:
                return self._cache

            stats = self._collect_fresh_stats()
            self._cache = stats
            self._cache_time = now
            return stats

    def _collect_fresh_stats(self) -> dict[str, Any]:
        """Collect all stats from DB + counters."""
        db_stats = self._query_db()
        bench_stats = self._load_benchmark()
        preflight = self._load_preflight()

        def avg_latency(key: str) -> int:
            vals = self._latencies.get(key, [])
            return int(sum(vals) / len(vals)) if vals else 0

        sc = self._search_counters
        total_searches = max(sc["searches_total"], 1)

        # RAG-first % and Fallback % are complementary session-level metrics.
        # Every session's first event is either "search" (rag-first) or "read"
        # (fallback).  They MUST sum to 100%.
        total_sessions_tracked = max(len(self._session_first_event), 1)
        rag_first_pct = min(
            int(sc["rag_first_count"] / total_sessions_tracked * 100), 100
        ) if sc["rag_first_count"] > 0 else 0
        fallback_rate_pct = 100 - rag_first_pct if len(self._session_first_event) > 0 else 0

        return {
            "timestamp": int(time.time() * 1000),
            "ts_label": datetime.now().strftime("%H:%M:%S"),
            "system": {
                "status": "active" if preflight.get("session_active") else "idle",
                "session_id": preflight.get("session_id"),
                "uptime_minutes": int((time.time() - self._start_time) / 60),
                "db_connected": db_stats.get("connected", False),
                "mcp_connected": preflight.get("mcp_ok", True),
                "enrichment_worker": preflight.get("enrichment_ok", True),
                "queue_depth": db_stats.get("queue_depth", 0),
            },
            "write": {
                **self._hook_counters,
                "chunks_total": db_stats.get("chunks_total", 0),
                "chunks_text": db_stats.get("chunks_text", 0),
                "chunks_heading": db_stats.get("chunks_heading", 0),
                "chunks_code": db_stats.get("chunks_code", 0),
                "chunks_other": db_stats.get("chunks_other", 0),
                "avg_hook_latency_ms": avg_latency("hook"),
                "avg_enrich_latency_ms": avg_latency("enrich"),
                "files_indexed": db_stats.get("files_indexed", 0),
            },
            "read": {
                "searches_total": sc["searches_total"],
                "avg_relevance": (
                    sc["relevance_sum"] / total_searches
                    if sc["relevance_sum"] > 0
                    else 0.0
                ),
                "avg_results_returned": (
                    sc["results_sum"] / total_searches
                    if sc["results_sum"] > 0
                    else 0.0
                ),
                "rag_first_pct": rag_first_pct,
                "fallback_rate_pct": fallback_rate_pct,
                "avg_search_latency_ms": avg_latency("search"),
                "avg_token_budget_used_pct": (
                    int(sc["budget_pct_sum"] / total_searches)
                    if sc["budget_pct_sum"] > 0
                    else 0
                ),
            },
            "benchmark": bench_stats,
        }

    def _get_hook_queue_depth(self) -> int:
        """Query the SQLite hook queue for pending item count."""
        try:
            from claude_rag.hooks.queue import HookQueue

            q = HookQueue(_config.STATE_DIR / "hook_queue.db")
            depth = q.pending_count()
            q.close()
            return depth
        except Exception:
            return 0

    def _query_db(self) -> dict[str, Any]:
        """Query PostgreSQL for chunk and source stats."""
        try:
            from claude_rag.db.manager import DatabaseManager

            db = DatabaseManager(_config)
            conn = db._get_connection()
            cur = conn.cursor()

            # Chunk counts by block_type
            cur.execute("""
                SELECT block_type, COUNT(*)
                FROM memory_chunks GROUP BY block_type
            """)
            type_counts: dict[str, int] = dict(cur.fetchall())

            # Source count
            files_indexed = db.get_source_count()

            # Queue depth from SQLite hook queue (actual pending ingestion items)
            queue_depth = self._get_hook_queue_depth()

            cur.close()
            conn.close()

            chunks_total = sum(type_counts.values())

            # Return the actual block_type breakdown from the DB.
            # The three main types are text, heading, code (created by
            # the parser).  When the enrichment pipeline is implemented,
            # semantic_summary / structural_signature / decision_context
            # will appear here automatically.
            return {
                "connected": True,
                "chunks_total": chunks_total,
                "chunk_types": type_counts,  # full breakdown
                # Pre-extract the main categories for the dashboard
                "chunks_text": type_counts.get("text", 0),
                "chunks_heading": type_counts.get("heading", 0),
                "chunks_code": type_counts.get("code", 0),
                "chunks_other": chunks_total - (
                    type_counts.get("text", 0)
                    + type_counts.get("heading", 0)
                    + type_counts.get("code", 0)
                ),
                "files_indexed": files_indexed,
                "queue_depth": queue_depth,
            }

        except Exception as exc:
            logger.debug("DB query failed: %s", exc)
            return {"connected": False, "error": str(exc)}

    def _load_benchmark(self) -> dict[str, Any]:
        """Load latest benchmark comparison data."""
        try:
            bench_file = METRICS_DIR / "benchmark_latest.json"
            if bench_file.exists():
                data = json.loads(bench_file.read_text())
                return {
                    "has_data": True,
                    "rag_on_avg_tokens": data.get("rag_on", {}).get("avg_tokens", 0),
                    "rag_off_avg_tokens": data.get("rag_off", {}).get("avg_tokens", 0),
                    "rag_on_avg_reads": data.get("rag_on", {}).get("avg_read_calls", 0),
                    "rag_off_avg_reads": data.get("rag_off", {}).get("avg_read_calls", 0),
                    "token_savings_pct": data.get("savings", {}).get("token_reduction_pct", 0),
                    "read_savings_pct": data.get("savings", {}).get("read_reduction_pct", 0),
                }
        except Exception:
            pass
        return {"has_data": False}

    def _load_preflight(self) -> dict[str, Any]:
        """Load latest preflight check results."""
        try:
            pf_file = METRICS_DIR / "latest_preflight.json"
            if pf_file.exists():
                data = json.loads(pf_file.read_text())
                results = data.get("preflight_results", {})
                return {
                    "session_active": data.get("session_id") is not None,
                    "session_id": data.get("session_id"),
                    "mcp_ok": results.get("mcp_server", {}).get("status") in ("OK", "CONFIGURED"),
                    "enrichment_ok": results.get("enrichment", {}).get("status") in ("OK", "SLOW", "UNKNOWN"),
                }
        except Exception:
            pass
        return {}


# ─── Dashboard HTML loader ──────────────────────────────────────────────────

_dashboard_html: bytes | None = None


def _load_dashboard_html() -> bytes:
    """Read and cache ``dashboard.html`` from the same package directory."""
    global _dashboard_html
    if _dashboard_html is None:
        html_path = Path(__file__).parent / "dashboard.html"
        _dashboard_html = html_path.read_bytes()
    return _dashboard_html


# ─── HTTP Handler ───────────────────────────────────────────────────────────

_collector: StatsCollector | None = None


class StatsHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving the dashboard, /stats, and /health endpoints."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path in ("/", "/dashboard"):
            body = _load_dashboard_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stats":
            assert _collector is not None
            stats = _collector.get_stats()
            body = json.dumps(stats).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests."""
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"shutting down")
            # Shut down in a background thread so the response completes first
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default request logging."""


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    """Start the stats HTTP server (API-only, no browser)."""
    global _collector
    _collector = StatsCollector()

    server = HTTPServer(("0.0.0.0", PORT), StatsHandler)
    print(f"RAG Stats Server running on http://localhost:{PORT}/stats")
    print(f"Dashboard polls this endpoint every {CACHE_TTL_SECONDS}s")
    print(f"Metrics dir: {METRICS_DIR}")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        _collector._persist_counters()
        server.shutdown()


def start_dashboard_server(port: int | None = None, open_browser: bool = True) -> None:
    """Start the stats server with the dashboard and optionally open a browser.

    Args:
        port: TCP port to listen on.  Falls back to ``RAG_STATS_PORT`` env var
              or **9473**.
        open_browser: If ``True``, open the dashboard URL in the default browser.
    """
    import webbrowser

    global _collector
    _collector = StatsCollector()

    listen_port = port if port is not None else PORT
    url = f"http://localhost:{listen_port}/"

    server = HTTPServer(("0.0.0.0", listen_port), StatsHandler)
    print(f"RAG Dashboard running at {url}")
    print(f"Stats API: {url}stats")
    print(f"Metrics dir: {METRICS_DIR}")
    print("Press Ctrl+C or click 'Stop Server' in the UI to stop.\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down...")
        _collector._persist_counters()
        server.server_close()


if __name__ == "__main__":
    main()
