# Phase 1 Verification & Revised Phase 2 — Live Testing Plan

## CRITICAL DISCOVERY: New Data Sources and Interception Points

After studying Claude Code's internals, the original plan had an incomplete picture of what to ingest. Here's what actually exists on disk and how to intercept it:

### Data Sources (on Windows: `%USERPROFILE%\.claude\`)

| Source | Path | Contains | Update Trigger |
|--------|------|----------|----------------|
| **Session JSONL** | `~/.claude/projects/<encoded-path>/<uuid>.jsonl` | Full transcript: every Read, Bash, Write, Edit tool call with inputs AND outputs. Thinking blocks. Token usage. | Appended in real-time during session |
| **Session Memory** | `~/.claude/projects/<hash>/<session-id>/session-memory/summary.md` | AI-generated session summary | Written at session end |
| **CLAUDE.md** | `<project>/CLAUDE.md` or `<project>/.claude/CLAUDE.md` | Project instructions, conventions | Manual or /remember |
| **CLAUDE.local.md** | `<project>/CLAUDE.local.md` | Personal project memory from /remember | /remember command |
| **History index** | `~/.claude/history.jsonl` | Session metadata (project, timestamp, topic) | Each session start |

### Interception Points (Hooks — THIS CHANGES EVERYTHING)

Claude Code has a **hooks system** that fires scripts at specific events. This is the
ideal real-time interception point, much better than polling JSONL files:

| Hook Event | When It Fires | What We Get |
|------------|---------------|-------------|
| **PostToolUse (Read)** | After Claude reads a file | `tool_name: "Read"`, `tool_input: {file_path}`, full file content in result |
| **PostToolUse (Bash)** | After Claude runs a command | `tool_name: "Bash"`, command, stdout/stderr |
| **PostToolUse (Grep)** | After Claude searches code | Search pattern, matching results |
| **UserPromptSubmit** | When user sends a prompt | The prompt text — captures intent |
| **SessionStart** | When a session begins | session_id, transcript_path, project dir |
| **Stop** | When session ends | session_id, completed work |

**Key insight:** Using `PostToolUse` hooks on `Read` events means we can index code
THE MOMENT Claude reads it, not after the session ends. Every token spent reading
code gets captured immediately.

Configure hooks in `.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read",
        "command": "python -m claude_rag.hooks.post_read \"$CLAUDE_TOOL_INPUT\" \"$CLAUDE_TOOL_RESULT\""
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "command": "python -m claude_rag.hooks.post_bash \"$CLAUDE_TOOL_INPUT\" \"$CLAUDE_TOOL_RESULT\""
      }
    ],
    "Stop": [
      {
        "command": "python -m claude_rag.hooks.session_end"
      }
    ]
  }
}
```

---

## PHASE 1 VERIFICATION: Live Testing Plan

These tests verify that the existing Phase 1 implementation works end-to-end with
human-observable evidence. Each test has a clear "what you'll see" section.

### Prerequisites
- Phase 1 code is deployed (parser, chunker, watcher, embeddings, DB, pipeline)
- PostgreSQL with pgvector running locally with the `claude_rag` database
- The file watcher is running (or can be started)

---

### TEST V1.1: Database Schema Validation
**Purpose:** Confirm the schema is correctly deployed with all tables, indexes, and constraints.

**Steps:**
1. Connect to PostgreSQL: `psql -d claude_rag`
2. Run the verification queries below

**Verification Queries:**
```sql
-- Check tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
-- EXPECT: memory_chunks, memory_sources (at minimum)

-- Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';
-- EXPECT: 1 row

-- Check vector column dimensions
SELECT column_name, udt_name
FROM information_schema.columns
WHERE table_name = 'memory_chunks' AND column_name = 'embedding';
-- EXPECT: udt_name = 'vector'

-- Check indexes exist
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'memory_chunks'
ORDER BY indexname;
-- EXPECT: HNSW index on embedding, GIN index on content_tsv, B-tree on source_id

-- Check tsvector column is generated
SELECT column_name, generation_expression
FROM information_schema.columns
WHERE table_name = 'memory_chunks' AND column_name = 'content_tsv';
-- EXPECT: generation_expression contains to_tsvector

-- Check cascade delete constraint
SELECT constraint_name, delete_rule
FROM information_schema.referential_constraints
WHERE constraint_name LIKE '%memory%';
-- EXPECT: delete_rule = 'CASCADE'
```

