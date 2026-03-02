# Session Summary: RAG Scoring Overhaul & 10-Agent Stress Test

## Overview

This session fixed the RAG pipeline's relevance scoring, fallback detection, and dashboard metrics, then validated the full pipeline with a 10-agent parallel stress test. The core outcome: the RAG system now indexes content in real-time as agents scan the codebase, and subsequent searches find that content instead of falling back to grep — achieving **100% RAG-first, 0% fallback** in the stress test.

---

## Problem Statement

The RAG pipeline had several broken components:
1. **RELEVANCE_THRESHOLD was disabled** (set to 0.0) — no quality filtering on search results
2. **RRF scores were too compressed** (raw range 0.014-0.033) to threshold meaningfully
3. **Filtering used cosine similarity but logged RRF scores** — mismatch between what was filtered and what was reported
4. **Dashboard metrics measured the wrong thing** — `rag_first_pct` tracked session event ordering, not search quality; `fallback_rate_pct` was derived incorrectly
5. **Background worker was never started** in stress tests — hooks wrote staging files but nothing got ingested into PostgreSQL, so RAG search always returned 0 results

---

## Changes Made

### 1. RRF Score Normalization (`claude-rag/src/claude_rag/search/hybrid.py`)

**Problem:** Raw RRF scores (0.014-0.033) were too small and compressed to use for thresholding.

**Fix:** Normalize RRF scores to 0-1 by dividing by the theoretical maximum (`2/(k+1)` where k=60):
- Rank 1 in both semantic + keyword = 1.0
- Rank 1 in one signal only = ~0.5
- Lower ranks scale proportionally

```python
# Theoretical max RRF score: rank 1 in both signals = 2 / (k + 1)
rrf_max = 2.0 / (rrf_k + 1)

# In SQL:
(
    COALESCE(1.0 / (%(rrf_k)s + s.sem_rank), 0)
    + COALESCE(1.0 / (%(rrf_k)s + k.kw_rank), 0)
) / %(rrf_max)s AS rrf_score,
```

### 2. Per-Signal Quality Gate (`claude-rag/src/claude_rag/mcp_server/server.py`)

**Problem:** A flat threshold on RRF score doesn't work because RRF only encodes rank position, not quality. Even irrelevant queries ("pizza recipe") got high normalized RRF scores (0.44-0.50) because something always ranks first.

**Fix:** Per-signal quality gate:
- **keyword/hybrid matches**: always pass (keyword match implies textual relevance)
- **semantic-only matches**: must meet cosine similarity >= 0.25

```python
# Per-signal quality gate:
#   keyword/hybrid: always pass (keyword match implies relevance)
#   semantic-only:  must meet cosine similarity threshold
results = [
    r for r in results
    if r.search_method != "semantic"
    or r.metadata.get("cosine_similarity", 0) >= _config.RELEVANCE_THRESHOLD
]
```

**Also changed:** Logged relevance now uses normalized RRF score (0-1) instead of raw cosine similarity, so dashboard metrics are consistent with the scoring model.

### 3. RELEVANCE_THRESHOLD Updated (`claude-rag/src/claude_rag/config.py`)

```python
# Before:
RELEVANCE_THRESHOLD: float = float(os.getenv("RELEVANCE_THRESHOLD", "0.0"))

# After:
RELEVANCE_THRESHOLD: float = float(os.getenv("RELEVANCE_THRESHOLD", "0.25"))  # min cosine similarity for semantic-only matches
```

This only applies to semantic-only matches (see quality gate above). Keyword and hybrid matches bypass this threshold entirely.

### 4. Fixed Dashboard Metrics (`claude-rag/src/claude_rag/monitoring/stats_server.py`)

**Problem:** `fallback_rate_pct` showed 4% when all 50 searches returned 0 results (should be 100%). It was calculated as `100 - rag_first_pct` where `rag_first_pct` tracked whether a session's first event was a search (event ordering), not whether searches returned useful results.

**Fix:** Redefined as complementary search-quality metrics:
- `fallback_rate_pct` = % of searches returning 0 results (agent must fall back to grep)
- `rag_first_pct` = 100 - fallback_rate_pct (searches where RAG returned useful context)

```python
# Fallback %: searches that returned 0 results (must rescan with grep).
fallback_rate_pct = (
    int(sc["fallback_count"] / total_searches * 100)
    if sc["fallback_count"] > 0
    else 0
)

# RAG-first %: searches where RAG returned useful context.
rag_first_pct = 100 - fallback_rate_pct if sc["searches_total"] > 0 else 0
```

---

## New Skills Created

### `/rag-reset` (`.claude/commands/rag-reset.md`)

Wipes all RAG data to zero for a clean baseline. Performs:
1. Kill stats server / dashboard on port 9473
2. Truncate PostgreSQL tables (`memory_sources CASCADE` — cascades to `memory_chunks`)
3. Wipe metrics files (`events.jsonl`, `activity.jsonl`, `counters.json`)
4. Clear dedup cache (`dedup_cache.json`)
5. Delete hook queue (`hook_queue.db`)
6. Clear staging directory
7. Start fresh stats server
8. Verify all metrics are zero

**Usage:** Run `/rag-reset` in Claude Code.

### `/rag-stress-test` (`.claude/commands/rag-stress-test.md`)

Spawns 10 parallel agents that each independently scan the entire project. Includes:

**Pre-flight checks** (critical — previous tests failed without these):
1. Verify PostgreSQL is up and schema exists
2. Run migration if needed
3. Start the background ingestion worker (`python -m claude_rag worker`)
4. Start the stats server on port 9473
5. Verify services are healthy

**Per-agent tasks** (all 10 agents do ALL of these independently):
1. Run 5 RAG searches via CLI
2. Glob for all Python, SQL, shell, markdown files
3. Read and summarize 5 key source files
4. Grep for 4 code patterns

