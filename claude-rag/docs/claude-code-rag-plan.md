# Claude Code Local RAG & Semantic Search System — Project Plan

## Architecture Summary

**Goal:** Build a local RAG pipeline that intercepts Claude Code's memory/session files, enriches and embeds them into PostgreSQL (pgvector), and exposes hybrid search (semantic + keyword) via an MCP server. Claude Code queries this system *first* before falling back to conventional codebase exploration.

**Stack:**
- **Language:** Python
- **Embeddings:** Local (sentence-transformers), swappable to API-based later
- **Vector DB:** PostgreSQL + pgvector
- **Keyword Search:** PostgreSQL tsvector/tsquery
- **Hybrid Ranking:** Reciprocal Rank Fusion (RRF)
- **Integration:** MCP server registered in Claude Code

---

## Phase 0 — Foundation & Environment Setup

### T0.1: Initialize Python project
Create project scaffold with `uv` or `poetry`. Set up `src/` layout, `pyproject.toml`, dev dependencies (pytest, ruff, mypy).
- **Test:** `uv run pytest` executes with 0 tests collected, no errors.

### T0.2: Provision PostgreSQL with pgvector
Install PostgreSQL locally (or via Docker). Install the `pgvector` extension. Create the project database.
- **Test:** Connect to DB and run `SELECT * FROM pg_extension WHERE extname = 'pgvector';` — returns a row.

### T0.3: Verify pgvector with sample data
Create a throwaway table with a `vector(384)` column. Insert a sample vector. Run a cosine similarity query.
- **Test:** Nearest-neighbor query returns the inserted row.

> **✅ Milestone M0 — Environment Ready**
> Python project runs, PostgreSQL + pgvector accepts vector queries.

---

## Phase 1 — Memory Ingestion: Parsing & Watching

### T1.1: Research Claude Code memory format
Document the location and structure of Claude Code's memory files: `CLAUDE.md` (project-level, user-level), session transcripts, and any `.claude/` directory contents. Record file paths, formats, and update patterns.
- **Test:** Written spec document listing all memory file locations, their schemas, and example content.

### T1.2: Build memory file parser
Python module that reads a Claude Code memory file and extracts structured records: timestamp, content blocks, code references, tags/categories.
- **Test:** Feed 3+ sample memory files → get back structured dicts with expected fields.

### T1.3: Build text chunker
Module that splits parsed content into chunks suitable for embedding. Support configurable chunk size (default ~512 tokens) and overlap (default ~50 tokens). Chunk boundaries should respect code block and paragraph boundaries.
- **Test:** A 2000-token document → produces 4–5 overlapping chunks. Code blocks are never split mid-block.

### T1.4: Unit tests for parser and chunker
Formalize the above tests into pytest suite with fixtures from sample data.
- **Test:** `pytest tests/test_parser.py tests/test_chunker.py` — all green.

> **✅ Milestone M1 — Parser & Chunker Ready**
> Can read Claude Code memory files and produce well-formed chunks.

### T2.1: Build file watcher
Use `watchdog` library to monitor Claude Code memory directories for file creation and modification events.
- **Test:** Start watcher, create a file in watched directory → callback fires with correct path.

### T2.2: Implement change detection
Track file hashes (SHA-256) to distinguish genuinely changed files from spurious events. Maintain a small SQLite or JSON state file for last-seen hashes.
- **Test:** Modify a file → detected as changed. Touch without modifying → ignored.

### T2.3: Integration test for watcher
End-to-end test: watcher detects a new CLAUDE.md, invokes parser, produces chunks.
- **Test:** Drop a sample file → chunks list is returned within 5 seconds.

> **✅ Milestone M2 — File Watcher Ready**
> System automatically detects new/changed memory files and produces chunks.

---

## Phase 2 — Embedding & Storage

### T3.1: Set up local embedding model
Install `sentence-transformers`. Select a code-aware model (e.g., `BAAI/bge-small-en-v1.5` for 384-dim or `nomic-ai/nomic-embed-text-v1.5` for 768-dim). Download and cache the model.
- **Test:** `model.encode(["hello world"])` returns a numpy array of expected dimension.

### T3.2: Build embedding module with provider interface
Create an abstract `EmbeddingProvider` base class with `embed(texts: list[str]) -> list[list[float]]`. Implement `LocalSentenceTransformerProvider`. This enables swapping later.
- **Test:** Instantiate provider, embed 10 strings, verify output shapes match model dimension.

