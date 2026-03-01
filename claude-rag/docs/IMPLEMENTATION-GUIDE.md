# Claude Code RAG System — Implementation Reference Guide

## CONTEXT FOR CLAUDE CODE

You are implementing a local RAG system that augments Claude Code's context by:
- **WRITE side:** Intercepting every file read, command, and prompt via Claude Code hooks → chunking → embedding → storing in PostgreSQL with pgvector
- **READ side:** Exposing hybrid search (semantic + keyword + RRF fusion) via an MCP server tool that Claude calls BEFORE reading files directly

This system lives inside an existing project at:
```
C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag\
```

The parent `llm-inference` repo has working code to REUSE — do not rebuild from scratch.

---

## REFERENCE ARTIFACTS

All planning documents and implementation templates are stored together. The user will
tell you where they've placed them. Here is what each file contains and when to use it:

### Architecture & Planning

| File | What It Is | When to Read It |
|------|-----------|-----------------|
| `agent-orchestration-script.md` | Master plan: 27 tasks, 5 phases, dependency graph, agent assignments, existing code inventory with exact file paths and line numbers | **READ FIRST** — this is the source of truth for the whole project |
| `claude-code-rag-plan.md` | Original high-level architecture: tech stack, component overview, data flow | Read for architectural context if you need to understand the "why" behind decisions |
| `bootstrap-guide.md` | Step-by-step project setup: pyproject.toml, CLAUDE.md template, phased dispatch prompts | Read if starting from scratch or verifying project structure |

### Dependency Graphs (Mermaid)

| File | What It Is |
|------|-----------|
| `rag-precedence-graph.mermaid` | Original task dependency graph (Phases 0-4) |
| `rag-precedence-graph-revised.mermaid` | Revised graph accounting for existing code reuse |
| `phase2-precedence-graph.mermaid` | Phase 2 graph: hooks → enrichment → dedup → search |

### Phase-Specific Plans

| File | What It Is | When to Read It |
|------|-----------|-----------------|
| `phase1-verification-and-phase2-revised.md` | Phase 1 verification tests (V1.1-V1.10) + full Phase 2 plan: hook-based interception (T-H1 to T-H5), layered enrichment (T-E1 to T-E4), deduplication (T-D1 to T-D3) + **critical discovery about Claude Code's hooks system and session JSONL format** | Read before working on hooks, enrichment, or dedup |
| `phase2-verification-tests.md` | 23 human-observable live tests (V2.1-V2.23) across 5 areas: hook interception, enrichment layers, deduplication, RAG retrieval, full loop verification | Read when implementing tests or verifying the system works |

### Implementation Templates (Ready to Adapt)

| File | What It Is | When to Read It |
|------|-----------|-----------------|
| `rag_preflight.py` | SessionStart hook script — checks DB, hooks, MCP, enrichment worker, queue depth at every session start (including subagents and agent teams). Prints status to stdout which gets injected into Claude's context. | **Adapt and install** as `src/claude_rag/hooks/rag_preflight.py` |
| `rag_benchmark.py` | Benchmark framework — 6 standardized tasks, runs with RAG on/off, parses session JSONL for tokens/reads/timing, produces comparison report. Includes settings.json toggle logic. | **Adapt and install** as `src/claude_rag/benchmark.py` or project root |
| `rag_stats_server.py` | HTTP stats server (port 9473) — aggregates metrics from DB + hook event log, serves `/stats` JSON endpoint for dashboard. Includes event logger function for hooks to call. | **Adapt and install** as `src/claude_rag/monitoring/stats_server.py` |
| `rag_dashboard.jsx` | Live React dashboard — polls stats server, shows write-side metrics (hooks, chunks, dedup, latency, queue), read-side metrics (searches, relevance, RAG-first %, fallback), benchmark comparison. Starts in demo mode. | Deploy as a standalone artifact or serve from the stats server |

### Operations Guide

