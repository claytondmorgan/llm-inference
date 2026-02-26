# Claude Code RAG System — Agent Team Orchestration Script

## TEAM LEADER: READ THIS FIRST

This document is the master plan for building a local RAG system that integrates with Claude Code. A team of worker agents will execute this plan in parallel where possible. Your job as team leader is to:

1. Read this entire document
2. Understand the dependency graph (which tasks block which)
3. Dispatch worker agents to independent workstreams
4. Verify each milestone's acceptance criteria before unblocking downstream work
5. Coordinate integration points where workstreams converge

---

## PROJECT OVERVIEW

**Goal:** Build a local RAG pipeline that:
- Watches Claude Code's memory files (CLAUDE.md, session logs) for changes
- Parses, chunks, and embeds them into PostgreSQL (pgvector)
- Exposes hybrid search (semantic + keyword via RRF) through an MCP server tool
- Claude Code queries this RAG system FIRST before falling back to conventional file exploration
- Maximizes relevant context per token in the context window

**Stack:** Python, PostgreSQL + pgvector, sentence-transformers (local, swappable), MCP SDK

**CRITICAL: This is NOT a greenfield project.** The existing codebase at `C:\Users\ClayMorgan\PycharmProjects\llm-inference` contains working implementations of embeddings, pgvector search, hybrid RRF search, RAG, and database management. **Study and reuse these modules.** Do not rebuild what already exists.

---

## EXISTING CODEBASE INVENTORY

Before writing ANY code, every worker agent MUST study the relevant existing files listed below. The team leader should ensure agents have read and understood these before starting work.

### Embedding System (REUSE)
**File:** `lambda-s3-trigger/ingestion-worker/app/embeddings.py`
- `EmbeddingGenerator` class with `generate_single()` and `generate_batch()` methods
- Uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim) by default
- Batch processing with configurable batch size
- Mean pooling + L2 normalization
- **Action:** Wrap this in an abstract provider interface; do NOT rewrite the core logic.

**File:** `app.py` lines 212-216
- `get_legal_embedding()` uses `SentenceTransformer` directly (768-dim ModernBERT)
- Shows the pattern for using a different model via `sentence_transformers.SentenceTransformer`
- **Action:** Use this as the reference for the provider swap pattern.

### Database Layer (REUSE)
**File:** `lambda-s3-trigger/ingestion-worker/app/database.py`
- `DatabaseManager` class with connection management, bulk insert, job tracking
- Uses `psycopg2` with `RealDictCursor` and `execute_values` for bulk ops
- Pattern: `_get_credentials()` → `_get_connection()` → operations → close
- **Action:** Extend this class (or create a subclass) for the new schema. Add local config support (env vars or config file) alongside AWS Secrets Manager.

**File:** `lambda-s3-trigger/ingestion-worker/app/config.py`
- Config class pattern with env var overrides and sensible defaults
- **Action:** Create a similar config for the RAG system.

### Hybrid Search with RRF (REUSE)
**File:** `app.py` lines 1139-1191
- Complete hybrid search implementation:
  - `semantic` CTE: cosine similarity via `content_embedding <=> query_vec::vector`, with `ROW_NUMBER()` for ranking
  - `keyword` CTE: `ts_rank()` + `plainto_tsquery()` against `content_tsv` column
  - `FULL OUTER JOIN` on id, RRF score: `1.0/(60 + sem_rank) + 1.0/(60 + kw_rank)`
  - Tags each result as 'hybrid', 'semantic', or 'keyword' based on which CTE matched
- **Action:** Adapt this SQL pattern for the `memory_chunks` table. The structure is identical — just change table/column names.

### Filter Builder (REUSE)
**File:** `app.py` lines 1084-1108
- `_build_legal_filters()` — dynamic WHERE clause builder from optional filter params
- **Action:** Create an equivalent for memory chunk filters (project, language, file references, date range).

### Schema Patterns (REUSE)
**File:** `schema_legal.sql`
- Complete reference for: pgvector columns, HNSW indexes, GIN indexes on tsvector, generated tsvector columns, B-tree metadata indexes
- **Action:** Model the new `memory_chunks` schema after this pattern.