### T3.3: Batch embedding with progress
Add batching support (configurable batch size) so large ingestion jobs don't OOM.
- **Test:** Embed 500 chunks in batches of 64 → all 500 vectors returned, no memory spike.

> **✅ Milestone M3 — Embedding Module Ready**
> Can generate vector embeddings locally for arbitrary text, with a swappable interface.

### T4.1: Design and create database schema
Create tables:
- `memory_sources` (id, file_path, file_hash, last_ingested_at)
- `chunks` (id, source_id, chunk_index, content, metadata JSONB, embedding vector(dim), tsv tsvector, created_at, updated_at)
- GIN index on `tsv`, ivfflat or HNSW index on `embedding`
- **Test:** Tables exist. `\d chunks` shows all columns and indexes.

### T4.2: Build storage module — write path
Python module with functions: `upsert_source()`, `upsert_chunks()`, `delete_chunks_for_source()`. Use `psycopg` or `asyncpg`.
- **Test:** Insert a source + 5 chunks → query confirms 5 rows. Re-upsert same source → still 5 rows (idempotent).

### T4.3: Build tsvector population
Auto-populate `tsv` column via a trigger or in the insert logic using `to_tsvector('english', content)`.
- **Test:** Insert a chunk containing "PostgreSQL vector search" → `tsv` column contains lexemes `postgresql`, `vector`, `search`.

### T4.4: Integration test for storage
Round-trip: create source, insert chunks with embeddings and tsvectors, query back.
- **Test:** All fields round-trip correctly. Vector dimension matches. tsvector is populated.

> **✅ Milestone M4 — Database Schema & Storage Ready**
> Chunks with embeddings and keyword indexes are stored and retrievable in PostgreSQL.

### T5.1: Wire end-to-end ingestion pipeline
Connect: watcher → parser → chunker → embedder → storage. A single orchestrator function or class that takes a file path event and runs the full pipeline.
- **Test:** Call `ingest_file("sample_claude.md")` → DB contains expected chunks with embeddings.

### T5.2: Live integration test
Start the watcher daemon. Drop a new memory file into the watched directory.
- **Test:** Within 10 seconds, query DB → new chunks appear with correct embeddings and tsvectors.

> **✅ Milestone M5 — End-to-End Ingestion Works**
> Dropping a memory file automatically results in embedded, indexed chunks in PostgreSQL.

---

## Phase 3 — Search & Retrieval

### T6.1: Build semantic search function
Function `semantic_search(query: str, top_k: int) -> list[SearchResult]` that embeds the query and runs cosine similarity (`<=>` operator) against pgvector.
- **Test:** Ingest known content. Query with related natural language → top result is the expected chunk.

### T6.2: Benchmark semantic search quality
Create a small evaluation set (10 query/expected-result pairs). Measure recall@5.
- **Test:** Recall@5 ≥ 0.7 on the evaluation set.

> **✅ Milestone M6 — Semantic Search Works**
> Natural language queries return relevant chunks ranked by vector similarity.

### T7.1: Build keyword search function
Function `keyword_search(query: str, top_k: int)` using `to_tsquery()` and `ts_rank()` against the `tsv` column.
- **Test:** Query "pgvector schema migration" → returns chunks containing those terms.

### T7.2: Build hybrid ranker (RRF)
Implement Reciprocal Rank Fusion: given ranked lists from semantic and keyword search, produce a merged ranked list. Configurable weight parameter α.
- **Test:** Two mock ranked lists → RRF output has correct merged ordering.

### T7.3: Build hybrid search endpoint
Function `hybrid_search(query: str, top_k: int, alpha: float)` that calls both searches and merges via RRF.
- **Test:** Hybrid search on evaluation set achieves recall@5 ≥ semantic-only recall.

> **✅ Milestone M7 — Hybrid Search Works**
> Queries leverage both semantic similarity and keyword matching with fused ranking.

### T8.1: Build result deduplication
Detect and merge near-duplicate chunks (e.g., overlapping chunks from the same source). Use content hash or Jaccard similarity.
- **Test:** Search returning 3 overlapping chunks from the same doc → deduplicated to 1–2.

### T8.2: Build token-budget-aware context formatter
Given search results and a token budget (e.g., 4096 tokens), format results into a structured context block. Truncate lower-ranked results to fit budget. Output as markdown with source attribution.
- **Test:** 10 results + budget of 2000 tokens → output is ≤ 2000 tokens, highest-ranked results included first.