| File | What It Is |
|------|-----------|
| `rag-startup-guide.md` | Complete operations manual: settings.json template with all hooks + MCP config, start_rag.bat launcher, troubleshooting flowchart, architecture diagram |

---

## EXISTING CODE TO REUSE (CRITICAL)

The parent `llm-inference/` project contains working implementations. Always import
and adapt these rather than writing from scratch:

### Embedding System → WRAP in abstract interface
- **File:** `../lambda-s3-trigger/ingestion-worker/app/embeddings.py`
- **Class:** `EmbeddingGenerator` — batch support, mean pooling, L2 normalization
- **Model:** `all-MiniLM-L6-v2` (384-dim) by default

### Database Patterns → EXTEND with local config
- **File:** `../lambda-s3-trigger/ingestion-worker/app/database.py`
- **Class:** `DatabaseManager` — connection management, bulk insert, job tracking
- **File:** `../schema_legal.sql` — pgvector columns, HNSW indexes, GIN indexes, generated tsvector
- **File:** `../migrate_schema.py` — idempotent migration pattern

### Hybrid RRF Search → ADAPT the SQL
- **File:** `../app.py` lines 1139-1191 — semantic CTE + keyword CTE + FULL OUTER JOIN + RRF
- **File:** `../app.py` lines 1084-1108 — dynamic WHERE clause builder

### Ingestion Pipeline → FOLLOW the pattern
- **File:** `../lambda-s3-trigger/ingestion-worker/app/processor.py`
- **Class:** `CSVProcessor` — field detection, batch processing, embed + insert pipeline

### Config Pattern → MIRROR
- **File:** `../lambda-s3-trigger/ingestion-worker/app/config.py`
- **Class:** Config with env var overrides and defaults

---

## TARGET PROJECT STRUCTURE

```
claude-rag/
├── src/claude_rag/
│   ├── __init__.py
│   ├── config.py                    # Config with env var overrides
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql               # Tables, indexes, tsvector columns
│   │   ├── manager.py               # Extended DatabaseManager
│   │   └── migrate.py               # Idempotent migration
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract EmbeddingProvider interface
│   │   └── local.py                 # Wraps existing EmbeddingGenerator
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── parser.py                # Parse CLAUDE.md + session JSONL
│   │   ├── chunker.py               # Code-fence-aware chunking
│   │   ├── watcher.py               # Watchdog file monitor
│   │   └── pipeline.py              # Orchestrate parse→chunk→embed→store
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── summarizer.py            # Layer 1: Semantic summaries via LLM
│   │   ├── signatures.py            # Layer 2: Structural signatures via AST
│   │   ├── decisions.py             # Layer 3: Decision context from thinking blocks
│   │   ├── pipeline.py              # Enrichment orchestrator
│   │   └── worker.py                # Background enrichment worker
│   ├── search/
│   │   ├── __init__.py
│   │   ├── semantic.py              # Vector similarity search
│   │   ├── keyword.py               # Full-text tsvector search
│   │   ├── hybrid.py                # RRF fusion combining both
│   │   └── formatter.py             # Token-budget-aware context formatter
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── rag_preflight.py         # SessionStart hook ← from rag_preflight.py artifact
│   │   ├── post_read.py             # PostToolUse(Read) hook
│   │   ├── post_bash.py             # PostToolUse(Bash) hook
│   │   ├── post_grep.py             # PostToolUse(Grep) hook
│   │   ├── prompt_capture.py        # UserPromptSubmit hook
│   │   └── session_end.py           # Stop hook → summary ingestion
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── stats_server.py          # HTTP stats endpoint ← from rag_stats_server.py artifact
│   │   └── event_logger.py          # Structured event logging for hooks
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   └── server.py                # MCP server exposing rag_search tool
│   └── cli.py                       # CLI: health, ingest, search, watch, coverage, preflight
├── tests/
│   ├── __init__.py
│   ├── fixtures/                    # Sample CLAUDE.md, session JSONL snippets
│   ├── test_parser.py
│   ├── test_chunker.py
│   ├── test_embeddings.py
│   ├── test_db.py
│   ├── test_search.py
│   ├── test_hooks.py
│   └── test_pipeline.py
├── rag_benchmark.py                 # ← from rag_benchmark.py artifact
├── rag_dashboard.jsx                # ← from rag_dashboard.jsx artifact
├── pyproject.toml
├── CLAUDE.md                        # Project instructions for Claude Code sessions
└── start_rag.bat                    # One-click launcher for background services
```

