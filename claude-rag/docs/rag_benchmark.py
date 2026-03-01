#!/usr/bin/env python3
"""
RAG Benchmark Framework
========================
Measures Claude Code's performance WITH vs WITHOUT the RAG system on standardized
tasks. Produces a baseline for continuous improvement.

Usage:
    python rag_benchmark.py --run-all          # Run full benchmark suite
    python rag_benchmark.py --run-task 3       # Run specific task
    python rag_benchmark.py --report           # Show latest results
    python rag_benchmark.py --compare          # Compare RAG-on vs RAG-off

How it works:
    1. Defines standardized tasks (questions about the codebase)
    2. Runs each task TWICE via Claude Code SDK:
       - Once with RAG enabled (MCP server + hooks active)
       - Once with RAG disabled (MCP server removed from config)
    3. Parses session JSONL to extract metrics
    4. Stores results in the metrics directory for the dashboard
    5. Produces a comparison report

Metrics captured per task:
    - Total input tokens consumed
    - Total output tokens produced
    - Number of Read tool calls
    - Number of rag_search tool calls
    - Time to first response
    - Time to completion
    - Files touched (read or modified)
    - Answer quality score (you rate 1-5 after reviewing)
"""

import json
import os
import sys
import time
import glob
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Configuration ───────────────────────────────────────────────────────────

METRICS_DIR = Path(os.environ.get(
    "RAG_METRICS_DIR",
    os.path.expanduser("~/.claude-rag/metrics")
))
METRICS_DIR.mkdir(parents=True, exist_ok=True)

BENCHMARK_DIR = METRICS_DIR / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))

PROJECT_DIR = os.environ.get(
    "RAG_PROJECT_DIR",
    r"C:\Users\ClayMorgan\PycharmProjects\llm-inference"
)

SESSION_DIR = Path(os.path.expanduser("~/.claude/projects"))

# ─── Benchmark Tasks ─────────────────────────────────────────────────────────

BENCHMARK_TASKS = [
    {
        "id": 1,
        "name": "Architecture Overview",
        "prompt": (
            "Describe the high-level architecture of this project. "
            "What are the main components, how do they connect, and what "
            "technologies does each use? Be specific about file locations."
        ),
        "category": "exploration",
        "expected_files": ["app.py", "database.py", "embeddings.py", "processor.py"],
        "difficulty": "broad",
    },
    {
        "id": 2,
        "name": "Specific Implementation Detail",
        "prompt": (
            "How does the hybrid search RRF scoring work? Walk me through "
            "the exact SQL, explain the k=60 constant, and tell me what "
            "happens when a result appears in only one of the two search methods."
        ),
        "category": "deep_dive",
        "expected_files": ["app.py"],
        "difficulty": "focused",
    },
    {
        "id": 3,
        "name": "Cross-File Relationship",
        "prompt": (
            "Trace the data flow from when a CSV file is uploaded to when "
            "its content becomes searchable. Which files are involved, what "
            "transformations happen, and where are the embeddings generated?"
        ),
        "category": "tracing",
        "expected_files": ["processor.py", "embeddings.py", "database.py"],
        "difficulty": "cross_cutting",
    },
    {
        "id": 4,
        "name": "Modification Planning",
        "prompt": (
            "I want to add a metadata filtering system to the search endpoint "
            "that allows filtering by date range, document type, and custom tags. "
            "What files need to change, what's the schema impact, and what's "
            "the implementation plan?"
        ),
        "category": "planning",
        "expected_files": ["app.py", "schema_legal.sql"],
        "difficulty": "design",
    },
    {
        "id": 5,
        "name": "Bug Investigation",
        "prompt": (
            "The search endpoint sometimes returns duplicate results when "
            "using hybrid mode. Walk through the hybrid search SQL and "
            "identify where duplicates could occur. Suggest a fix."
        ),
        "category": "debugging",
        "expected_files": ["app.py"],
        "difficulty": "analytical",
    },
    {
        "id": 6,
        "name": "Configuration Question",
        "prompt": (
            "What embedding model does this project use, what are its "
            "dimensions, and where is it configured? Is it the right choice "
            "for legal document search?"
        ),
        "category": "config",
        "expected_files": ["embeddings.py", "config.py", "app.py"],
        "difficulty": "lookup",
    },
]


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class TaskResult:
    task_id: int
    task_name: str
    rag_enabled: bool
    timestamp: str = ""
    session_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    read_calls: int = 0
    rag_search_calls: int = 0
    bash_calls: int = 0
    grep_calls: int = 0
    files_read: list = field(default_factory=list)
    unique_files_read: int = 0
    time_to_first_response_ms: int = 0
    time_to_completion_ms: int = 0
    tool_call_sequence: list = field(default_factory=list)
    rag_called_first: Optional[bool] = None
    quality_score: Optional[int] = None  # Human rates 1-5
    notes: str = ""