### T8.3: Add relevance threshold filtering
Discard results below a configurable similarity threshold to avoid injecting noise.
- **Test:** Query with no good matches → returns empty or near-empty context (not garbage).

> **✅ Milestone M8 — Search Pipeline Complete**
> Queries return deduplicated, formatted, token-budget-aware context blocks.

---

## Phase 4 — Claude Code Integration

### T9.1: Build MCP server exposing RAG tool
Python MCP server (using `mcp` SDK) that exposes a `rag_search` tool. Input: query string + optional token budget. Output: formatted context block.
- **Test:** Run MCP server in stdio mode, send a tool call JSON → receive valid response.

### T9.2: Add MCP server configuration
Create the MCP server config entry for Claude Code's `settings.json` or `claude_desktop_config.json` (depending on where Claude Code reads MCP config).
- **Test:** Claude Code starts with the MCP server listed in its available tools.

### T9.3: End-to-end MCP test
With ingested data in DB, ask Claude Code to use the `rag_search` tool with a test query.
- **Test:** Claude Code receives context from the RAG system in its tool response.

> **✅ Milestone M9 — MCP Server Operational**
> Claude Code can call the RAG search tool and receive context.

### T10.1: Write CLAUDE.md RAG-first instructions
Author project-level `CLAUDE.md` content that instructs Claude Code to:
1. Always call `rag_search` first with the current task description
2. Evaluate if returned context is sufficient
3. Only fall back to file reads/grep if RAG context is insufficient
- **Test:** Instruction file exists and is syntactically correct.

### T10.2: Test RAG-first workflow
Give Claude Code a coding task related to previously-ingested sessions. Observe that it calls `rag_search` before reading files.
- **Test:** In the Claude Code transcript, `rag_search` tool call appears before any `Read`/`Bash` tool calls.

### T10.3: Test fallback behavior
Give Claude Code a task with no relevant RAG results. Verify it falls back to conventional exploration.
- **Test:** Claude Code calls `rag_search`, gets low/no results, then proceeds with file reads.

> **✅ Milestone M10 — RAG-First Workflow Active**
> Claude Code prioritizes local RAG and falls back gracefully.

---

## Phase 5 — Enrichment & Hardening

### T11.1: Build metadata extractor
Extract structured metadata from chunks: referenced file paths, programming language, intent tags (e.g., "bug-fix", "refactor", "new-feature"), project name.
- **Test:** Chunk referencing `src/auth.py` with Python code → metadata includes `{files: ["src/auth.py"], language: "python"}`.

### T11.2: Add metadata filters to search
Extend `hybrid_search` to accept optional metadata filters (e.g., `project="myapp"`, `language="python"`).
- **Test:** Filter by project → only chunks from that project returned.

### T11.3: Build session linker
Connect related chunks across sessions using temporal proximity and shared file references.
- **Test:** Two sessions both touching `auth.py` within 24h → linked with a `session_group_id`.

> **✅ Milestone M11 — Enrichment Pipeline Active**
> Chunks carry rich metadata; search supports filtered queries.

### T12.1: Add API-based embedding provider
Implement `APIEmbeddingProvider` (e.g., OpenAI `text-embedding-3-small` or Voyage `voyage-code-3`). Plug into the same interface.
- **Test:** Swap provider in config → embeddings generated via API.

### T12.2: Build re-embedding migration tool
Script that re-embeds all existing chunks when switching models. Handles dimension changes by altering the vector column.
- **Test:** Switch from 384-dim to 1536-dim → all chunks re-embedded, search still works.

> **✅ Milestone M12 — Embedding Provider Swappable**
> Can switch between local and API-based embeddings with a config change.

### T13.1: Add structured logging
Integrate Python `logging` with structured JSON output. Log all pipeline stages, search queries, and errors.
- **Test:** Run ingestion + search → log file contains structured entries for each stage.

### T13.2: Build health check CLI
CLI command `rag-health` that reports: DB connection status, chunk count, index status, embedding model loaded, watcher running.
- **Test:** `python -m rag_system health` → prints status table, exits 0.

### T13.3: Performance benchmark
Measure search latency (p50, p95) and ingestion throughput with realistic data (~1000 chunks).
- **Test:** Search p95 < 200ms. Ingestion throughput > 50 chunks/sec.

> **✅ Milestone M13 — Production Ready**
> System is observable, performant, and maintainable.
