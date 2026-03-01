"""Comprehensive dashboard stress test with exact math validation.

Generates known quantities of every event type, then compares the
dashboard /stats JSON against mathematically expected values.

Usage:
    PGPASSWORD=postgres PYTHONPATH=src python tests/stress_test_dashboard.py

Set STATS_URL to override the dashboard URL (default: http://localhost:9474).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

# --- Configuration ---------------------------------------------------------

STATS_URL = os.environ.get("STATS_URL", "http://localhost:9474")
STATS_ENDPOINT = f"{STATS_URL}/stats"

# Test parameters: exact counts per session
NUM_SESSIONS = 20
READS_PER_SESSION = 10
DEDUP_READS_PER_SESSION = 3   # of the 10 reads, 3 have dedup=True
BASH_PER_SESSION = 3
GREP_PER_SESSION = 2
PROMPTS_PER_SESSION = 2
SEARCHES_PER_SESSION = 4

# Fixed values on every search event (so averages are deterministic)
RELEVANCE_PER_SEARCH = 0.72
RESULTS_PER_SEARCH = 5
BUDGET_PCT_PER_SEARCH = 65
SEARCH_LATENCY_MS = 45
HOOK_LATENCY_MS = 12

# Sessions 0..13 are rag-first (first event = search).
# Sessions 14..19 are fallback (first event = read).
RAG_FIRST_SESSIONS = 14
FALLBACK_SESSIONS = NUM_SESSIONS - RAG_FIRST_SESSIONS  # 6

# --- Expected values -------------------------------------------------------

EXPECTED: dict[str, Any] = {}


def compute_expected() -> None:
    """Derive every expected dashboard value from the constants above.

    IMPORTANT -- how the stats server counts hook_read events:
      hooks_total += 1   (for EVERY hook_read, dedup or not)
      hooks_read  += 1   (for EVERY hook_read, dedup or not)
      dedup_hits  += 1   (only when dedup=True)

    So hooks_read = ALL read events.  dedup_hits is a *subset* of hooks_read.
    """
    # -- Write pipeline --
    reads_total = NUM_SESSIONS * READS_PER_SESSION       # 200
    dedup_total = NUM_SESSIONS * DEDUP_READS_PER_SESSION  # 60
    bash_total = NUM_SESSIONS * BASH_PER_SESSION          # 60
    grep_total = NUM_SESSIONS * GREP_PER_SESSION          # 40
    prompt_total = NUM_SESSIONS * PROMPTS_PER_SESSION     # 40

    # hooks_total = every non-search event that enters _process_event
    hooks_total = reads_total + bash_total + grep_total + prompt_total  # 340

    EXPECTED["hooks_total"] = hooks_total
    EXPECTED["hooks_read"] = reads_total       # ALL reads (dedup + non-dedup)
    EXPECTED["hooks_bash"] = bash_total
    EXPECTED["hooks_grep"] = grep_total
    EXPECTED["hooks_prompt"] = prompt_total
    EXPECTED["dedup_hits"] = dedup_total       # subset of hooks_read

    # -- Read pipeline --
    searches_total = NUM_SESSIONS * SEARCHES_PER_SESSION
    EXPECTED["searches_total"] = searches_total
    EXPECTED["avg_relevance"] = RELEVANCE_PER_SEARCH
    EXPECTED["avg_results_returned"] = float(RESULTS_PER_SEARCH)
    EXPECTED["avg_search_latency_ms"] = SEARCH_LATENCY_MS
    EXPECTED["avg_hook_latency_ms"] = HOOK_LATENCY_MS
    EXPECTED["avg_token_budget_used_pct"] = BUDGET_PCT_PER_SEARCH

    # -- Session metrics --
    EXPECTED["rag_first_pct"] = int(RAG_FIRST_SESSIONS / NUM_SESSIONS * 100)  # 70
    EXPECTED["fallback_rate_pct"] = 100 - EXPECTED["rag_first_pct"]  # 30

    # Sanity: they MUST sum to 100
    assert EXPECTED["rag_first_pct"] + EXPECTED["fallback_rate_pct"] == 100

    # -- Benchmark (injected) --
    EXPECTED["rag_on_avg_tokens"] = 12000
    EXPECTED["rag_off_avg_tokens"] = 25000
    EXPECTED["rag_on_avg_reads"] = 1.5
    EXPECTED["rag_off_avg_reads"] = 5.5
    EXPECTED["token_savings_pct"] = 52
    EXPECTED["read_savings_pct"] = 73


# --- Helpers ---------------------------------------------------------------

def get_metrics_dir() -> Path:
    return Path.home() / ".claude-rag" / "metrics"


def fetch_stats(retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(STATS_ENDPOINT)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Cannot reach {STATS_ENDPOINT}: {e}") from e
            time.sleep(1)
    return {}


# --- Event generation ------------------------------------------------------

def generate_session_events(session_idx: int) -> list[dict]:
    """Generate all events for one session in correct first-event order."""
    sid = f"stress_{session_idx:04d}"
    ts = datetime.now().isoformat()
    events: list[dict] = []

    is_rag_first = session_idx < RAG_FIRST_SESSIONS

    if is_rag_first:
        # First event = search  =>  rag-first session
        events.append({
            "type": "rag_search", "session_id": sid, "timestamp": ts,
            "relevance": RELEVANCE_PER_SEARCH, "result_count": RESULTS_PER_SEARCH,
            "fallback": False, "budget_used_pct": BUDGET_PCT_PER_SEARCH,
            "latency_ms": SEARCH_LATENCY_MS,
        })
        # Then all reads
        for i in range(READS_PER_SESSION):
            events.append({
                "type": "hook_read", "session_id": sid, "timestamp": ts,
                "file_path": f"/test/s{session_idx}_r{i}.py",
                "latency_ms": HOOK_LATENCY_MS,
                "dedup": i < DEDUP_READS_PER_SESSION,
            })
        remaining_searches = SEARCHES_PER_SESSION - 1
    else:
        # First event = read  =>  fallback session
        events.append({
            "type": "hook_read", "session_id": sid, "timestamp": ts,
            "file_path": f"/test/s{session_idx}_first.py",
            "latency_ms": HOOK_LATENCY_MS,
            "dedup": False,
        })
        # Remaining reads (READS_PER_SESSION - 1 more)
        for i in range(READS_PER_SESSION - 1):
            events.append({
                "type": "hook_read", "session_id": sid, "timestamp": ts,
                "file_path": f"/test/s{session_idx}_r{i}.py",
                "latency_ms": HOOK_LATENCY_MS,
                "dedup": i < DEDUP_READS_PER_SESSION,
            })
        remaining_searches = SEARCHES_PER_SESSION

    # Bash
    for _ in range(BASH_PER_SESSION):
        events.append({"type": "hook_bash", "session_id": sid, "timestamp": ts})

    # Grep
    for _ in range(GREP_PER_SESSION):
        events.append({"type": "hook_grep", "session_id": sid, "timestamp": ts})

    # Prompt
    for _ in range(PROMPTS_PER_SESSION):
        events.append({"type": "hook_prompt", "session_id": sid, "timestamp": ts})

    # Remaining searches
    for _ in range(remaining_searches):
        events.append({
            "type": "rag_search", "session_id": sid, "timestamp": ts,
            "relevance": RELEVANCE_PER_SEARCH, "result_count": RESULTS_PER_SEARCH,
            "fallback": False, "budget_used_pct": BUDGET_PCT_PER_SEARCH,
            "latency_ms": SEARCH_LATENCY_MS,
        })

    return events


def inject_benchmark(metrics_dir: Path) -> None:
    bench = {
        "rag_on": {"avg_tokens": EXPECTED["rag_on_avg_tokens"],
                    "avg_read_calls": EXPECTED["rag_on_avg_reads"]},
        "rag_off": {"avg_tokens": EXPECTED["rag_off_avg_tokens"],
                     "avg_read_calls": EXPECTED["rag_off_avg_reads"]},
        "savings": {"token_reduction_pct": EXPECTED["token_savings_pct"],
                     "read_reduction_pct": EXPECTED["read_savings_pct"]},
    }
    (metrics_dir / "benchmark_latest.json").write_text(
        json.dumps(bench, indent=2), encoding="utf-8"
    )


# --- Validation report -----------------------------------------------------

class V:
    """Validation result accumulator."""

    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, expected: Any, actual: Any,
              tol: float = 0, note: str = "") -> bool:
        if isinstance(expected, float):
            ok = abs(expected - float(actual)) <= tol
        elif isinstance(expected, bool):
            ok = bool(actual) == expected
        else:
            ok = abs(int(expected) - int(actual)) <= tol
        self.checks.append(dict(name=name, exp=expected, act=actual,
                                ok=ok, tol=tol, note=note))
        return ok

    def check_sum(self, name: str, parts: list[tuple[str, Any]],
                  total: Any, tol: float = 0) -> bool:
        s = sum(v for _, v in parts)
        ok = abs(s - total) <= tol
        detail = " + ".join(f"{n}={v}" for n, v in parts)
        self.checks.append(dict(name=name, exp=f"sum={total}",
                                act=f"{detail} = {s}", ok=ok, tol=tol,
                                note="additive consistency"))
        return ok

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c["ok"])

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c["ok"])

    @property
    def all_ok(self) -> bool:
        return all(c["ok"] for c in self.checks)

    def report(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("=" * 78)
        lines.append("  DASHBOARD VALIDATION REPORT")
        lines.append("=" * 78)
        lines.append(f"  Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Endpoint: {STATS_URL}")
        lines.append(f"  Sessions: {NUM_SESSIONS} ({RAG_FIRST_SESSIONS} rag-first, "
                      f"{FALLBACK_SESSIONS} fallback)")
        lines.append("")

        # Group by section
        sections: dict[str, list[dict]] = {
            "WRITE PIPELINE": [], "READ PIPELINE": [],
            "SESSION METRICS (must sum to 100%)": [],
            "CHUNK LAYERS": [], "SYSTEM STATUS": [],
            "BENCHMARK": [], "CONSISTENCY CHECKS": [],
        }
        for c in self.checks:
            n = c["name"]
            if any(k in n for k in ("hooks_", "dedup")):
                sections["WRITE PIPELINE"].append(c)
            elif any(k in n for k in ("search", "relevance", "results_ret", "budget")):
                sections["READ PIPELINE"].append(c)
            elif any(k in n for k in ("rag_first", "fallback", "sum=100")):
                sections["SESSION METRICS (must sum to 100%)"].append(c)
            elif any(k in n for k in ("chunk", "layer")):
                sections["CHUNK LAYERS"].append(c)
            elif any(k in n for k in ("db_", "uptime", "mcp_", "enrichment")):
                sections["SYSTEM STATUS"].append(c)
            elif any(k in n for k in ("benchmark", "rag_on", "rag_off", "savings")):
                sections["BENCHMARK"].append(c)
            else:
                sections["CONSISTENCY CHECKS"].append(c)

        for sec, checks in sections.items():
            if not checks:
                continue
            lines.append(f"  --- {sec} ---")
            for c in checks:
                mark = "[PASS]" if c["ok"] else "[FAIL]"
                lines.append(f"    {mark} {c['name']}")
                t = f" (tol={c['tol']})" if c["tol"] else ""
                lines.append(f"           expected: {c['exp']}{t}")
                lines.append(f"           actual:   {c['act']}")
                if c.get("note"):
                    lines.append(f"           note:     {c['note']}")
            lines.append("")

        lines.append("-" * 78)
        t = len(self.checks)
        lines.append(f"  TOTAL: {t} checks  |  PASSED: {self.passed}  |  FAILED: {self.failed}")
        lines.append("")
        if self.all_ok:
            lines.append("  *** ALL CHECKS PASSED ***")
        else:
            lines.append("  *** FAILURES DETECTED ***")
            for c in self.checks:
                if not c["ok"]:
                    lines.append(f"    X {c['name']}: expected {c['exp']}, got {c['act']}")
        lines.append("=" * 78)
        return "\n".join(lines)


def validate(stats: dict, v: V) -> None:
    """Run all validation checks against /stats JSON."""
    w = stats.get("write", {})
    r = stats.get("read", {})
    s = stats.get("system", {})
    b = stats.get("benchmark", {})

    # Write pipeline
    v.check("hooks_total", EXPECTED["hooks_total"], w.get("hooks_total", 0))
    v.check("hooks_read", EXPECTED["hooks_read"], w.get("hooks_read", 0))
    v.check("hooks_bash", EXPECTED["hooks_bash"], w.get("hooks_bash", 0))
    v.check("hooks_grep", EXPECTED["hooks_grep"], w.get("hooks_grep", 0))
    v.check("hooks_prompt", EXPECTED["hooks_prompt"], w.get("hooks_prompt", 0))
    v.check("dedup_hits", EXPECTED["dedup_hits"], w.get("dedup_hits", 0))
    v.check("avg_hook_latency_ms", EXPECTED["avg_hook_latency_ms"],
            w.get("avg_hook_latency_ms", 0), tol=1)

    # Read pipeline
    v.check("searches_total", EXPECTED["searches_total"], r.get("searches_total", 0))
    v.check("avg_relevance", EXPECTED["avg_relevance"],
            r.get("avg_relevance", 0.0), tol=0.01)
    v.check("avg_results_returned", EXPECTED["avg_results_returned"],
            r.get("avg_results_returned", 0.0), tol=0.1)
    v.check("avg_search_latency_ms", EXPECTED["avg_search_latency_ms"],
            r.get("avg_search_latency_ms", 0), tol=1)
    v.check("avg_token_budget_used_pct", EXPECTED["avg_token_budget_used_pct"],
            r.get("avg_token_budget_used_pct", 0), tol=1)

    # Session metrics (MUST sum to 100%)
    rfp = r.get("rag_first_pct", 0)
    fbp = r.get("fallback_rate_pct", 0)
    v.check("rag_first_pct", EXPECTED["rag_first_pct"], rfp)
    v.check("fallback_rate_pct", EXPECTED["fallback_rate_pct"], fbp)
    v.check_sum("rag_first + fallback = 100",
                [("rag_first", rfp), ("fallback", fbp)], 100)

    # Chunk layers (actual block types from DB: text, heading, code, other)
    ct = w.get("chunks_total", 0)
    c_text = w.get("chunks_text", 0)
    c_heading = w.get("chunks_heading", 0)
    c_code = w.get("chunks_code", 0)
    c_other = w.get("chunks_other", 0)
    v.check("chunks_total > 0", True, ct > 0, note=f"value={ct}")
    v.check_sum("layer sum = chunks_total",
                [("text", c_text), ("heading", c_heading),
                 ("code", c_code), ("other", c_other)], ct)
    v.check("chunks_text > 0", True, c_text > 0, note=f"value={c_text}")
    v.check("chunks_heading > 0", True, c_heading > 0, note=f"value={c_heading}")
    v.check("chunks_code > 0", True, c_code > 0, note=f"value={c_code}")

    # System status
    v.check("db_connected", True, s.get("db_connected", False))
    v.check("uptime >= 0", True, s.get("uptime_minutes", -1) >= 0,
            note=f"value={s.get('uptime_minutes')}")

    # Benchmark
    v.check("benchmark has_data", True, b.get("has_data", False))
    v.check("rag_on_avg_tokens", EXPECTED["rag_on_avg_tokens"],
            b.get("rag_on_avg_tokens", 0))
    v.check("rag_off_avg_tokens", EXPECTED["rag_off_avg_tokens"],
            b.get("rag_off_avg_tokens", 0))
    v.check("rag_on_avg_reads", EXPECTED["rag_on_avg_reads"],
            b.get("rag_on_avg_reads", 0.0), tol=0.01)
    v.check("rag_off_avg_reads", EXPECTED["rag_off_avg_reads"],
            b.get("rag_off_avg_reads", 0.0), tol=0.01)
    v.check("token_savings_pct", EXPECTED["token_savings_pct"],
            b.get("token_savings_pct", 0))
    v.check("read_savings_pct", EXPECTED["read_savings_pct"],
            b.get("read_savings_pct", 0))

    # Consistency: hook subtypes sum to hooks_total
    v.check_sum("subtypes sum = hooks_total",
                [("read", w.get("hooks_read", 0)), ("bash", w.get("hooks_bash", 0)),
                 ("grep", w.get("hooks_grep", 0)), ("prompt", w.get("hooks_prompt", 0))],
                w.get("hooks_total", 0))

    # Consistency: dedup_hits is a subset of hooks_read
    hr = w.get("hooks_read", 0)
    dh = w.get("dedup_hits", 0)
    v.check("dedup_hits <= hooks_read",
            True, dh <= hr,
            note=f"dedup={dh}, hooks_read={hr}")


# --- Main ------------------------------------------------------------------

def main() -> int:
    print("=" * 78)
    print("  DASHBOARD STRESS TEST -- FULL VALIDATION")
    print("=" * 78)

    # Step 0: compute expected values
    compute_expected()
    print("\n[0] Expected values:")
    for k, val in sorted(EXPECTED.items()):
        print(f"     {k}: {val}")

    # Step 1: kill any existing dashboard on our port
    port = STATS_URL.rsplit(":", 1)[-1].rstrip("/")
    print(f"\n[1] Ensuring port {port} is free ...")
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{STATS_URL}/shutdown", method="POST"), timeout=5)
        time.sleep(2)
        print("    Shut down existing dashboard.")
    except Exception:
        print("    No existing dashboard to shut down.")

    # Step 2: clear events + counters
    metrics_dir = get_metrics_dir()
    metrics_dir.mkdir(parents=True, exist_ok=True)
    events_file = metrics_dir / "events.jsonl"
    counters_file = metrics_dir / "counters.json"

    print("\n[2] Clearing old data ...")
    events_file.write_text("", encoding="utf-8")
    if counters_file.exists():
        counters_file.unlink()
    print(f"    Cleared {events_file}")

    # Step 3: inject benchmark
    print("\n[3] Injecting benchmark data ...")
    inject_benchmark(metrics_dir)

    # Step 4: start fresh dashboard
    print(f"\n[4] Starting fresh dashboard on port {port} ...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PGPASSWORD"] = env.get("PGPASSWORD", "postgres")
    env["RAG_STATS_PORT"] = port

    project_root = str(Path(__file__).resolve().parent.parent)
    dashboard = subprocess.Popen(
        [sys.executable, "-m", "claude_rag.monitoring.stats_server"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=project_root,
    )
    time.sleep(3)

    try:
        fetch_stats()
        print(f"    Dashboard running (PID {dashboard.pid})")
    except Exception as e:
        print(f"    FATAL: Dashboard failed to start: {e}")
        dashboard.kill()
        return 1

    # Step 5: generate events
    print(f"\n[5] Generating {NUM_SESSIONS} sessions ...")
    all_events: list[dict] = []
    for i in range(NUM_SESSIONS):
        all_events.extend(generate_session_events(i))
    print(f"    {len(all_events)} total events")

    # Count types
    tcounts: dict[str, int] = {}
    for e in all_events:
        tcounts[e["type"]] = tcounts.get(e["type"], 0) + 1
    print(f"    Types: {dict(sorted(tcounts.items()))}")

    # Step 6: write events via thread-safe log_event
    # Use one thread PER SESSION so each session's events stay in order.
    # This matches real-world behavior (Claude Code processes one tool at a
    # time per session) while still stress-testing concurrent writes across
    # sessions.
    print(f"\n[6] Writing events ({NUM_SESSIONS} session threads) ...")
    sys.path.insert(0, os.path.join(project_root, "src"))
    from claude_rag.monitoring.event_logger import log_event

    # Group events by session
    session_events: dict[int, list[dict]] = {}
    for i in range(NUM_SESSIONS):
        session_events[i] = generate_session_events(i)

    t0 = time.monotonic()

    def write_session(idx: int) -> int:
        """Write all events for one session in order."""
        for e in session_events[idx]:
            etype = e["type"]
            payload = {k: v for k, v in e.items() if k != "type"}
            log_event(etype, **payload)
        return len(session_events[idx])

    with ThreadPoolExecutor(max_workers=NUM_SESSIONS) as pool:
        futs = [pool.submit(write_session, i) for i in range(NUM_SESSIONS)]
        written = sum(f.result() for f in as_completed(futs))

    elapsed = time.monotonic() - t0
    print(f"    Wrote {written} events in {elapsed:.2f}s "
          f"({written / elapsed:.0f} events/sec)")

    # Step 7: wait for dashboard to ingest
    print("\n[7] Waiting for dashboard to process events ...")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            st = fetch_stats()
            h = st.get("write", {}).get("hooks_total", 0)
            sr = st.get("read", {}).get("searches_total", 0)
            print(f"    hooks={h}/{EXPECTED['hooks_total']}  "
                  f"searches={sr}/{EXPECTED['searches_total']}")
            if h >= EXPECTED["hooks_total"] and sr >= EXPECTED["searches_total"]:
                break
        except Exception:
            pass
    else:
        print("    WARNING: timed out waiting for counters")

    # Wait one more cache cycle
    time.sleep(6)

    # Step 8: fetch final stats
    print("\n[8] Fetching final stats ...")
    stats = fetch_stats()

    # Print raw JSON for debugging
    print("\n    Raw /stats JSON:")
    for section in ("system", "write", "read", "benchmark"):
        print(f"    {section}:")
        for k, val in sorted(stats.get(section, {}).items()):
            print(f"      {k}: {val}")

    # Step 9: validate
    print("\n[9] Validating ...")
    v = V()
    validate(stats, v)
    print(v.report())

    # Step 10: integrity check
    print("[10] events.jsonl integrity ...")
    total_lines = corrupt = 0
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            try:
                json.loads(line.strip())
            except json.JSONDecodeError:
                corrupt += 1
    print(f"     {total_lines} lines, {corrupt} corrupt "
          f"({'ALL VALID' if corrupt == 0 else 'CORRUPTION DETECTED'})")

    # Step 11: shut down dashboard
    print("\n[11] Shutting down dashboard ...")
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{STATS_URL}/shutdown", method="POST"), timeout=5)
    except Exception:
        pass
    dashboard.wait(timeout=10)
    print("     Done.\n")

    return 0 if v.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())