# ─── Session JSONL Parser ────────────────────────────────────────────────────

def parse_session_metrics(jsonl_path: str) -> dict:
    """Parse a Claude Code session JSONL and extract all metrics."""
    metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "read_calls": 0,
        "rag_search_calls": 0,
        "bash_calls": 0,
        "grep_calls": 0,
        "files_read": [],
        "tool_call_sequence": [],
        "timestamps": [],
    }

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if record.get("type") == "assistant":
                msg = record.get("message", {})

                # Token usage
                usage = msg.get("usage", {})
                metrics["input_tokens"] += usage.get("input_tokens", 0)
                metrics["output_tokens"] += usage.get("output_tokens", 0)

                # Timestamp
                ts = record.get("timestamp", "")
                if ts:
                    metrics["timestamps"].append(ts)

                # Tool calls
                for block in msg.get("content", []):
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {})

                        metrics["tool_call_sequence"].append(name)

                        if name == "Read":
                            metrics["read_calls"] += 1
                            fp = inp.get("file_path", "")
                            if fp:
                                metrics["files_read"].append(fp)

                        elif name == "rag_search":
                            metrics["rag_search_calls"] += 1

                        elif name == "Bash":
                            metrics["bash_calls"] += 1

                        elif name in ("Grep", "Glob"):
                            metrics["grep_calls"] += 1

    # Timing
    if len(metrics["timestamps"]) >= 2:
        try:
            first = datetime.fromisoformat(metrics["timestamps"][0].replace("Z", "+00:00"))
            last = datetime.fromisoformat(metrics["timestamps"][-1].replace("Z", "+00:00"))
            metrics["time_to_completion_ms"] = int((last - first).total_seconds() * 1000)
        except:
            pass

    # Was rag_search called before Read?
    seq = metrics["tool_call_sequence"]
    rag_idx = next((i for i, n in enumerate(seq) if n == "rag_search"), None)
    read_idx = next((i for i, n in enumerate(seq) if n == "Read"), None)
    if rag_idx is not None and (read_idx is None or rag_idx < read_idx):
        metrics["rag_called_first"] = True
    elif rag_idx is None:
        metrics["rag_called_first"] = None  # RAG never called
    else:
        metrics["rag_called_first"] = False

    return metrics


def find_latest_session(project_dir: str) -> Optional[str]:
    """Find the most recently modified session JSONL for a project."""
    # Claude Code encodes project paths in the directory name
    encoded = project_dir.replace("/", "-").replace("\\", "-").replace(":", "")
    # Try to find matching project directory
    for d in SESSION_DIR.iterdir():
        if d.is_dir() and encoded in d.name:
            jsonl_files = list(d.glob("*.jsonl"))
            if jsonl_files:
                return str(max(jsonl_files, key=lambda f: f.stat().st_mtime))

    # Fallback: search all projects for most recent
    all_jsonl = list(SESSION_DIR.glob("**/*.jsonl"))
    if all_jsonl:
        return str(max(all_jsonl, key=lambda f: f.stat().st_mtime))

    return None