**Human Observes:** All queries return expected results. Screenshot or log the output.

**Pass Criteria:** All 6 queries match expected results.

---

### TEST V1.2: Embedding Provider Round-Trip
**Purpose:** Confirm embeddings generate correctly and match expected dimensions.

**Steps:**
```python
# Run in Python REPL or as a script
from claude_rag.embeddings.local import LocalEmbeddingProvider

provider = LocalEmbeddingProvider()

# Test 1: Single embedding
vec = provider.embed_single("Python authentication middleware using JWT tokens")
print(f"Dimension: {len(vec)}")
print(f"First 5 values: {vec[:5]}")
print(f"Is normalized (L2 ≈ 1.0): {sum(v**2 for v in vec) ** 0.5:.4f}")

# Test 2: Batch embedding
texts = [
    "Database connection pooling with pgbouncer",
    "React component lifecycle hooks useEffect",
    "Kubernetes pod autoscaling configuration",
]
vecs = provider.embed(texts)
print(f"Batch size: {len(vecs)}, each dim: {len(vecs[0])}")

# Test 3: Semantic similarity sanity check
from numpy import dot
sim = dot(vecs[0], vecs[1])  # DB vs React — should be low
print(f"DB vs React similarity: {sim:.4f}")  # Expect < 0.5

sim2 = dot(
    provider.embed_single("PostgreSQL connection pool"),
    vecs[0]  # "Database connection pooling with pgbouncer"
)
print(f"PG pool vs DB pool similarity: {sim2:.4f}")  # Expect > 0.7
```

**Human Observes:** Dimensions match config (384 or 768), vectors are normalized, similar texts score high, dissimilar texts score low.

**Pass Criteria:** Dimension correct, L2 norm ≈ 1.0, semantic similarity sanity check passes.

---

### TEST V1.3: Parser Handles Real Claude Code Data
**Purpose:** Confirm the parser can handle actual Claude Code files, not just test fixtures.

**Steps:**
1. Locate your real CLAUDE.md files:
   ```
   # On Windows:
   dir /s /b %USERPROFILE%\.claude\CLAUDE.md
   dir /s /b C:\Users\ClayMorgan\PycharmProjects\llm-inference\CLAUDE.md
   ```
2. Also locate a real session JSONL:
   ```
   dir /s /b %USERPROFILE%\.claude\projects\*.jsonl
   ```
3. Run the parser on each:
   ```python
   from claude_rag.ingestion.parser import parse_claude_md, parse_session_log

   # Test against real CLAUDE.md
   blocks = parse_claude_md(r"C:\Users\ClayMorgan\PycharmProjects\llm-inference\CLAUDE.md")
   print(f"Parsed {len(blocks)} blocks")
   for b in blocks[:5]:
       print(f"  [{b.block_type}] {b.content[:80]}...")

   # Test against real session JSONL
   session_blocks = parse_session_log(r"<path-to-a-real-session>.jsonl")
   print(f"Parsed {len(session_blocks)} blocks from session")
   for b in session_blocks[:5]:
       print(f"  [{b.block_type}] {b.content[:80]}...")
   ```

**Human Observes:** Blocks are parsed with correct types. Code fences identified as "code". Tool calls identified. No crashes on real data.

**Pass Criteria:** Parser produces structured blocks from real files without errors. Block types are meaningful (not all "unknown").

---

### TEST V1.4: Chunker Respects Code Block Boundaries
**Purpose:** Confirm chunks never split inside code fences.