**File:** `migrate_schema.py`
- Schema migration with step-by-step verification and rollback handling
- **Action:** Create a similar migration for the RAG system tables.

### Ingestion Pipeline (REUSE PATTERN)
**File:** `lambda-s3-trigger/ingestion-worker/app/processor.py`
- `CSVProcessor` class: batch processing, field detection, embed + insert pipeline
- Pattern: detect fields → extract records → embed in batches → bulk insert
- **Action:** Adapt this pattern for memory file processing (parser → chunker → embed → insert).

### Pydantic Models (REUSE PATTERN)
**File:** `app.py` lines 54-158
- `SearchRequest`, `SearchResult`, `LegalSearchRequest`, `LegalSearchResult`, `RAGRequest`, `RAGResponse`
- **Action:** Create equivalent models for memory search requests/results.

---

## REVISED TASK PLAN (accounting for existing code)

Tasks marked 🔄 are adaptations of existing code. Tasks marked 🆕 are net-new.

---

### PHASE 0 — Project Setup & Local Environment

#### T0.1 🆕 Create project structure within llm-inference repo
Create a new `claude-rag/` subdirectory inside the existing `llm-inference` project:
```
llm-inference/
├── claude-rag/
│   ├── pyproject.toml          # or requirements.txt
│   ├── src/
│   │   └── claude_rag/
│   │       ├── __init__.py
│   │       ├── config.py
│   │       ├── db/
│   │       │   ├── __init__.py
│   │       │   ├── manager.py
│   │       │   ├── schema.sql
│   │       │   └── migrate.py
│   │       ├── embeddings/
│   │       │   ├── __init__.py
│   │       │   ├── base.py         # Abstract provider
│   │       │   └── local.py        # Wraps existing EmbeddingGenerator
│   │       ├── ingestion/
│   │       │   ├── __init__.py
│   │       │   ├── parser.py
│   │       │   ├── chunker.py
│   │       │   └── watcher.py
│   │       ├── search/
│   │       │   ├── __init__.py
│   │       │   ├── semantic.py
│   │       │   ├── keyword.py
│   │       │   ├── hybrid.py
│   │       │   └── formatter.py
│   │       ├── mcp_server/
│   │       │   ├── __init__.py
│   │       │   └── server.py
│   │       └── cli.py
│   └── tests/
│       ├── conftest.py
│       ├── test_parser.py
│       ├── test_chunker.py
│       ├── test_embeddings.py
│       ├── test_search.py
│       └── test_pipeline.py
```
- **Test:** `cd claude-rag && python -c "import claude_rag"` succeeds.

#### T0.2 🆕 Create local config module
Create `config.py` modeled after existing `lambda-s3-trigger/ingestion-worker/app/config.py`. Support two modes:
1. **Local mode (default):** DB credentials from env vars (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) or a `.env` file
2. **AWS mode:** DB credentials from Secrets Manager (for compatibility with existing infra)

Also configure:
- `EMBEDDING_MODEL` (default: `sentence-transformers/all-MiniLM-L6-v2`)
- `EMBEDDING_DIM` (default: 384)
- `CHUNK_SIZE` (default: 512 tokens)
- `CHUNK_OVERLAP` (default: 50 tokens)
- `CLAUDE_MEMORY_DIRS` (list of directories to watch)
- `SEARCH_TOP_K` (default: 10)
- `RELEVANCE_THRESHOLD` (default: 0.3)
- `CONTEXT_TOKEN_BUDGET` (default: 4096)

- **Test:** `from claude_rag.config import Config; c = Config(); assert c.EMBEDDING_DIM == 384`

#### T0.3 🔄 Provision local PostgreSQL with pgvector
Use an existing local PostgreSQL installation or Docker. Enable pgvector. Create the `claude_rag` database. Verify with the same pattern from `setup_pgvector.py`.
- **Test:** Connect to `claude_rag` DB, run `SELECT * FROM pg_extension WHERE extname = 'vector';` — returns a row.

> **✅ Milestone M0 — Project Scaffolded, DB Ready**

---

### PHASE 1 — Memory Ingestion Pipeline