# ─── Settings Toggle ─────────────────────────────────────────────────────────

def toggle_rag(enable: bool):
    """Enable or disable RAG by modifying Claude Code settings.

    When disabling:
      - Removes MCP server entry for claude-rag
      - Renames PostToolUse hooks (adds .disabled suffix to commands)
    When enabling:
      - Restores MCP server entry
      - Restores hook commands
    """
    backup_path = SETTINGS_PATH.with_suffix(".json.rag-benchmark-backup")

    if not SETTINGS_PATH.exists():
        print(f"ERROR: {SETTINGS_PATH} not found")
        return False

    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    if not enable:
        # Save backup before disabling
        backup_path.write_text(json.dumps(settings, indent=2))
        print(f"  Backed up settings to {backup_path}")

        # Remove MCP server
        mcp_servers = settings.get("mcpServers", {})
        for key in list(mcp_servers.keys()):
            if "rag" in key.lower():
                mcp_servers[f"_{key}_disabled"] = mcp_servers.pop(key)

        # Disable hooks (prefix commands with #DISABLED#)
        hooks = settings.get("hooks", {})
        for event, hook_list in hooks.items():
            for hook in hook_list:
                cmd = hook.get("command", "")
                if "claude_rag" in cmd or "rag_preflight" in cmd:
                    hook["command"] = f"#DISABLED# {cmd}"

        settings["mcpServers"] = mcp_servers
        settings["hooks"] = hooks
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        print("  RAG DISABLED in settings")

    else:
        # Restore from backup if it exists
        if backup_path.exists():
            backup = json.loads(backup_path.read_text(encoding="utf-8"))
            SETTINGS_PATH.write_text(json.dumps(backup, indent=2))
            backup_path.unlink()
            print("  RAG ENABLED (restored from backup)")
        else:
            # Try to re-enable in-place
            mcp_servers = settings.get("mcpServers", {})
            for key in list(mcp_servers.keys()):
                if key.startswith("_") and key.endswith("_disabled"):
                    original = key[1:].rsplit("_disabled", 1)[0]
                    mcp_servers[original] = mcp_servers.pop(key)

            hooks = settings.get("hooks", {})
            for event, hook_list in hooks.items():
                for hook in hook_list:
                    cmd = hook.get("command", "")
                    if cmd.startswith("#DISABLED# "):
                        hook["command"] = cmd.replace("#DISABLED# ", "")

            settings["mcpServers"] = mcp_servers
            settings["hooks"] = hooks
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
            print("  RAG ENABLED (in-place restoration)")

    return True


# ─── Benchmark Runner ────────────────────────────────────────────────────────