**Steps:**
```python
from claude_rag.ingestion.parser import parse_claude_md
from claude_rag.ingestion.chunker import chunk_blocks

# Use a file you know contains code blocks
blocks = parse_claude_md(r"<path-to-claude-md-with-code>")
chunks = chunk_blocks(blocks, chunk_size=512, overlap=50)

print(f"Input: {len(blocks)} blocks → {len(chunks)} chunks")

# Verify no code block is split
for i, chunk in enumerate(chunks):
    backtick_count = chunk.content.count("```")
    if backtick_count % 2 != 0:
        print(f"❌ FAIL: Chunk {i} has unmatched code fence ({backtick_count} backticks)")
        print(f"   Content preview: {chunk.content[:200]}")
    else:
        print(f"✅ Chunk {i}: {backtick_count // 2} complete code blocks, ~{len(chunk.content)} chars")
```

**Human Observes:** No chunk has an odd number of triple-backtick markers.

**Pass Criteria:** Every chunk has an even number of ``` markers (0, 2, 4...).

---

### TEST V1.5: Full Ingestion Pipeline — File to Database
**Purpose:** Confirm end-to-end: file → parse → chunk → embed → store in PostgreSQL.

**Steps:**
```python
from claude_rag.ingestion.pipeline import IngestionPipeline
from claude_rag.config import Config
import psycopg2

config = Config()
pipeline = IngestionPipeline(config)

# Ingest a real CLAUDE.md
result = pipeline.ingest_file(r"<path-to-a-real-claude-md>")
print(f"Ingested: source_id={result.source_id}, chunks={result.chunks_created}, time={result.duration_ms}ms")

# Verify in database
conn = psycopg2.connect(
    host=config.PGHOST, database=config.PGDATABASE,
    user=config.PGUSER, password=config.PGPASSWORD, port=config.PGPORT
)
cur = conn.cursor()

# Check source record
cur.execute("SELECT file_path, file_hash, chunk_count FROM memory_sources WHERE id = %s", (result.source_id,))
source = cur.fetchone()
print(f"Source: path={source[0]}, hash={source[1]}, chunks={source[2]}")

# Check chunks have embeddings AND tsvectors
cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(embedding) as with_embeddings,
           COUNT(content_tsv) as with_tsvectors
    FROM memory_chunks WHERE source_id = %s
""", (result.source_id,))
counts = cur.fetchone()
print(f"Chunks: total={counts[0]}, with_embeddings={counts[1]}, with_tsvectors={counts[2]}")

# Verify embedding dimensions
cur.execute("""
    SELECT vector_dims(embedding) FROM memory_chunks
    WHERE source_id = %s AND embedding IS NOT NULL LIMIT 1
""", (result.source_id,))
dims = cur.fetchone()
print(f"Embedding dimensions: {dims[0]}")

# Sample a chunk's tsvector
cur.execute("""
    SELECT LEFT(content, 100), content_tsv::text
    FROM memory_chunks WHERE source_id = %s LIMIT 1
""", (result.source_id,))
sample = cur.fetchone()
print(f"Sample content: {sample[0]}")
print(f"Sample tsvector: {sample[1][:200]}")

cur.close()
conn.close()
```

**Human Observes:** Source row created, all chunks have embeddings AND tsvectors, dimensions match config.

**Pass Criteria:**
- `with_embeddings == total`
- `with_tsvectors == total`
- `vector_dims == Config.EMBEDDING_DIM`
- `chunk_count > 0`

---

### TEST V1.6: Idempotent Re-Ingestion
**Purpose:** Confirm re-ingesting the same unchanged file doesn't create duplicates.