#### T1.1 🆕 Research Claude Code memory format
Investigate Claude Code's local file structure. Document:
- Location of `CLAUDE.md` (project-level: `<project>/.claude/CLAUDE.md`, user-level: `~/.claude/CLAUDE.md`)
- Location of session transcripts/conversation logs if any exist on disk
- Location of `.claude/settings.json` and other config files
- File format (markdown, JSON, etc.) and update patterns (append, overwrite)
- What information they contain (tool calls, reasoning, code output, decisions)

Create `docs/memory-format-spec.md` documenting findings with example content.
- **Test:** Spec document exists with at least 3 file locations and example content from each.

#### T1.2 🆕 Build memory file parser
Create `src/claude_rag/ingestion/parser.py`:
- `parse_claude_md(file_path: str) -> list[ParsedBlock]` — parse CLAUDE.md into structured blocks
- `parse_session_log(file_path: str) -> list[ParsedBlock]` — parse session transcripts
- `ParsedBlock` dataclass with fields: `content: str`, `block_type: str` (e.g., "instruction", "code", "reasoning", "tool_output"), `metadata: dict` (timestamps, file references, etc.)
- Handle markdown sections, code fences, and tool call blocks

**Study first:** The field detection logic in `lambda-s3-trigger/ingestion-worker/app/processor.py` lines 95-117 for pattern inspiration on auto-detecting content types.

- **Test:** Feed 3+ sample CLAUDE.md files → get back list of `ParsedBlock` with correct types. Code fences are identified as `block_type="code"`.

#### T1.3 🆕 Build text chunker
Create `src/claude_rag/ingestion/chunker.py`:
- `chunk_blocks(blocks: list[ParsedBlock], chunk_size: int, overlap: int) -> list[Chunk]`
- `Chunk` dataclass: `content: str`, `index: int`, `source_blocks: list[int]`, `metadata: dict`
- Chunking rules:
  - Never split inside a code fence
  - Prefer splitting at paragraph/section boundaries
  - If a single block exceeds `chunk_size`, split at sentence boundaries
  - Overlap region is from the end of the previous chunk
- Use `tiktoken` (cl100k_base) for accurate token counting

- **Test:** A 2000-token document → 4-5 chunks. No code block is ever split. `sum(len(c.content) for c in chunks)` > original (due to overlap).

#### T1.4 🆕 Unit tests for parser and chunker
Formalize T1.2 and T1.3 tests as pytest fixtures with sample data files in `tests/fixtures/`.
- **Test:** `pytest tests/test_parser.py tests/test_chunker.py` — all green.

> **✅ Milestone M1 — Parser & Chunker Ready**

#### T2.1 🆕 Build file watcher
Create `src/claude_rag/ingestion/watcher.py`:
- Use `watchdog` library
- `MemoryFileWatcher` class that monitors configured directories
- Fires callbacks on file create/modify events
- Filters to only `.md` and relevant file types
- Debounce rapid successive events (500ms window)

- **Test:** Start watcher, create a `.md` file → callback fires with correct path within 1 second.

#### T2.2 🆕 Build change detection
Add to watcher module:
- Track file SHA-256 hashes in a small SQLite DB (or JSON file) at `~/.claude-rag/state.json`
- On file event: compute hash, compare with stored hash
- Only trigger processing if hash changed
- Store: `{file_path: str, hash: str, last_processed: datetime}`

- **Test:** Modify file → detected. Touch without modifying → ignored. New file → detected.

> **✅ Milestone M2 — File Watcher Ready**

---

### PHASE 2 — Embedding & Storage

#### T3.1 🔄 Create abstract embedding provider
Create `src/claude_rag/embeddings/base.py`:
```python
from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_single(self, text: str) -> list[float]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...
```

Create `src/claude_rag/embeddings/local.py`:
- `LocalEmbeddingProvider(EmbeddingProvider)` that wraps the EXISTING `EmbeddingGenerator` from `lambda-s3-trigger/ingestion-worker/app/embeddings.py`
- Import and delegate to `EmbeddingGenerator.generate_batch()` and `EmbeddingGenerator.generate_single()`
- Do NOT duplicate the mean pooling / batch logic — import it

