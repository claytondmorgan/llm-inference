"""CLI for the Claude Code RAG system.

Usage::

    python -m claude_rag health          -- Check system health
    python -m claude_rag ingest <path>   -- Ingest a file or directory
    python -m claude_rag search <query>  -- Search the RAG database
    python -m claude_rag watch           -- Start file watcher daemon
    python -m claude_rag serve           -- Start MCP server (stdio)
    python -m claude_rag worker          -- Start hook queue worker
    python -m claude_rag preflight       -- Run RAG preflight checks
    python -m claude_rag stats           -- Start stats HTTP server
    python -m claude_rag dashboard       -- Open live dashboard in browser
    python -m claude_rag activity        -- View human-readable activity log
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from claude_rag.config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(config: Config) -> None:
    """Configure the root logger based on the application config.

    Sets the root log level from ``Config.LOG_LEVEL`` and attaches a
    ``StreamHandler`` writing to *stderr* so that log output never
    intermixes with tool data on *stdout*.

    Args:
        config: The application configuration instance.
    """
    from claude_rag.logging_config import configure_logging

    configure_logging(
        level=config.LOG_LEVEL,
        log_format=config.LOG_FORMAT,
    )


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _cmd_health(config: Config) -> None:
    """Print a health report to stdout.

    Reports database connection status, chunk/source counts, the configured
    embedding model name, and the installed pgvector version.

    Args:
        config: The application configuration instance.
    """
    from claude_rag.db.manager import DatabaseManager

    db = DatabaseManager(config)

    print("=== Claude RAG Health Check ===")
    print()

    # Database connection
    connected = db.test_connection()
    status = "OK" if connected else "FAILED"
    print(f"Database connection : {status}")
    print(f"  Host              : {config.PGHOST}:{config.PGPORT}")
    print(f"  Database          : {config.PGDATABASE}")

    if connected:
        # Counts
        chunk_count = db.get_chunk_count()
        source_count = db.get_source_count()
        print(f"  Chunks            : {chunk_count:,}")
        print(f"  Sources           : {source_count:,}")

        # pgvector version
        try:
            conn = db._get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            row = cur.fetchone()
            pgvector_version = row[0] if row else "not installed"
            cur.close()
            conn.close()
        except Exception as exc:
            pgvector_version = f"error ({exc})"
        print(f"  pgvector version  : {pgvector_version}")
    else:
        print("  (skipping counts and pgvector check -- no connection)")

    print()

    # Embedding model
    print(f"Embedding model     : {config.EMBEDDING_MODEL}")
    print(f"Embedding dimension : {config.EMBEDDING_DIM}")
    print()

    # Search config
    print(f"Search top_k        : {config.SEARCH_TOP_K}")
    print(f"Relevance threshold : {config.RELEVANCE_THRESHOLD}")
    print(f"Context token budget: {config.CONTEXT_TOKEN_BUDGET}")
    print(f"RRF constant (k)    : {config.RRF_K}")


def _cmd_ingest(config: Config, path: str) -> None:
    """Ingest a single file or all .md files in a directory.

    Args:
        config: The application configuration instance.
        path: Path to a file or directory to ingest.
    """
    from claude_rag.ingestion.pipeline import IngestionPipeline

    resolved = Path(path).resolve()
    pipeline = IngestionPipeline(config=config)

    if resolved.is_file():
        print(f"Ingesting file: {resolved}")
        result = pipeline.ingest_file(str(resolved))
        if result.skipped:
            print(
                f"  Skipped (unchanged) -- source_id={result.source_id}, "
                f"existing chunks={result.chunks_created}"
            )
        else:
            print(
                f"  Done -- source_id={result.source_id}, "
                f"chunks={result.chunks_created}, "
                f"time={result.duration_ms:.1f} ms"
            )
    elif resolved.is_dir():
        print(f"Ingesting directory: {resolved}")
        results = pipeline.ingest_directory(str(resolved))
        ingested = sum(1 for r in results if not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        total_chunks = sum(r.chunks_created for r in results)
        print(
            f"  Done -- {ingested} ingested, {skipped} skipped, "
            f"{total_chunks} total chunks"
        )
    else:
        print(f"Error: path does not exist: {resolved}", file=sys.stderr)
        sys.exit(1)


def _cmd_search(
    config: Config,
    query: str,
    top_k: int | None,
    budget: int | None,
) -> None:
    """Run a hybrid search and print formatted results to stdout.

    Args:
        config: The application configuration instance.
        query: Natural language search query.
        top_k: Override for ``Config.SEARCH_TOP_K``.
        budget: Override for ``Config.CONTEXT_TOKEN_BUDGET``.
    """
    import os
    import time as _time

    from claude_rag.db.manager import DatabaseManager
    from claude_rag.embeddings.local import LocalEmbeddingProvider
    from claude_rag.monitoring.event_logger import log_event
    from claude_rag.search.formatter import deduplicate_results, format_context
    from claude_rag.search.hybrid import hybrid_search

    # Use Claude Code session ID if available, else generate a CLI-specific one
    session_id = os.environ.get("CLAUDE_SESSION_ID", f"cli-{os.getpid()}")

    effective_top_k = top_k if top_k is not None else config.SEARCH_TOP_K
    effective_budget = budget if budget is not None else config.CONTEXT_TOKEN_BUDGET

    print(f'Searching: "{query}"')
    print(f"  top_k={effective_top_k}, budget={effective_budget}")
    print()

    _t0 = _time.monotonic()
    embedder = LocalEmbeddingProvider()
    query_embedding = embedder.embed_single(query)

    db = DatabaseManager(config)
    conn = db._get_connection()
    try:
        results = hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            top_k=effective_top_k,
            db_conn=conn,
            rrf_k=config.RRF_K,
        )
    finally:
        conn.close()

    # Filter by relevance threshold and deduplicate
    results = [r for r in results if r.similarity >= config.RELEVANCE_THRESHOLD]
    results = deduplicate_results(results)

    _latency = int((_time.monotonic() - _t0) * 1000)
    # Use cosine similarity (0-1) for relevance, not RRF score (~0.02)
    _avg_cosine = (
        sum(r.metadata.get("cosine_similarity", 0) for r in results) / len(results)
        if results
        else 0.0
    )
    _is_fallback = len(results) == 0

    if not results:
        log_event(
            "rag_search",
            session_id=session_id,
            query=query[:100],
            result_count=0,
            relevance=0.0,
            latency_ms=_latency,
            fallback=True,
            budget_used_pct=0,
        )
        print("No relevant results found.")
        return

    print(f"Found {len(results)} result(s):")
    print()

    context, tokens_used = format_context(results, token_budget=effective_budget)
    _budget_pct = round(tokens_used / effective_budget * 100) if effective_budget > 0 else 0
    log_event(
        "rag_search",
        session_id=session_id,
        query=query[:100],
        result_count=len(results),
        relevance=round(_avg_cosine, 3),
        latency_ms=_latency,
        fallback=_is_fallback,
        budget_used_pct=_budget_pct,
    )
    print(context)


def _cmd_watch(config: Config) -> None:
    """Start the file watcher daemon.  Blocks until interrupted with Ctrl+C.

    Args:
        config: The application configuration instance.
    """
    from claude_rag.ingestion.pipeline import IngestionPipeline
    from claude_rag.ingestion.watcher import MemoryFileWatcher

    pipeline = IngestionPipeline(config=config)
    watcher = MemoryFileWatcher(
        directories=config.CLAUDE_MEMORY_DIRS,
        pipeline=pipeline,
    )

    print("Starting file watcher...")
    print(f"  Watching: {config.CLAUDE_MEMORY_DIRS}")
    print("  Press Ctrl+C to stop.")
    print()

    watcher.start()
    try:
        # Block the main thread until interrupted.
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
    finally:
        watcher.stop()

    print("Watcher stopped.")


def _cmd_serve() -> None:
    """Start the MCP server in stdio mode.

    This hands control to the async MCP event loop and blocks until the
    client disconnects.
    """
    from claude_rag.mcp_server.server import main as server_main

    print("Starting MCP server (stdio mode)...", file=sys.stderr)
    asyncio.run(server_main())


def _cmd_preflight(config: Config, verbose: bool) -> None:
    """Run RAG preflight checks and print results.

    This is the same logic as the SessionStart hook, but invoked
    manually for diagnostics.

    Args:
        config: The application configuration instance.
        verbose: If ``True``, print the full JSON results.
    """
    import json

    from claude_rag.hooks.rag_preflight import format_context, run_preflight

    results = run_preflight()

    if verbose:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_context(results))


def _cmd_stats(config: Config, port: int | None) -> None:
    """Start the stats HTTP server for the live dashboard.

    Args:
        config: The application configuration instance.
        port: Port override (default 9473).
    """
    import os

    if port is not None:
        os.environ["RAG_STATS_PORT"] = str(port)

    from claude_rag.monitoring.stats_server import main as stats_main

    stats_main()


def _cmd_dashboard(config: Config, port: int | None, no_browser: bool) -> None:
    """Start the dashboard server and open it in a browser.

    Args:
        config: The application configuration instance.
        port: Port override (default 9473).
        no_browser: If ``True``, skip opening the browser automatically.
    """
    import os

    if port is not None:
        os.environ["RAG_STATS_PORT"] = str(port)

    from claude_rag.monitoring.stats_server import start_dashboard_server

    start_dashboard_server(port=port, open_browser=not no_browser)


def _cmd_activity(config: Config, tail: int, follow: bool, component: str | None) -> None:
    """Pretty-print the activity log for human review.

    Args:
        config: The application configuration instance.
        tail: Number of most-recent entries to show (0 = all).
        follow: If ``True``, continuously watch for new entries.
        component: If set, only show entries whose ``component`` matches.
    """
    import json
    import time as _time
    from datetime import datetime

    activity_file = config.STATE_DIR / "metrics" / "activity.jsonl"

    if not activity_file.exists():
        print(f"Activity log not found: {activity_file}")
        print("(No activity has been recorded yet.)")
        return

    def _format_entry(entry: dict) -> str:
        """Format a single activity entry for terminal display."""
        ts = entry.get("timestamp", "")
        level = entry.get("level", "info").upper()
        comp = entry.get("component", "?")
        action = entry.get("action", "?")
        desc = entry.get("description", "")
        cid = entry.get("correlation_id")
        dur = entry.get("duration_ms")

        # Color-code by level (ANSI)
        level_colors = {"INFO": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "DEBUG": "\033[90m"}
        reset = "\033[0m"
        color = level_colors.get(level, "")

        parts = [f"{color}[{ts}] {level:5s}{reset} {comp}:{action}"]
        if cid:
            parts[0] += f"  \033[36m(#{cid})\033[0m"
        parts.append(f"  {desc}")
        if dur is not None:
            parts.append(f"  \033[90m({dur}ms)\033[0m")

        return "\n".join(parts)

    def _matches(entry: dict) -> bool:
        if component and entry.get("component", "") != component:
            return False
        return True

    def _read_entries() -> list[dict]:
        entries = []
        with open(activity_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if _matches(entry):
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries

    if not follow:
        entries = _read_entries()
        if tail > 0:
            entries = entries[-tail:]
        if not entries:
            print("No matching activity entries.")
            return
        for entry in entries:
            print(_format_entry(entry))
            print()
    else:
        # Show initial tail, then follow
        entries = _read_entries()
        if tail > 0:
            entries = entries[-tail:]
        for entry in entries:
            print(_format_entry(entry))
            print()

        print(f"\033[90m--- Following {activity_file} (Ctrl+C to stop) ---\033[0m")
        sys.stdout.flush()

        try:
            with open(activity_file, "r", encoding="utf-8") as f:
                # Seek to end
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        _time.sleep(0.3)
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if _matches(entry):
                            print(_format_entry(entry))
                            print()
                            sys.stdout.flush()
                    except json.JSONDecodeError:
                        continue
        except KeyboardInterrupt:
            print("\nStopped.")


def _cmd_worker(config: Config, once: bool) -> None:
    """Start the hook queue worker.

    Drains events enqueued by Claude Code hooks and ingests them through
    the RAG pipeline.

    Args:
        config: The application configuration instance.
        once: If ``True``, drain the queue then exit.  Otherwise poll
            continuously until interrupted.
    """
    from claude_rag.hooks.worker import HookWorker

    worker = HookWorker(config)

    if once:
        count = worker.drain()
        print(f"Processed {count} item(s).")
    else:
        print("Hook worker running. Press Ctrl+C to stop.")
        try:
            worker.run()
        except KeyboardInterrupt:
            print("\nWorker stopped.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser.

    Returns:
        An ``argparse.ArgumentParser`` with subcommands for each CLI action.
    """
    parser = argparse.ArgumentParser(
        prog="claude-rag",
        description="Claude Code RAG system CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # health
    subparsers.add_parser(
        "health",
        help="Check system health (DB, embeddings, pgvector)",
    )

    # ingest
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest a file or directory into the RAG database",
    )
    ingest_parser.add_argument(
        "path",
        help="Path to a file or directory to ingest",
    )

    # search
    search_parser = subparsers.add_parser(
        "search",
        help="Search the RAG database",
    )
    search_parser.add_argument(
        "query",
        help="Natural language search query",
    )
    search_parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Maximum number of results (default: from config)",
    )
    search_parser.add_argument(
        "--budget",
        type=int,
        default=None,
        help="Token budget for returned context (default: from config)",
    )

    # watch
    subparsers.add_parser(
        "watch",
        help="Start file watcher daemon (Ctrl+C to stop)",
    )

    # serve
    subparsers.add_parser(
        "serve",
        help="Start MCP server in stdio mode",
    )

    # worker
    worker_parser = subparsers.add_parser(
        "worker",
        help="Start hook queue worker (processes events from Claude Code hooks)",
    )
    worker_parser.add_argument(
        "--once",
        action="store_true",
        help="Drain the queue once then exit (don't poll)",
    )

    # preflight
    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Run RAG preflight checks (DB, hooks, MCP, queue)",
    )
    preflight_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full JSON diagnostic output",
    )

    # stats
    stats_parser = subparsers.add_parser(
        "stats",
        help="Start stats HTTP server for the live dashboard",
    )
    stats_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (default: 9473)",
    )

    # dashboard
    dash_parser = subparsers.add_parser(
        "dashboard",
        help="Open live monitoring dashboard in a browser",
    )
    dash_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (default: 9473)",
    )
    dash_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open a browser automatically",
    )

    # activity
    activity_parser = subparsers.add_parser(
        "activity",
        help="View human-readable activity log (hooks, worker, pipeline)",
    )
    activity_parser.add_argument(
        "--tail", "-n",
        type=int,
        default=20,
        help="Number of most-recent entries to show (0 = all, default: 20)",
    )
    activity_parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Continuously watch for new entries (like tail -f)",
    )
    activity_parser.add_argument(
        "--component", "-c",
        type=str,
        default=None,
        help="Filter by component (e.g. 'hook.post_tool_use', 'worker', 'pipeline')",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    config = Config()
    _configure_logging(config)

    if args.command == "health":
        _cmd_health(config)
    elif args.command == "ingest":
        _cmd_ingest(config, args.path)
    elif args.command == "search":
        _cmd_search(config, args.query, args.top_k, args.budget)
    elif args.command == "watch":
        _cmd_watch(config)
    elif args.command == "serve":
        _cmd_serve()
    elif args.command == "worker":
        _cmd_worker(config, args.once)
    elif args.command == "preflight":
        _cmd_preflight(config, args.verbose)
    elif args.command == "stats":
        _cmd_stats(config, args.port)
    elif args.command == "dashboard":
        _cmd_dashboard(config, args.port, args.no_browser)
    elif args.command == "activity":
        _cmd_activity(config, args.tail, args.follow, args.component)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