**Steps:**
```python
# Ingest the same file twice
result1 = pipeline.ingest_file(r"<same-file-as-V1.5>")
result2 = pipeline.ingest_file(r"<same-file-as-V1.5>")

print(f"First:  source_id={result1.source_id}, chunks={result1.chunks_created}")
print(f"Second: source_id={result2.source_id}, chunks={result2.chunks_created}")

# Check DB has only one source and one set of chunks
cur.execute("SELECT COUNT(*) FROM memory_sources WHERE file_path = %s", (r"<same-file-path>",))
source_count = cur.fetchone()[0]
print(f"Source records for this file: {source_count}")  # Should be 1

cur.execute("SELECT COUNT(*) FROM memory_chunks WHERE source_id = %s", (result1.source_id,))
chunk_count = cur.fetchone()[0]
print(f"Chunk records: {chunk_count}")  # Should equal result1.chunks_created
```

**Human Observes:** Second ingestion is either skipped (hash match) or replaces (not duplicates) chunks.

**Pass Criteria:** `source_count == 1`. Chunk count matches first ingestion, not doubled.

---

### TEST V1.7: Change Detection Works
**Purpose:** Confirm modified files trigger re-ingestion, unmodified files are skipped.

**Steps:**
```python
import shutil, time

# Copy a test file
test_file = r"C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag\tests\fixtures\test_claude.md"
shutil.copy(r"<original-claude-md>", test_file)

# Ingest it
result1 = pipeline.ingest_file(test_file)
print(f"Initial ingestion: {result1.chunks_created} chunks")

# Ingest again without changing — should skip
result2 = pipeline.ingest_file(test_file)
print(f"Re-ingest (unchanged): {result2.chunks_created} chunks, skipped={result2.skipped}")

# Now modify the file
with open(test_file, "a") as f:
    f.write("\n\n## New Section\nThis is new content that should trigger re-ingestion.\n")

# Ingest again — should detect change
result3 = pipeline.ingest_file(test_file)
print(f"Re-ingest (modified): {result3.chunks_created} chunks")

assert result3.chunks_created >= result1.chunks_created, "Modified file should produce at least as many chunks"
```

**Human Observes:** Unchanged file is skipped. Modified file is re-processed.

**Pass Criteria:** result2 is skipped. result3 processes with updated chunk count.

---

### TEST V1.8: File Watcher Fires on Real Events
**Purpose:** Confirm watchdog detects file changes in real-time.

**Steps:**
```python
import time, threading
from claude_rag.ingestion.watcher import MemoryFileWatcher

events_received = []

def on_file_change(file_path):
    events_received.append(file_path)
    print(f"🔔 DETECTED: {file_path} at {time.strftime('%H:%M:%S')}")

watcher = MemoryFileWatcher(
    watch_dirs=[r"<test-directory>"],
    callback=on_file_change
)

# Start watcher in background
thread = threading.Thread(target=watcher.start, daemon=True)
thread.start()
print("Watcher started. Creating test files...")

time.sleep(2)  # Let watcher initialize

# Create a new file
with open(r"<test-directory>\test_new.md", "w") as f:
    f.write("# Test\nNew content for watcher test")

time.sleep(3)

# Modify the file
with open(r"<test-directory>\test_new.md", "a") as f:
    f.write("\n## Modified\nAdditional content")

time.sleep(3)

print(f"\nTotal events received: {len(events_received)}")
for e in events_received:
    print(f"  → {e}")

watcher.stop()
```

**Human Observes:** Console prints "🔔 DETECTED" within seconds of each file operation.

**Pass Criteria:** At least 1 event for creation, at least 1 for modification.

---

### TEST V1.9: Live Session JSONL Ingestion
**Purpose:** Confirm the parser can handle real Claude Code session JSONL files and extract Read tool calls (the most important data for code indexing).