- **Test:** `provider = LocalEmbeddingProvider(); result = provider.embed(["hello"]); assert len(result[0]) == 384`

#### T3.2 🆕 Add API embedding provider stub
Create `src/claude_rag/embeddings/api.py`:
- `APIEmbeddingProvider(EmbeddingProvider)` with constructor taking `api_key`, `model_name`, `base_url`
- Implement for OpenAI-compatible API (`/v1/embeddings`)
- Leave as optional — system works without it

- **Test:** Class instantiates. If no API key, raises clear error on `embed()`. If mocked, returns correct shape.

> **✅ Milestone M3 — Embedding Providers Ready**

#### T4.1 🔄 Create database schema
Create `src/claude_rag/db/schema.sql` modeled after existing `schema_legal.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_sources (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(50) NOT NULL,       -- 'claude_md', 'session_log', 'settings'
    project_path TEXT,                     -- project root this file belongs to
    last_ingested_at TIMESTAMP DEFAULT NOW(),
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memory_chunks (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES memory_sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    block_type VARCHAR(50),               -- 'instruction', 'code', 'reasoning', 'tool_output'
    metadata JSONB DEFAULT '{}',          -- file_references, language, intent, etc.

    -- Embeddings
    embedding vector(384),                -- matches EMBEDDING_DIM config

    -- Full-text search
    content_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(source_id, chunk_index)
);

-- HNSW index for vector search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON memory_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON memory_chunks USING gin(content_tsv);

-- B-tree indexes for metadata filtering
CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON memory_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_block_type ON memory_chunks(block_type);
CREATE INDEX IF NOT EXISTS idx_sources_project ON memory_sources(project_path);
CREATE INDEX IF NOT EXISTS idx_sources_file_type ON memory_sources(file_type);

-- JSONB index for metadata queries
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON memory_chunks USING gin(metadata);
```

- **Test:** Run schema SQL against `claude_rag` database. All tables and indexes created. `\d memory_chunks` shows all columns.

#### T4.2 🔄 Build database manager
Create `src/claude_rag/db/manager.py` extending the pattern from `lambda-s3-trigger/ingestion-worker/app/database.py`:

Must support:
- `upsert_source(file_path, file_hash, file_type, project_path) -> source_id`
- `upsert_chunks(source_id, chunks: list[ChunkRecord])` — delete old chunks for source, insert new
- `delete_source(source_id)` — cascading delete
- `get_source_by_path(file_path) -> SourceRecord | None`
- `get_chunk_count() -> int`
- `get_source_count() -> int`

Use the EXISTING `_get_credentials()` and `_get_connection()` patterns but add local config support:
```python
def _get_connection(self):
    if self.config.DB_MODE == "local":
        return psycopg2.connect(
            host=self.config.PGHOST,
            database=self.config.PGDATABASE,
            user=self.config.PGUSER,
            password=self.config.PGPASSWORD,
            port=self.config.PGPORT
        )
    else:
        # AWS Secrets Manager path (existing pattern)
        creds = self._get_credentials()
        return psycopg2.connect(...)
```

- **Test:** Insert source + 5 chunks → query confirms 5 rows. Re-upsert → still 5 rows. Delete source → 0 chunk rows (cascade).

#### T4.3 🔄 Build schema migration script
Create `src/claude_rag/db/migrate.py` modeled after existing `migrate_schema.py`:
- Step-by-step migration with verification
- Idempotent (safe to run multiple times)
- Reports current state before and after

- **Test:** Run migration twice → no errors, same state. Tables and indexes all present.

> **✅ Milestone M4 — Database Ready**

#### T5.1 🆕 Wire end-to-end ingestion pipeline
Create `src/claude_rag/ingestion/pipeline.py`:
- `IngestionPipeline` class that orchestrates: parser → chunker → embedder → storage
- Method: `ingest_file(file_path: str) -> IngestionResult`
- `IngestionResult` dataclass: `source_id`, `chunks_created`, `duration_ms`
- On re-ingestion of same file: check hash, skip if unchanged, re-process if changed

