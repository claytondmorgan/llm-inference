# Claude Code RAG System — Project Instructions

## What This Project Is
A local RAG pipeline that intercepts Claude Code's memory files, enriches and embeds
them into PostgreSQL (pgvector), and exposes hybrid search via an MCP server. This
system lives inside the existing `llm-inference` repository and REUSES existing modules.

## CRITICAL: Existing Code to Reuse (DO NOT REBUILD)

The parent `llm-inference/` project contains working implementations. Always import
from these rather than rewriting:

### Embedding System -> WRAP, don't rewrite
- `../lambda-s3-trigger/ingestion-worker/app/embeddings.py`
  - `EmbeddingGenerator` class with batch support, mean pooling, normalization

### Database Patterns -> EXTEND, don't rewrite
- `../lambda-s3-trigger/ingestion-worker/app/database.py`
  - `DatabaseManager` with connection management, bulk insert, job tracking
- `../schema_legal.sql`
  - pgvector columns, HNSW indexes, GIN indexes, generated tsvector columns
- `../migrate_schema.py`
  - Idempotent schema migration pattern

### Hybrid RRF Search -> ADAPT the SQL, don't rewrite
- `../app.py` lines 1139-1191
  - Complete semantic CTE + keyword CTE + FULL OUTER JOIN + RRF scoring
- `../app.py` lines 1084-1108
  - Dynamic filter builder pattern

## Project Structure
```
claude-rag/
├── src/claude_rag/
│   ├── config.py           # Config with env var overrides
│   ├── db/                 # Schema, manager, migration
│   ├── embeddings/         # Abstract provider + local wrapper
│   ├── ingestion/          # Parser, chunker, watcher, pipeline
│   ├── search/             # Semantic, keyword, hybrid, formatter
│   ├── hooks/              # Claude Code hook handlers + async queue
│   ├── mcp_server/         # MCP server exposing rag_search tool
│   └── cli.py              # Health check, manual ingest/search/worker
├── demos/                  # Poker app demo
└── tests/                  # Pytest suite with fixtures
```

## CLI Commands
```bash
python -m claude_rag health          # Check system health
python -m claude_rag ingest <path>   # Ingest a file or directory
python -m claude_rag search <query>  # Search the RAG database
python -m claude_rag watch           # Start file watcher daemon
python -m claude_rag serve           # Start MCP server (stdio)
python -m claude_rag worker          # Start hook queue worker
python -m claude_rag worker --once   # Drain queue then exit
```

## Quality Standards
- Type hints on all functions
- Google-style docstrings on all public functions/classes
- Tests for every module (pytest)
- Config-driven: all magic numbers in Config class
- Idempotent operations (re-ingesting same file is safe)

## RAG-First Context Strategy

When starting any coding task:
1. ALWAYS call `rag_search` first with a description of the current task
2. Review the returned context for relevant past decisions, patterns, and code references
3. If the RAG context covers the needed information, proceed WITHOUT reading additional files
4. Only fall back to Read/Bash tools if:
   - RAG returned no results (empty context)
   - RAG results are clearly irrelevant to the current task
   - You need specific file contents not captured in the memory system
5. When reading files as fallback, prefer targeted reads (specific files/line ranges) over broad exploration

## Environment Setup
```bash
# Required for local PostgreSQL (Docker)
docker run -d --name claude-rag-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=claude_rag -p 5433:5432 pgvector/pgvector:pg17

# Run migration
PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=src python -m claude_rag.db.migrate

# Run tests
PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=src python -m pytest tests/ -v
```

## MCP Server Configuration
Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "claude-rag": {
      "command": "python",
      "args": ["-m", "claude_rag.mcp_server.server"],
      "cwd": "C:\\Users\\ClayMorgan\\PycharmProjects\\llm-inference\\claude-rag",
      "env": {
        "PYTHONPATH": "src",
        "PGPASSWORD": "postgres"
      }
    }
  }
}
```

## Hook Configuration (Phase 2A)
Add to `~/.claude/settings.json` or `.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "python -m claude_rag.hooks.post_tool_use", "timeout": 5 }]
      },
      {
        "matcher": "Bash|Grep",
        "hooks": [{ "type": "command", "command": "python -m claude_rag.hooks.post_tool_use", "timeout": 5 }]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "python -m claude_rag.hooks.user_prompt", "timeout": 5 }]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "python -m claude_rag.hooks.session_end", "timeout": 30 }]
      }
    ]
  }
}
```
Start the background worker to process hook events:
```bash
PGPASSWORD=postgres PYTHONPATH=src python -m claude_rag worker
```
