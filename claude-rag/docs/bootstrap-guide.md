# Bootstrap Guide: Launching the Claude Code RAG Project

## TL;DR — The 10-Minute Setup

1. Create `claude-rag/` folder inside your `llm-inference` project
2. Drop in the CLAUDE.md with the orchestration plan
3. Open Claude Code in PyCharm, use `/plan` mode first
4. Then tell Claude to dispatch subagents for parallel workstreams
5. Use agent teams only for the integration phases

---

## Step 0: Choose Your Dispatch Mechanism

You have two options. Here's when to use each:

### Subagents (recommended for most of this project)
- Workers report results back to the lead — they can't talk to each other
- Cheaper (~1x per agent vs ~2-4x for teams)
- Perfect for independent modules: parser, embeddings, search, DB
- Workers finish and are gone — no idle overhead

### Agent Teams (use for integration phases only)
- Workers can message each other and share a task list
- More expensive (each teammate is a full Claude Code session)
- Use when workers need to coordinate: e.g., wiring the pipeline (Phase 2→3 convergence)
- Experimental — enable with: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

**Recommendation for this project:** Start with subagents for Phases 0-2 (independent modules).
Consider agent teams for Phase 3+ if integration gets complex.

---

## Step 1: Create the Project Structure (You Do This in PyCharm)

In PyCharm, inside your existing `llm-inference` project:

```
1. Right-click llm-inference/ → New → Directory → "claude-rag"
2. Inside claude-rag/, create:
   - src/claude_rag/__init__.py  (empty)
   - tests/__init__.py           (empty)
   - pyproject.toml              (see below)
```

Minimal `pyproject.toml`:
```toml
[project]
name = "claude-rag"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "psycopg2-binary>=2.9.9",
    "sentence-transformers>=3.3.0",
    "watchdog>=4.0.0",
    "tiktoken>=0.7.0",
    "mcp>=1.0.0",
    "pydantic>=2.5.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4.0", "mypy>=1.10"]
api = ["httpx>=0.27.0"]  # For API embedding provider

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

---

## Step 2: Create the CLAUDE.md (This Is How You Give Claude the Plan)

Create a file at `llm-inference/claude-rag/CLAUDE.md` with the following content.
This is what Claude Code reads on startup — it's the project-level instruction file.

```markdown
# Claude Code RAG System — Project Instructions

## What This Project Is
A local RAG pipeline that intercepts Claude Code's memory files, enriches and embeds
them into PostgreSQL (pgvector), and exposes hybrid search via an MCP server. This
system lives inside the existing `llm-inference` repository and REUSES existing modules.

## CRITICAL: Existing Code to Reuse (DO NOT REBUILD)

The parent `llm-inference/` project contains working implementations. Always import
from these rather than rewriting:

### Embedding System → WRAP, don't rewrite
- `../lambda-s3-trigger/ingestion-worker/app/embeddings.py`
  - `EmbeddingGenerator` class with batch support, mean pooling, normalization

### Database Patterns → EXTEND, don't rewrite
- `../lambda-s3-trigger/ingestion-worker/app/database.py`
  - `DatabaseManager` with connection management, bulk insert, job tracking
- `../schema_legal.sql`
  - pgvector columns, HNSW indexes, GIN indexes, generated tsvector columns
- `../migrate_schema.py`
  - Idempotent schema migration pattern

### Hybrid RRF Search → ADAPT the SQL, don't rewrite
- `../app.py` lines 1139-1191
  - Complete semantic CTE + keyword CTE + FULL OUTER JOIN + RRF scoring
- `../app.py` lines 1084-1108
  - Dynamic filter builder pattern

### Ingestion Pipeline → FOLLOW the pattern
- `../lambda-s3-trigger/ingestion-worker/app/processor.py`
  - Batch processing, field detection, embed + insert pipeline

## Project Structure
```
claude-rag/
├── src/claude_rag/
│   ├── config.py           # Config with env var overrides
│   ├── db/                 # Schema, manager, migration
│   ├── embeddings/         # Abstract provider + local wrapper
│   ├── ingestion/          # Parser, chunker, watcher, pipeline
│   ├── search/             # Semantic, keyword, hybrid, formatter
│   ├── mcp_server/         # MCP server exposing rag_search tool
│   └── cli.py              # Health check, manual ingest/search
└── tests/                  # Pytest suite with fixtures
```

## Quality Standards
- Type hints on all functions
- Google-style docstrings on all public functions/classes
- Tests for every module (pytest)
- Config-driven: all magic numbers in Config class
- Idempotent operations (re-ingesting same file is safe)

## Sub-Agent Routing Rules
When dispatching work to sub-agents:

**Parallel dispatch** (these modules are independent):
- `embeddings/` — no shared files with other modules
- `db/` — no shared files with other modules
- `ingestion/parser.py` + `ingestion/chunker.py` — independent of db/embeddings
- `search/` — depends on db schema but not on ingestion code

**Sequential dispatch** (these depend on prior work):
- `ingestion/pipeline.py` — needs parser + chunker + embeddings + db all done
- `ingestion/watcher.py` → `ingestion/pipeline.py` (watcher feeds pipeline)
- `mcp_server/` — needs search pipeline complete
- `cli.py` — needs everything else done

**Background dispatch** (research, no file modifications):
- Investigating Claude Code memory file format/locations
- Reading existing codebase modules before implementation
```

---

## Step 3: Open Claude Code and Plan First

Open Claude Code in PyCharm (the Claude plugin terminal). Navigate to the `claude-rag/` directory.

### First Session: Plan Mode

Start with plan mode to let Claude study the codebase and internalize the plan:

```
/plan
```

Then paste this prompt:

```
Read the CLAUDE.md in this directory and the agent orchestration plan below. Study
the existing code in the parent llm-inference/ project — especially the files listed
in CLAUDE.md under "Existing Code to Reuse." Then create a detailed implementation
plan with tasks, dependencies, and file assignments.