- **Test:** `pipeline.ingest_file("sample_claude.md")` → DB contains expected chunks with embeddings and tsvectors.

#### T5.2 🆕 Wire watcher to pipeline
Connect file watcher events to the ingestion pipeline:
- Watcher detects change → calls `pipeline.ingest_file()`
- Add a simple event queue to avoid concurrent processing of same file

- **Test:** Start watcher daemon. Drop a new `.md` file → within 10 seconds, query DB shows new chunks with embeddings.

> **✅ Milestone M5 — End-to-End Ingestion Works**

---

### PHASE 3 — Search & Retrieval

#### T6.1 🔄 Build semantic search
Create `src/claude_rag/search/semantic.py`:
- `semantic_search(query: str, top_k: int, provider: EmbeddingProvider, db: DatabaseManager) -> list[SearchResult]`
- Adapt the SQL pattern from `app.py` line 586-618 (the documents search) but targeting `memory_chunks`
- Use `1 - (embedding <=> query_vec::vector) as similarity`

- **Test:** Ingest known content. Query with related text → top result matches expected chunk.

#### T6.2 🔄 Build keyword search
Create `src/claude_rag/search/keyword.py`:
- `keyword_search(query: str, top_k: int, db: DatabaseManager) -> list[SearchResult]`
- Use `plainto_tsquery()` and `ts_rank()` against `content_tsv` — same pattern as `app.py` line 1157-1167

- **Test:** Query "pgvector schema migration" → returns chunks containing those terms.

#### T6.3 🔄 Build hybrid search with RRF
Create `src/claude_rag/search/hybrid.py`:
- `hybrid_search(query: str, top_k: int, alpha: float, ...) -> list[SearchResult]`
- **Directly adapt** the SQL from `app.py` lines 1146-1191:
  - `semantic` CTE with `ROW_NUMBER()` ranking
  - `keyword` CTE with `ts_rank()` ranking
  - `FULL OUTER JOIN` with RRF: `1.0/(60 + sem_rank) + 1.0/(60 + kw_rank)`
- Add optional metadata filters using the `_build_legal_filters()` pattern from `app.py` lines 1084-1108

`SearchResult` dataclass: `chunk_id`, `content`, `similarity`, `search_method`, `metadata`, `source_path`

- **Test:** Hybrid search on eval set achieves recall@5 ≥ semantic-only. Results tagged correctly as 'hybrid'/'semantic'/'keyword'.

> **✅ Milestone M6 — Search Works**

#### T7.1 🆕 Build result deduplication
Add to search module:
- Detect near-duplicate chunks (overlapping content from same source)
- Use Jaccard similarity on token sets with threshold 0.7
- Keep the highest-ranked instance

- **Test:** Search returning 3 overlapping chunks → deduplicated to 1-2.

#### T7.2 🆕 Build token-budget-aware context formatter
Create `src/claude_rag/search/formatter.py`:
- `format_context(results: list[SearchResult], token_budget: int) -> str`
- Greedy packing: iterate results by rank, add to output until budget exhausted
- Format each result as:
  ```
  [Source: <file_path> | Type: <block_type> | Relevance: <similarity>]
  <content>
  ---
  ```
- Use `tiktoken` (cl100k_base) for token counting
- If a result would exceed remaining budget, try truncating it to fit; if still too large, skip

- **Test:** 10 results + budget 2000 tokens → output ≤ 2000 tokens. Highest-ranked results included first.

#### T7.3 🆕 Add relevance threshold filtering
Add to search pipeline:
- Discard results below `Config.RELEVANCE_THRESHOLD` (default 0.3)
- Return empty context string if no results pass threshold

- **Test:** Query with no relevant content → empty or near-empty context returned.

> **✅ Milestone M7 — Search Pipeline Complete**

---

### PHASE 4 — MCP Server & Claude Code Integration

#### T8.1 🆕 Build MCP server
Create `src/claude_rag/mcp_server/server.py`:
- Use the `mcp` Python SDK (pip install mcp)
- Expose a single tool: `rag_search`
  - Input schema: `{ query: string, token_budget?: int, project_filter?: string, block_type_filter?: string }`
  - Output: formatted context string from the search pipeline