def run_single_task(task: dict, rag_enabled: bool) -> TaskResult:
    """Run a single benchmark task and collect metrics.

    This uses Claude Code in non-interactive mode via the SDK.
    If SDK is not available, it prints instructions for manual execution.
    """
    result = TaskResult(
        task_id=task["id"],
        task_name=task["name"],
        rag_enabled=rag_enabled,
        timestamp=datetime.now().isoformat(),
    )

    mode = "RAG-ON" if rag_enabled else "RAG-OFF"
    print(f"\n{'='*60}")
    print(f"Task {task['id']}: {task['name']} [{mode}]")
    print(f"{'='*60}")
    print(f"Prompt: {task['prompt'][:80]}...")

    try:
        # Try to use Claude Code SDK for automated execution
        start_time = time.time()

        proc = subprocess.run(
            ["claude", "--print", "--output-format", "json", "-p", task["prompt"]],
            capture_output=True,
            text=True,
            cwd=PROJECT_DIR,
            timeout=120,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)
        result.time_to_completion_ms = elapsed_ms

        # Find the session JSONL that was just created
        time.sleep(2)  # Wait for session to flush
        session_path = find_latest_session(PROJECT_DIR)

        if session_path:
            result.session_id = Path(session_path).stem
            metrics = parse_session_metrics(session_path)

            result.input_tokens = metrics["input_tokens"]
            result.output_tokens = metrics["output_tokens"]
            result.total_tokens = metrics["input_tokens"] + metrics["output_tokens"]
            result.read_calls = metrics["read_calls"]
            result.rag_search_calls = metrics["rag_search_calls"]
            result.bash_calls = metrics["bash_calls"]
            result.grep_calls = metrics["grep_calls"]
            result.files_read = list(set(metrics["files_read"]))
            result.unique_files_read = len(result.files_read)
            result.tool_call_sequence = metrics["tool_call_sequence"]
            result.rag_called_first = metrics["rag_called_first"]

            print(f"\n  Results:")
            print(f"    Tokens: {result.total_tokens:,} (in: {result.input_tokens:,}, out: {result.output_tokens:,})")
            print(f"    Read calls: {result.read_calls}")
            print(f"    RAG calls: {result.rag_search_calls}")
            print(f"    Files: {result.unique_files_read}")
            print(f"    Time: {result.time_to_completion_ms:,}ms")
            print(f"    RAG first: {result.rag_called_first}")
            print(f"    Tool sequence: {' → '.join(result.tool_call_sequence[:10])}")
        else:
            print("  ⚠️ Could not find session JSONL")

    except FileNotFoundError:
        print("\n  ⚠️ Claude Code CLI not found. Use manual mode:")
        print(f"  1. Open Claude Code in {PROJECT_DIR}")
        print(f"  2. Paste this prompt: {task['prompt']}")
        print(f"  3. After completion, run: python rag_benchmark.py --parse-latest --task {task['id']} --rag {'on' if rag_enabled else 'off'}")

    except subprocess.TimeoutExpired:
        print("  ⚠️ Task timed out after 120 seconds")
        result.notes = "TIMEOUT"

    except Exception as e:
        print(f"  ⚠️ Error: {e}")
        result.notes = f"ERROR: {e}"

    return result