---

## IMPLEMENTATION PRIORITY

The user has already built Phases 1 and 2. The current task is:

### IMMEDIATE: Implement monitoring, preflight, and benchmark

1. **Adapt `rag_preflight.py`** → install at `src/claude_rag/hooks/rag_preflight.py`
   - Update paths for the actual project structure
   - Wire DB queries to match the actual schema table/column names
   - Test: `python src/claude_rag/hooks/rag_preflight.py` should print green status

2. **Adapt `rag_stats_server.py`** → install at `src/claude_rag/monitoring/stats_server.py`
   - Wire `_query_db()` to the actual schema
   - Wire event log tailing to wherever hooks write events
   - Test: `curl http://localhost:9473/stats` returns valid JSON

3. **Adapt `rag_benchmark.py`** → install at project root
   - Update `PROJECT_DIR` and session JSONL paths for Windows
   - Verify `toggle_rag()` correctly modifies settings.json
   - Test: `python rag_benchmark.py --list-tasks` shows 6 tasks

4. **Install hooks in settings.json** using the template from `rag-startup-guide.md`
   - Ensure all hook script paths are absolute Windows paths
   - Test: start a Claude Code session and check that preflight output appears

5. **Deploy dashboard** — the `rag_dashboard.jsx` can be opened as a Claude.ai artifact
   or served from a local dev server

### THEN: Run verification tests from `phase2-verification-tests.md`
- Start with Area A (hook interception) V2.1-V2.6
- Then Area D (RAG retrieval) V2.16-V2.20
- Then Area E (full loop) V2.21-V2.23

---

## CRITICAL TECHNICAL DETAILS

### Claude Code Session JSONL Format
Sessions are stored at: `~/.claude/projects/<url-encoded-path>/<session-uuid>.jsonl`
Each line is a JSON object. Key types:
- `{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "..."}}]}}`
- `{"type": "user", "message": {"content": "user prompt text"}}`
- Token usage: `record.message.usage.input_tokens` / `.output_tokens`

### Claude Code Hooks
Configured in `~/.claude/settings.json`. Key events:
- `SessionStart` — fires for every new session including subagents
- `PostToolUse` with `matcher` — fires after specific tool completes
- `UserPromptSubmit` — fires when user sends a prompt
- `Stop` — fires when session ends
- Hook stdout on exit 0 is injected into Claude's context (SessionStart, UserPromptSubmit)
- Exit 2 blocks the action

### Database Schema (key tables)
```sql
-- memory_sources: one row per indexed file
-- memory_chunks: chunks with embeddings, tsvectors, block_type, metadata
-- block_types: code, raw, file_content, semantic_summary, structural_signature,
--              decision_context, user_intent, session_summary, bash_output, grep_result
```

### MCP Server
- Uses Python `mcp` SDK in stdio mode
- Exposes `rag_search` tool with params: query, token_budget, project_filter
- Configured in settings.json under `mcpServers.claude-rag`

---

## QUALITY STANDARDS

- Type hints on all functions
- Google-style docstrings on public functions/classes
- Pytest tests for every module
- All magic numbers in Config class
- Idempotent operations (re-ingesting same file is safe)
- Hooks must complete in <500ms (use async queue for heavy work)
- All file paths must work on Windows (use pathlib or raw strings)