- Run in stdio mode (for Claude Code integration)

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("claude-rag")

@server.list_tools()
async def list_tools():
    return [Tool(
        name="rag_search",
        description="Search local RAG database of Claude Code memories and session history. "
                    "Returns relevant context from past coding sessions. "
                    "ALWAYS call this first before reading files directly.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language description of what context you need"},
                "token_budget": {"type": "integer", "description": "Max tokens for context (default: 4096)", "default": 4096},
                "project_filter": {"type": "string", "description": "Filter to specific project path"},
            },
            "required": ["query"]
        }
    )]

@server.call_tool()
async def call_tool(name, arguments):
    if name == "rag_search":
        context = search_pipeline.search(
            query=arguments["query"],
            token_budget=arguments.get("token_budget", 4096),
            project_filter=arguments.get("project_filter")
        )
        return [TextContent(type="text", text=context)]
```

- **Test:** Run MCP server in stdio mode, send a `tools/list` JSON-RPC → receive tool definition. Send a `tools/call` → receive context string.

#### T8.2 🆕 Add MCP server to Claude Code config
Create installation instructions and a setup script that adds the MCP server to Claude Code's config:

For Claude Code (CLI), add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "claude-rag": {
      "command": "python",
      "args": ["-m", "claude_rag.mcp_server.server"],
      "cwd": "C:\\Users\\ClayMorgan\\PycharmProjects\\llm-inference\\claude-rag"
    }
  }
}
```

- **Test:** Start Claude Code. The `rag_search` tool appears in available tools.

#### T8.3 🆕 Write CLAUDE.md RAG-first instructions
Create a `CLAUDE.md` snippet (to be added to project-level CLAUDE.md files) that instructs Claude Code:

```markdown
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
```

- **Test:** Instruction content is valid markdown. Added to a project's CLAUDE.md.

#### T8.4 🆕 End-to-end integration test
With ingested data in DB:
1. Give Claude Code a coding task related to previously-ingested sessions
2. Observe that `rag_search` is called before file reads
3. Verify the context returned is relevant

- **Test:** In Claude Code transcript, `rag_search` appears before any `Read`/`Bash` tool calls.

#### T8.5 🆕 Test fallback behavior
Give Claude Code a task with no relevant RAG results. Verify graceful fallback.
- **Test:** Claude Code calls `rag_search`, gets empty/low results, then proceeds with normal file exploration.

> **✅ Milestone M8 — MCP Server Operational, RAG-First Active**

---

### PHASE 5 — Enrichment & Hardening

#### T9.1 🆕 Build metadata extractor
Create enrichment logic in the parser/chunker pipeline:
- Extract file paths referenced in content (regex for common path patterns)
- Detect programming language from code blocks (use fence language hints or heuristics)
- Classify intent: "bug-fix", "refactor", "new-feature", "investigation", "configuration"
- Extract project name from file path context
- Store all extracted metadata in the chunk's `metadata` JSONB field

- **Test:** Chunk referencing `src/auth.py` with Python code → `metadata.files = ["src/auth.py"], metadata.language = "python"`.

#### T9.2 🆕 Add metadata filters to search
Extend `hybrid_search` to accept optional metadata filters using JSONB queries:
- `project_filter`: `WHERE metadata->>'project' = ?`
- `language_filter`: `WHERE metadata->>'language' = ?`
- `block_type_filter`: `WHERE block_type = ?`

- **Test:** Filter by project → only chunks from that project returned.

#### T9.3 🆕 Build health check CLI
Create `src/claude_rag/cli.py`:
- `python -m claude_rag health` — reports: DB connection, chunk count, source count, embedding model loaded, watcher status
- `python -m claude_rag ingest <file_path>` — manual single-file ingestion
- `python -m claude_rag search <query>` — manual search for debugging
- `python -m claude_rag watch` — start the file watcher daemon

- **Test:** `python -m claude_rag health` → prints status table, exits 0.

#### T9.4 🆕 Add structured logging
Use Python `logging` with JSON formatter across all modules. Log:
- Ingestion events (file detected, parsed, chunked, embedded, stored)
- Search queries (query text, result count, latency)
- Errors with full context