**Steps:**
```python
import json, glob

# Find the most recent session JSONL
session_dir = r"%USERPROFILE%\.claude\projects"  # adjust for your Windows path
jsonl_files = glob.glob(f"{session_dir}/**/*.jsonl", recursive=True)
latest = max(jsonl_files, key=lambda f: os.path.getmtime(f))
print(f"Testing with: {latest}")
print(f"Size: {os.path.getsize(latest) / 1024:.1f} KB")

# Count Read tool calls (these are the tokens we want to capture)
read_calls = []
with open(latest, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            record = json.loads(line)
            if record.get("type") == "assistant":
                content = record.get("message", {}).get("content", [])
                for block in content:
                    if block.get("type") == "tool_use" and block.get("name") == "Read":
                        read_calls.append(block["input"]["file_path"])
        except:
            continue

print(f"\nRead tool calls in session: {len(read_calls)}")
for f in read_calls[:10]:
    print(f"  📖 {f}")

# Now parse through the pipeline
blocks = parse_session_log(latest)
print(f"\nParsed {len(blocks)} blocks from session JSONL")

# Count blocks by type
from collections import Counter
types = Counter(b.block_type for b in blocks)
for t, count in types.most_common():
    print(f"  {t}: {count}")
```

**Human Observes:** Read tool calls are extracted and counted. The parser produces meaningful blocks from session data.

**Pass Criteria:** Read calls found (≥1 in any non-trivial session). Blocks have distinct types.

---

### TEST V1.10: The "Golden Path" — Full Live Cycle
**Purpose:** The ultimate test. Simulate the complete workflow a user would experience.

**Steps (manual, human-driven):**

1. **Start the watcher daemon:**
   ```bash
   python -m claude_rag watch
   ```
   Console should show: "Watching directories: ..."

2. **In a SEPARATE terminal, start Claude Code on your llm-inference project:**
   ```bash
   claude
   ```

3. **Give Claude Code a task that requires reading code:**
   ```
   Read the hybrid search implementation in app.py and explain
   how the RRF scoring works.
   ```

4. **While Claude Code works, watch the watcher terminal.**
   You should see file change events as session JSONL is appended.

5. **After Claude Code responds, check the database:**
   ```sql
   SELECT ms.file_path, mc.block_type, LEFT(mc.content, 100) as preview,
          mc.created_at
   FROM memory_chunks mc
   JOIN memory_sources ms ON mc.source_id = ms.id
   ORDER BY mc.created_at DESC
   LIMIT 10;
   ```

6. **Now test retrieval — run a search:**
   ```bash
   python -m claude_rag search "reciprocal rank fusion scoring"
   ```
   Should return chunks related to what Claude just read.

**Human Observes:**
- Watcher terminal shows activity during Claude Code session
- Database has new chunks created with timestamps matching the session
- Search returns relevant content from the just-indexed session

**Pass Criteria:** All three observations confirmed. The content Claude read is now searchable in the RAG database.

---

## REVISED PHASE 2: Layered Enrichment + Hook-Based Interception

Based on the architecture discussion about semantic descriptions vs raw code,
and the discovery of Claude Code's hooks system, here is the revised Phase 2.

### PHASE 2A — Hook-Based Real-Time Interception

#### T-H1: Build PostToolUse hook for Read events
Create `src/claude_rag/hooks/post_read.py`:
- Receives `tool_input` (file_path, line range) and `tool_result` (file content) via stdin/env
- Sends the file path + content to the ingestion pipeline
- Runs in <500ms to avoid slowing Claude Code down (async queue if needed)
- Logs every interception to structured log

Hook config for `.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read",
        "command": "python C:\\...\\claude-rag\\src\\claude_rag\\hooks\\post_read.py"
      }
    ]
  }
}
```

**Test:** Claude Code reads a file → hook fires → chunk appears in DB within 2 seconds.

#### T-H2: Build PostToolUse hook for Bash/Grep events
Same pattern for Bash and Grep tool calls. Capture:
- Commands run (useful for understanding what Claude was investigating)
- stdout/stderr output (contains code search results, test output, etc.)
- Only index outputs >50 chars (skip trivial commands like `ls`, `pwd`)

**Test:** Claude Code runs `grep -r "authentication" src/` → grep results indexed.

#### T-H3: Build UserPromptSubmit hook
Capture every prompt the user sends. This is the "intent" layer — it records
WHAT Claude was asked to do, which is critical context for future RAG queries.