Here is the full orchestration plan:
[paste the contents of agent-orchestration-script.md here]
```

Claude will produce a plan. **Review it.** Make sure it correctly identifies the existing
code to reuse. Adjust if needed.

---

## Step 4: Dispatch Phase 0 (Single Agent — Setup)

Phase 0 is setup work that should be done sequentially by a single agent:

```
Execute Phase 0 from the plan:
1. Create the full project directory structure under src/claude_rag/ with all
   __init__.py files as specified in CLAUDE.md
2. Create config.py with local DB support (PGHOST/PGPORT/PGUSER/PGPASSWORD env vars)
   modeled after ../lambda-s3-trigger/ingestion-worker/app/config.py
3. Create the database schema (schema.sql) and migration script modeled after
   ../schema_legal.sql and ../migrate_schema.py
4. Run the migration against the local claude_rag database

Verify: `python -c "from claude_rag.config import Config; print(Config())"` works
```

---

## Step 5: Dispatch Parallel Workstreams (Subagents)

Once Phase 0 is verified, dispatch parallel subagents. Use this prompt:

```
Phase 0 is complete. Now dispatch parallel sub-agents for the independent workstreams.
Each sub-agent should study the existing code referenced in CLAUDE.md before writing
anything new.

Sub-agent 1 — Ingestion (parser + chunker):
- Research Claude Code memory format (CLAUDE.md locations, session logs)
- Build src/claude_rag/ingestion/parser.py — parse CLAUDE.md into structured blocks
- Build src/claude_rag/ingestion/chunker.py — chunk with code-fence awareness
- Build tests/test_parser.py and tests/test_chunker.py with sample fixtures
- Study ../lambda-s3-trigger/ingestion-worker/app/processor.py for patterns

Sub-agent 2 — Embeddings + DB:
- Build src/claude_rag/embeddings/base.py — abstract EmbeddingProvider interface
- Build src/claude_rag/embeddings/local.py — wrap ../lambda-s3-trigger/ingestion-worker/app/embeddings.py
- Build src/claude_rag/db/manager.py — extend DatabaseManager pattern from ../lambda-s3-trigger/ingestion-worker/app/database.py
- Build tests/test_embeddings.py and tests/test_db.py
- Import and delegate to existing EmbeddingGenerator, do NOT duplicate

Sub-agent 3 — Search:
- Build src/claude_rag/search/semantic.py — adapt SQL from ../app.py lines 586-618
- Build src/claude_rag/search/keyword.py — adapt SQL from ../app.py lines 1157-1167
- Build src/claude_rag/search/hybrid.py — adapt RRF SQL from ../app.py lines 1146-1191
- Build src/claude_rag/search/formatter.py — token-budget-aware context formatter
- Build tests/test_search.py

All sub-agents: study the referenced existing files BEFORE writing code.
Run tests after implementation. Report back with results.
```

---

## Step 6: Integration Phase (After Subagents Complete)

Once all three subagents report success, wire them together:

```
All three workstreams are complete. Now wire the integration:

1. Build src/claude_rag/ingestion/watcher.py — watchdog file monitor with
   change detection (SHA-256 hashing)
2. Build src/claude_rag/ingestion/pipeline.py — orchestrate:
   watcher → parser → chunker → embedder → storage
3. Test end-to-end: create a sample CLAUDE.md file, run the pipeline,
   verify chunks appear in the database with embeddings and tsvectors
4. Test search: run hybrid_search against the ingested chunks
```

---

## Step 7: MCP Server & Claude Code Integration

```
Build the MCP server and integrate with Claude Code:

1. Build src/claude_rag/mcp_server/server.py using the mcp Python SDK
   - Expose a "rag_search" tool with query, token_budget, project_filter params
   - Wire it to the hybrid search pipeline + context formatter
2. Build src/claude_rag/cli.py with health, ingest, search, watch commands
3. Create the Claude Code MCP config entry for settings.json
4. Test: start the MCP server in stdio mode, send tools/list and tools/call
```

---

## Step 8: Verify the Full Loop

```
Run the complete verification:
1. python -m claude_rag health → all green
2. python -m claude_rag ingest <path-to-sample-claude-md> → chunks in DB
3. python -m claude_rag search "authentication module" → relevant results
4. Start MCP server → Claude Code sees rag_search tool
5. Give Claude Code a task → verify it calls rag_search first
```

---

## Tips for Success

### Token Cost Management
- Use `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-5-20250929` to run sub-agents on
  Sonnet instead of Opus — significantly cheaper for focused implementation tasks
- Only use Opus for the lead agent's planning and integration work

### If a Sub-Agent Gets Stuck
- Check if it studied the existing code first (most issues come from not reading
  the existing implementations)
- Provide the specific file path and line range it should study

### If Tests Fail
- Have the lead agent review the failure and dispatch a focused fix sub-agent
- Don't have the original sub-agent retry — spawn a fresh one with the error context

### PyCharm-Specific Notes
- The Claude plugin in PyCharm uses the same Claude Code engine as the CLI
- Sub-agents work the same way — they spawn within the session
- Agent teams (if you enable them) will spawn additional terminal sessions
- Make sure your terminal in PyCharm has the right Python environment activated

### Environment Variables to Set
```bash
# Required for local PostgreSQL
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=your_password
export PGDATABASE=claude_rag

# Optional: cheaper sub-agents
export CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-5-20250929

# Optional: enable agent teams (experimental)
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```