- **Test:** Run ingestion + search → log file contains structured JSON entries.

> **✅ Milestone M9 — Production Ready**

---

## DEPENDENCY GRAPH (Precedence)

```
                    ┌──────────────────────────────────────────────┐
                    │               START                          │
                    └──────────────┬───────────────────────────────┘
                                   │
                          T0.1, T0.2, T0.3
                                   │
                    ┌──────────────▼───────────────────────────────┐
                    │        M0: Project Scaffolded, DB Ready       │
                    └──┬──────────────┬──────────────┬─────────────┘
                       │              │              │
            T1.1-T1.4  │    T3.1-T3.2 │    T4.1-T4.3 │
          (parser +    │  (embedding   │   (schema +   │
           chunker)    │   providers)  │    db mgr)    │
                       │              │              │
         ┌─────────────▼──┐  ┌────────▼────┐  ┌─────▼─────────────┐
         │ M1: Parser &   │  │ M3: Embed   │  │ M4: Database      │
         │ Chunker Ready  │  │ Providers   │  │ Ready             │
         └───────┬────────┘  │ Ready       │  └────────┬──────────┘
                 │           └──────┬──────┘           │
           T2.1-T2.2               │                   │
          (watcher)                │                   │
                 │                 │                   │
         ┌───────▼────────┐       │                   │
         │ M2: Watcher    │       │                   │
         │ Ready          │       │                   │
         └───────┬────────┘       │                   │
                 │                │                   │
                 └────────┬───────┘───────────────────┘
                          │
                    T5.1-T5.2 (wire pipeline)
                          │
              ┌───────────▼──────────────────────────┐
              │  M5: End-to-End Ingestion Works       │
              └───────────┬──────────────────────────┘
                          │
                          │ (also needs M3 + M4)
                          │
                 T6.1-T6.3, T7.1-T7.3
                (search + formatting)
                          │
              ┌───────────▼──────────────────────────┐
              │  M6-M7: Search Pipeline Complete      │
              └───────────┬──────────────────────────┘
                          │
                  T8.1-T8.5 (MCP server + integration)
                          │
              ┌───────────▼──────────────────────────┐
              │  M8: MCP Server + RAG-First Active    │
              └───────────┬──────────────────────────┘
                          │
                T9.1-T9.4 (enrichment + hardening)
                          │
              ┌───────────▼──────────────────────────┐
              │  M9: Production Ready                 │
              └──────────────────────────────────────┘
```

---

## WORKER AGENT ASSIGNMENTS

The team leader should dispatch these 4 workstreams in parallel after M0:

### 🔵 Agent A: Ingestion Workstream
**Scope:** T1.1 → T1.2 → T1.3 → T1.4 → T2.1 → T2.2
**Deliverables:** Parser, chunker, file watcher, change detection
**Prerequisites:** M0 complete
**Files to study first:**
- `lambda-s3-trigger/ingestion-worker/app/processor.py` (field detection, batch processing)
- `lambda-s3-trigger/ingestion-worker/app/config.py` (config pattern)