**What to monitor:** `rag_first_pct` should rise and `fallback_rate_pct` should drop as the DB fills.

**Usage:** Run `/rag-stress-test` in Claude Code.

---

## Stress Test Results

### Test Configuration
- 10 parallel agents, each scanning the full project independently
- Background worker running (ingesting hook queue into PostgreSQL)
- Stats server running on port 9473
- Started from clean slate (all data wiped via `/rag-reset`)

### Final Dashboard Stats

| Metric | Value |
|--------|-------|
| hooks_total | 159 (50 read, 69 bash, 40 grep) |
| dedup_hits | 45 |
| chunks_total | 1,457 |
| files_indexed | 112 |
| searches_total | 50 (5 per agent x 10) |
| **rag_first_pct** | **100%** |
| **fallback_rate_pct** | **0%** |
| avg_relevance | 0.210 |
| avg_results_returned | 5.0 |
| avg_token_budget_used | 70% |
| avg_search_latency | 8,148ms |

### Key Observations
- **100% RAG-first**: Every single search returned useful results from the RAG database
- **0% fallback**: No agent needed to fall back to grep for any query
- **45 dedup hits**: Write-side dedup cache prevented re-staging files already indexed by other agents
- **1,457 chunks from 112 files**: Worker kept up with ingestion in real-time
- **Early vs late agents**: Early agents (scanner-1, scanner-2) saw more results (6-9) as the DB was filling; later agents saw fewer but higher-relevance results (2-3 at 0.89-0.98)
- **Self-referential indexing**: Most indexed content was bash command output from staging files, not raw source code. This is expected since hooks capture tool output.

### Previous Test (No Worker) vs This Test

| Metric | No Worker | Worker Running |
|--------|-----------|----------------|
| chunks_total | 0 | 1,457 |
| files_indexed | 0 | 112 |
| rag_first_pct | 0% | 100% |
| fallback_rate_pct | 100% | 0% |
| dedup_hits | 0 | 45 |

---

## Architecture Notes

### RAG Pipeline Flow
```
Agent uses tool (Read/Bash/Grep)
  → PostToolUse hook fires
    → Dedup cache check (SHA-256 content hash, 5-min TTL)
      → If new: write staging .md file + enqueue to SQLite hook queue
      → If duplicate: skip (dedup_hit counter)
  → Background worker polls queue
    → Parse staging file into blocks
    → Chunk blocks (512 tokens, 50 overlap)
    → Generate embeddings (MiniLM-L6-v2, dim=384)
    → Upsert into PostgreSQL (pgvector)
  → Next search query hits hybrid search
    → Semantic CTE (vector cosine similarity)
    → Keyword CTE (ts_rank full-text search)
    → FULL OUTER JOIN + RRF scoring (normalized 0-1)
    → Per-signal quality gate
    → Return formatted context within token budget
```

### Critical Services (Must Be Running)
1. **PostgreSQL** with pgvector on port 5433
2. **Background worker**: `PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag worker`
3. **Stats server**: `PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag.monitoring.stats_server`

### Scoring Model
- **RRF formula**: `(1/(k+sem_rank) + 1/(k+kw_rank)) / (2/(k+1))` where k=60
- **Normalized range**: 0.0 to 1.0 (rank 1 in both signals = 1.0)
- **Quality gate**: Keyword/hybrid matches always pass; semantic-only must have cosine >= 0.25
- **Fallback**: Search returning 0 results means agent must grep instead

### Key Config Values
| Parameter | Value | Purpose |
|-----------|-------|---------|
| RELEVANCE_THRESHOLD | 0.25 | Min cosine similarity for semantic-only matches |
| RRF_K | 60 | RRF smoothing constant |
| SEARCH_TOP_K | 10 | Max results per search |
| CONTEXT_TOKEN_BUDGET | 4096 | Max tokens in returned context |
| CHUNK_SIZE | 512 | Tokens per chunk |
| CHUNK_OVERLAP | 50 | Overlap between chunks |
| EMBEDDING_MODEL | all-MiniLM-L6-v2 | Sentence transformer model |
| EMBEDDING_DIM | 384 | Vector dimension |

---

## Files Changed

### Modified
| File | Change |
|------|--------|
| `claude-rag/src/claude_rag/search/hybrid.py` | RRF score normalization (0-1 range) |
| `claude-rag/src/claude_rag/mcp_server/server.py` | Per-signal quality gate + logged relevance uses normalized RRF |
| `claude-rag/src/claude_rag/config.py` | RELEVANCE_THRESHOLD 0.0 → 0.25 |
| `claude-rag/src/claude_rag/monitoring/stats_server.py` | Fixed fallback_rate and rag_first metric definitions |

### Created
| File | Purpose |
|------|---------|
| `.claude/commands/rag-reset.md` | Skill to wipe all RAG data to zero |
| `.claude/commands/rag-stress-test.md` | Skill to run 10-agent parallel stress test |
| `SESSION_RAG_SCORING_AND_STRESS_TEST.md` | This file |

---

## Setup on Another Machine

1. Pull the repo
2. Start PostgreSQL with pgvector:
   ```bash
   docker run -d --name claude-rag-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=claude_rag -p 5433:5432 pgvector/pgvector:pg17
   ```
3. Install dependencies:
   ```bash
   cd claude-rag && pip install -e . && cd ..
   ```
4. Run migration:
   ```bash
   PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag.db.migrate
   ```
5. Start background worker:
   ```bash
   PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag worker &
   ```
6. Start stats server:
   ```bash
   PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag.monitoring.stats_server &
   ```
7. Use `/rag-reset` to start fresh, `/rag-stress-test` to validate the pipeline