def run_full_benchmark():
    """Run all benchmark tasks with RAG on and off."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    print("=" * 60)
    print(f"RAG BENCHMARK RUN: {run_id}")
    print(f"Tasks: {len(BENCHMARK_TASKS)}")
    print(f"Modes: RAG-ON + RAG-OFF = {len(BENCHMARK_TASKS) * 2} total runs")
    print("=" * 60)

    # Phase 1: RAG-ON runs
    print("\n\n>>> PHASE 1: RAG ENABLED <<<\n")
    toggle_rag(True)
    time.sleep(3)  # Let settings propagate

    for task in BENCHMARK_TASKS:
        result = run_single_task(task, rag_enabled=True)
        results.append(result)
        time.sleep(5)  # Cooldown between tasks

    # Phase 2: RAG-OFF runs
    print("\n\n>>> PHASE 2: RAG DISABLED <<<\n")
    toggle_rag(False)
    time.sleep(3)

    for task in BENCHMARK_TASKS:
        result = run_single_task(task, rag_enabled=False)
        results.append(result)
        time.sleep(5)

    # Restore RAG
    print("\n\n>>> RESTORING RAG <<<")
    toggle_rag(True)

    # Save results
    results_file = BENCHMARK_DIR / f"benchmark_{run_id}.json"
    results_data = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "project": PROJECT_DIR,
        "task_count": len(BENCHMARK_TASKS),
        "results": [asdict(r) for r in results],
    }
    results_file.write_text(json.dumps(results_data, indent=2))
    print(f"\nResults saved to: {results_file}")

    # Also write to dashboard-consumable format
    write_dashboard_metrics(results)

    # Print comparison report
    print_comparison_report(results)

    # Prompt for quality scores
    print("\n\n>>> QUALITY SCORING <<<")
    print("Review the output of each task and rate quality 1-5.")
    print("Run: python rag_benchmark.py --score <run_id>")


def write_dashboard_metrics(results: list):
    """Write metrics in a format the live dashboard can consume."""
    dashboard_file = METRICS_DIR / "benchmark_latest.json"

    rag_on = [r for r in results if r.rag_enabled]
    rag_off = [r for r in results if not r.rag_enabled]

    def avg(values):
        return sum(values) / len(values) if values else 0

    summary = {
        "timestamp": datetime.now().isoformat(),
        "rag_on": {
            "avg_tokens": int(avg([r.total_tokens for r in rag_on])),
            "avg_read_calls": round(avg([r.read_calls for r in rag_on]), 1),
            "avg_rag_calls": round(avg([r.rag_search_calls for r in rag_on]), 1),
            "avg_time_ms": int(avg([r.time_to_completion_ms for r in rag_on])),
            "avg_files": round(avg([r.unique_files_read for r in rag_on]), 1),
            "rag_first_pct": round(
                sum(1 for r in rag_on if r.rag_called_first is True) / max(len(rag_on), 1) * 100
            ),
        },
        "rag_off": {
            "avg_tokens": int(avg([r.total_tokens for r in rag_off])),
            "avg_read_calls": round(avg([r.read_calls for r in rag_off]), 1),
            "avg_time_ms": int(avg([r.time_to_completion_ms for r in rag_off])),
            "avg_files": round(avg([r.unique_files_read for r in rag_off]), 1),
        },
        "savings": {
            "token_reduction_pct": round(
                (1 - avg([r.total_tokens for r in rag_on]) / max(avg([r.total_tokens for r in rag_off]), 1)) * 100, 1
            ) if rag_off else 0,
            "read_reduction_pct": round(
                (1 - avg([r.read_calls for r in rag_on]) / max(avg([r.read_calls for r in rag_off]), 1)) * 100, 1
            ) if rag_off else 0,
            "time_reduction_pct": round(
                (1 - avg([r.time_to_completion_ms for r in rag_on]) / max(avg([r.time_to_completion_ms for r in rag_off]), 1)) * 100, 1
            ) if rag_off else 0,
        },
        "per_task": [],
    }

    for task in BENCHMARK_TASKS:
        on = next((r for r in rag_on if r.task_id == task["id"]), None)
        off = next((r for r in rag_off if r.task_id == task["id"]), None)
        if on and off:
            summary["per_task"].append({
                "task_id": task["id"],
                "name": task["name"],
                "category": task["category"],
                "rag_on_tokens": on.total_tokens,
                "rag_off_tokens": off.total_tokens,
                "rag_on_reads": on.read_calls,
                "rag_off_reads": off.read_calls,
                "rag_on_time_ms": on.time_to_completion_ms,
                "rag_off_time_ms": off.time_to_completion_ms,
                "token_savings_pct": round(
                    (1 - on.total_tokens / max(off.total_tokens, 1)) * 100, 1
                ),
            })

    dashboard_file.write_text(json.dumps(summary, indent=2))


def print_comparison_report(results: list):
    """Print a formatted comparison report to stdout."""
    rag_on = {r.task_id: r for r in results if r.rag_enabled}
    rag_off = {r.task_id: r for r in results if not r.rag_enabled}

    print("\n\n" + "=" * 80)
    print("RAG BENCHMARK COMPARISON REPORT")
    print("=" * 80)

    # Header
    print(f"\n{'Task':<30} {'Metric':<18} {'RAG OFF':>10} {'RAG ON':>10} {'Δ':>10}")
    print("-" * 80)

    for task in BENCHMARK_TASKS:
        on = rag_on.get(task["id"])
        off = rag_off.get(task["id"])
        if not on or not off:
            continue

        name = task["name"][:28]

        # Tokens
        t_delta = on.total_tokens - off.total_tokens
        t_pct = f"({t_delta / max(off.total_tokens, 1) * 100:+.0f}%)"
        print(f"{name:<30} {'Tokens':<18} {off.total_tokens:>10,} {on.total_tokens:>10,} {t_pct:>10}")

        # Read calls
        r_delta = on.read_calls - off.read_calls
        print(f"{'':<30} {'Read calls':<18} {off.read_calls:>10} {on.read_calls:>10} {r_delta:>+10}")

        # Time
        print(f"{'':<30} {'Time (s)':<18} {off.time_to_completion_ms/1000:>10.1f} {on.time_to_completion_ms/1000:>10.1f} {(on.time_to_completion_ms - off.time_to_completion_ms)/1000:>+10.1f}")

        # RAG usage
        if on.rag_search_calls > 0:
            first = "✅" if on.rag_called_first else "❌"
            print(f"{'':<30} {'RAG searches':<18} {'N/A':>10} {on.rag_search_calls:>10} {first:>10}")

        print("-" * 80)

    # Summary
    all_on = [r for r in results if r.rag_enabled]
    all_off = [r for r in results if not r.rag_enabled]

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0

    print(f"\n{'AVERAGES':<30}")
    avg_tok_on = avg([r.total_tokens for r in all_on])
    avg_tok_off = avg([r.total_tokens for r in all_off])
    avg_read_on = avg([r.read_calls for r in all_on])
    avg_read_off = avg([r.read_calls for r in all_off])

    print(f"  Tokens:     {avg_tok_off:,.0f} → {avg_tok_on:,.0f}  ({(avg_tok_on - avg_tok_off) / max(avg_tok_off, 1) * 100:+.1f}%)")
    print(f"  Read calls: {avg_read_off:.1f} → {avg_read_on:.1f}  ({(avg_read_on - avg_read_off) / max(avg_read_off, 1) * 100:+.1f}%)")
    print(f"  RAG-first:  {sum(1 for r in all_on if r.rag_called_first is True)}/{len(all_on)} sessions")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="RAG Benchmark Framework")
    parser.add_argument("--run-all", action="store_true", help="Run full benchmark suite")
    parser.add_argument("--run-task", type=int, help="Run specific task by ID")
    parser.add_argument("--report", action="store_true", help="Show latest benchmark results")
    parser.add_argument("--compare", action="store_true", help="Compare RAG-on vs RAG-off")
    parser.add_argument("--parse-latest", action="store_true", help="Parse most recent session JSONL")
    parser.add_argument("--task", type=int, help="Task ID for --parse-latest")
    parser.add_argument("--rag", choices=["on", "off"], help="RAG mode for --parse-latest")
    parser.add_argument("--list-tasks", action="store_true", help="List benchmark tasks")
    parser.add_argument("--toggle-rag", choices=["on", "off"], help="Toggle RAG on/off")

    args = parser.parse_args()

    if args.list_tasks:
        print("\nBenchmark Tasks:")
        for t in BENCHMARK_TASKS:
            print(f"  {t['id']}. [{t['category']}] {t['name']}")
            print(f"     {t['prompt'][:70]}...")
        return

    if args.toggle_rag:
        toggle_rag(args.toggle_rag == "on")
        return

    if args.run_all:
        run_full_benchmark()
        return

    if args.run_task:
        task = next((t for t in BENCHMARK_TASKS if t["id"] == args.run_task), None)
        if not task:
            print(f"Unknown task ID: {args.run_task}")
            return
        toggle_rag(True)
        result = run_single_task(task, rag_enabled=True)
        print(f"\nResult: {json.dumps(asdict(result), indent=2)}")
        return

    if args.parse_latest:
        session_path = find_latest_session(PROJECT_DIR)
        if session_path:
            print(f"Parsing: {session_path}")
            metrics = parse_session_metrics(session_path)
            print(json.dumps(metrics, indent=2, default=str))
        else:
            print("No session JSONL found")
        return

    if args.report or args.compare:
        dashboard_file = METRICS_DIR / "benchmark_latest.json"
        if dashboard_file.exists():
            data = json.loads(dashboard_file.read_text())
            print(json.dumps(data, indent=2))
        else:
            print("No benchmark data found. Run --run-all first.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