**Test:** User types "refactor the auth module" → prompt text indexed with block_type="user_intent".

#### T-H4: Build session summary ingestion
Create `src/claude_rag/hooks/session_end.py`:
- On `Stop` hook, wait 5 seconds for session-memory summary to be written
- Parse `~/.claude/projects/<hash>/<session-id>/session-memory/summary.md`
- Ingest as a high-value chunk with block_type="session_summary"

**Test:** End a Claude Code session → summary.md appears in DB as a chunk.

#### T-H5: Build async queue for hook processing
Hooks must be fast (<500ms) or they'll slow down Claude Code. Build:
- A lightweight SQLite queue (or file-based queue) that hooks write to
- A background worker that reads from the queue and runs the full pipeline
- Hooks just enqueue; the worker does parse → chunk → embed → store

**Test:** Rapid-fire 10 Read events → all 10 indexed within 30 seconds, no Claude Code slowdown.

> **✅ Milestone M-H: Hook-Based Real-Time Interception Active**
> Every Read, Bash, Grep, and user prompt is captured and indexed as it happens.

---

### PHASE 2B — Layered Semantic Enrichment

This implements the 3-layer representation from our discussion.

#### T-E1: Build Layer 1 — Semantic Summary Generator
Create `src/claude_rag/enrichment/summarizer.py`:
- Takes a raw code chunk (from a Read tool capture)
- Calls a local LLM (or Claude Haiku via API) to generate a ~50-100 token
  natural language summary: purpose, relationships, design patterns
- Stores as a separate chunk with `block_type="semantic_summary"` linked to
  the raw chunk via metadata `{"summarizes_chunk_id": <id>}`

Example input (raw code):
```python
class AuthManager:
    def __init__(self, jwt_secret, user_repo):
        self.jwt_secret = jwt_secret
        self.user_repo = user_repo

    def validate_token(self, token):
        ...
```

Example output (semantic summary):
"AuthManager handles JWT validation and delegates user lookups to UserRepository.
Constructor requires jwt_secret and a user_repo dependency. Core method is
validate_token which decodes and verifies JWT tokens."

**Test:** Ingest a Python file → both raw chunk AND semantic summary exist in DB.
Query "JWT authentication" → semantic summary ranks higher than raw code.

#### T-E2: Build Layer 2 — Structural Signature Extractor
Create `src/claude_rag/enrichment/signatures.py`:
- Parses code to extract: class names, method signatures, type hints, imports
- Uses Python `ast` module for Python files, regex for others
- Produces a `.pyi`-style stub: just the API surface, no implementation
- Stores as `block_type="structural_signature"`

Example output:
```
class AuthManager:
    jwt_secret: str
    user_repo: UserRepository
    def validate_token(self, token: str) -> dict: ...
    def create_token(self, user_id: int, roles: list[str]) -> str: ...
    def require_role(self, role: str) -> Callable: ...
```

**Test:** Ingest `app.py` → signature chunk contains all class/function names.
Token count of signature << token count of full file.

#### T-E3: Build Layer 3 — Decision Context Extractor
Create `src/claude_rag/enrichment/decisions.py`:
- Scans session JSONL thinking blocks for reasoning about design decisions
- Scans user prompts for task context ("we need to add X because Y")
- Extracts and stores as `block_type="decision_context"`

Example output:
"Chose JWT over session cookies for the auth system because of the microservice
architecture. Added refresh token rotation after the security review."

**Test:** A session where Claude explains a design choice → decision context chunk created.

#### T-E4: Build enrichment pipeline orchestrator
Create `src/claude_rag/enrichment/pipeline.py`:
- After raw chunks are stored, queue them for enrichment
- Run summarizer → signature extractor → decision extractor
- Mark chunks as `enriched=true` in metadata to avoid re-enrichment
- Background process — doesn't block the hook pipeline

**Test:** Ingest 10 files → all get raw chunks immediately, enrichment layers appear within 60 seconds.