### 🟡 Agent B: Embedding & Storage Workstream
**Scope:** T3.1 → T3.2 → T4.1 → T4.2 → T4.3
**Deliverables:** Embedding provider interface + local provider, DB schema, DB manager, migration
**Prerequisites:** M0 complete
**Files to study first:**
- `lambda-s3-trigger/ingestion-worker/app/embeddings.py` (WRAP this, don't rewrite)
- `lambda-s3-trigger/ingestion-worker/app/database.py` (EXTEND this pattern)
- `schema_legal.sql` (schema template)
- `migrate_schema.py` (migration pattern)
- `app.py` lines 212-216 (SentenceTransformer usage for alternative model)

### 🔵 Agent A (continued) or Agent C: Pipeline Integration
**Scope:** T5.1 → T5.2
**Deliverables:** End-to-end ingestion pipeline connecting watcher → parser → chunker → embedder → storage
**Prerequisites:** M1 + M2 + M3 + M4 all complete
**This is a convergence point — team leader must verify all prerequisites**

### 🟢 Agent C: Search Workstream
**Scope:** T6.1 → T6.2 → T6.3 → T7.1 → T7.2 → T7.3
**Deliverables:** Semantic search, keyword search, hybrid RRF, dedup, formatter, threshold
**Prerequisites:** M4 complete (needs DB schema). Can start with mocked embedding provider until M3 is ready.
**Files to study first:**
- `app.py` lines 576-622 (semantic search pattern)
- `app.py` lines 1139-1191 (THE KEY FILE — hybrid RRF SQL)
- `app.py` lines 1084-1108 (filter builder pattern)

### 🟣 Agent D: MCP Server & Integration Workstream
**Scope:** T8.1 → T8.2 → T8.3 → T8.4 → T8.5
**Deliverables:** MCP server, Claude Code config, CLAUDE.md instructions, integration tests
**Prerequisites:** M7 complete (full search pipeline)
**Files to study first:**
- MCP Python SDK documentation
- Claude Code MCP configuration documentation

### 🟤 Agent E: Enrichment & Hardening
**Scope:** T9.1 → T9.2 → T9.3 → T9.4
**Deliverables:** Metadata extractor, search filters, CLI, logging
**Prerequisites:** M8 complete
**Can be split across multiple agents if needed**

---

## PARALLEL EXECUTION SCHEDULE

```
Time →   Phase 0     Phase 1-2 (parallel)          Phase 3      Phase 4    Phase 5
         ┌─────┐     ┌──────────────────────┐      ┌────────┐   ┌───────┐  ┌───────┐
Agent A: │ T0.x │ ──▶│ T1.1→T1.4→T2.1→T2.2 │ ──▶  │ T5.1-2 │   │       │  │       │
         └─────┘     └──────────────────────┘      │(integr)│   │       │  │       │
                     ┌──────────────────────┐      │        │   │       │  │       │
Agent B: │ T0.x │ ──▶│ T3.1→T3.2→T4.1→T4.3 │ ──▶  │        │   │       │  │       │
         └─────┘     └──────────────────────┘      └───┬────┘   │       │  │       │
                                                       │        │       │  │       │
Agent C:                                          T6.1→T7.3 ──▶│       │  │       │
                                                                │       │  │       │
Agent D:                                                    T8.1→T8.5 ──▶│       │
                                                                        │       │
Agent E:                                                            T9.1→T9.4  │
                                                                               │
                                                                          ✅ DONE
```

---

## CRITICAL INTEGRATION CHECKPOINTS

The team leader MUST verify these before allowing downstream work:

### Checkpoint 1: Before T5.x (Pipeline Integration)
Verify ALL of these are done:
- [ ] Parser produces correct `ParsedBlock` structures
- [ ] Chunker respects code block boundaries
- [ ] `EmbeddingProvider.embed()` returns correct dimensions
- [ ] DB schema is deployed and migration is idempotent
- [ ] `DatabaseManager.upsert_chunks()` works with real data

### Checkpoint 2: Before T8.x (MCP Server)
Verify:
- [ ] `hybrid_search()` returns ranked results with RRF scores
- [ ] Context formatter respects token budget
- [ ] Relevance threshold filtering works
- [ ] Deduplication reduces overlapping chunks

### Checkpoint 3: Before shipping
Verify:
- [ ] `python -m claude_rag health` reports all green
- [ ] Full cycle: drop file → watcher → DB → search → MCP tool → formatted context
- [ ] Claude Code transcript shows `rag_search` called before file reads
- [ ] Fallback works when RAG has no results

---

## QUALITY STANDARDS FOR ALL AGENTS

1. **Type hints everywhere.** All functions must have complete type annotations.
2. **Docstrings on all public functions/classes.** Google style.
3. **Tests for every module.** Each `src/` module gets a corresponding `tests/test_*.py`.
4. **No code duplication.** Import from existing modules — especially embeddings.py and database.py.
5. **Config-driven.** All magic numbers go in `Config`. All paths are configurable.
6. **Errors are handled and logged.** No bare `except: pass`. Use structured logging.
7. **Idempotent operations.** Re-running ingestion on the same file should be safe.