> **✅ Milestone M-E: Layered Enrichment Active**
> Every indexed file has 3 layers: semantic summary, structural signature, decision context.

---

### PHASE 2C — "Already Covered" Detection

#### T-D1: Build file content hash index
Track every file path + content hash that has been indexed:
- `memory_sources` table already has `file_hash`
- Add `content_version` tracking: `{file_path: str, content_hash: str, last_seen: datetime}`
- Before processing a Read hook event, check: "Have we already indexed this exact content?"

**Test:** Claude reads `app.py` (unchanged) → hook fires → system checks hash → logs "already indexed, skipping" → no duplicate work.

#### T-D2: Build chunk-level deduplication
Beyond file-level: detect when Claude reads overlapping line ranges of the same file
across sessions. Don't re-embed content that's already embedded.
- Hash each chunk's content
- Before inserting, check if chunk hash already exists for this source
- If identical, update `last_seen` timestamp but skip embedding

**Test:** Two sessions both read lines 1-200 of `app.py` → only 1 set of chunks, with updated timestamp.

#### T-D3: Build "coverage report" CLI
Add to `cli.py`:
```bash
python -m claude_rag coverage
```
Output:
```
=== RAG Coverage Report ===
Project: llm-inference
Files indexed: 23 / 47 total source files (49%)
Sessions indexed: 12
Total chunks: 342 (178 raw, 89 summaries, 52 signatures, 23 decisions)
Last ingestion: 2 minutes ago

Recently read but NOT yet enriched:
  - src/claude_rag/search/hybrid.py (raw only, enrichment queued)

Files read most often (candidates for priority enrichment):
  - app.py (read 14 times across 8 sessions)
  - lambda-s3-trigger/ingestion-worker/app/processor.py (read 7 times)

Estimated token savings vs full re-read: ~45,000 tokens/session
```

**Test:** Run after several Claude Code sessions → report shows accurate counts and coverage.

> **✅ Milestone M-D: Deduplication & Coverage Tracking Active**
> System knows what it's already indexed and skips redundant work. Human can see coverage.

---

## REVISED DEPENDENCY GRAPH

```
Phase 1 (DONE) ──────────────────────────────────────────────┐
  Parser, Chunker, Watcher, Embeddings, DB, Pipeline         │
                                                              │
                                    ┌─────────────────────────▼──────────────┐
                                    │ VERIFICATION (V1.1 - V1.10)            │
                                    │ Human-observable live tests             │
                                    └─────────────────┬──────────────────────┘
                                                      │ All tests pass
                                    ┌─────────────────▼──────────────────────┐
                                    │ Phase 2A: Hook-Based Interception      │
                                    │ T-H1 → T-H2 → T-H3 → T-H4 → T-H5    │
                                    │ "Capture everything in real-time"      │
                                    └───────┬────────────────┬───────────────┘
                                            │                │
                              ┌─────────────▼────┐   ┌──────▼────────────────┐
                              │ Phase 2B:        │   │ Phase 2C:             │
                              │ Enrichment       │   │ Dedup & Coverage      │
                              │ T-E1→T-E4        │   │ T-D1→T-D3            │
                              │ (can run in      │   │ (can run in           │
                              │  parallel with C)│   │  parallel with B)     │
                              └───────┬──────────┘   └──────┬────────────────┘
                                      │                     │
                                      └──────────┬──────────┘
                                                 │
                              ┌──────────────────▼───────────────────────────┐
                              │ Continue to Phase 3: Search + MCP Server     │
                              │ (from original plan)                         │
                              └──────────────────────────────────────────────┘
```

---

## EXECUTION ORDER

1. **Now:** Run V1.1 through V1.10 on your existing Phase 1 implementation
2. **Fix any failures** found during verification
3. **Then:** Build Phase 2A (hooks) — this is the highest-value work
4. **Then:** Phase 2B + 2C in parallel (enrichment + dedup)
5. **Then:** Continue with Phase 3 (search) and Phase 4 (MCP server) from original plan
