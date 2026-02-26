# Phase 2 Verification — Complete Human-Observable Live Test Suite

## Overview

These tests verify the ENTIRE pipeline works end-to-end with real Claude Code sessions.
Every test is designed so you can see exactly what's happening — no hidden assertions,
no silent passes. You're watching the data flow through the system in real time.

The tests are organized into 5 verification areas:

| Area | What It Proves | Tests |
|------|---------------|-------|
| **A. Hook Interception** | Every token Claude spends reading code gets captured | V2.1 – V2.6 |
| **B. Enrichment Layers** | Raw code → semantic summary + signatures + decisions | V2.7 – V2.11 |
| **C. Deduplication** | System knows what it's already seen, skips redundant work | V2.12 – V2.15 |
| **D. RAG Retrieval** | Claude actually USES the RAG system and gets good context | V2.16 – V2.20 |
| **E. Full Loop** | The complete virtuous cycle: read → index → retrieve → skip re-read | V2.21 – V2.23 |

---

## Prerequisites

Before running any tests:

```bash
# 1. Confirm PostgreSQL is running with data from Phase 1 + Phase 2
psql -d claude_rag -c "SELECT COUNT(*) FROM memory_chunks;"
# Should show > 0 rows

# 2. Confirm hooks are configured
# On Windows, check:
type %USERPROFILE%\.claude\settings.json
# Should show PostToolUse hooks for Read, Bash, Grep
# Should show UserPromptSubmit hook
# Should show Stop hook

# 3. Confirm the async queue worker is running (or can be started)
python -m claude_rag.hooks.worker status
# Should show "running" or instructions to start

# 4. Open TWO terminals side-by-side:
#    Terminal 1: "Observer" — for monitoring DB and logs
#    Terminal 2: "Claude" — for running Claude Code sessions
```

---

## AREA A: Hook Interception Verification

**Goal:** Prove that EVERY Read, Bash, Grep, and prompt is captured in real time.

---

### TEST V2.1: Read Hook — Single File Capture

**What this proves:** When Claude reads a file, the hook fires and the content appears in the database within seconds.

**Setup (Terminal 1 — Observer):**
```sql
-- Note the current chunk count
SELECT COUNT(*) as before_count FROM memory_chunks;
-- Note the current max created_at
SELECT MAX(created_at) as latest_before FROM memory_chunks;
```

**Action (Terminal 2 — Claude Code):**
```
Open Claude Code in the llm-inference project directory, then type:

> Read the file setup_pgvector.py and tell me what it does.
```

Wait for Claude to respond.

**Verify (Terminal 1 — Observer):**
```sql
-- Check for NEW chunks created after the Read
SELECT mc.id, ms.file_path, mc.block_type, mc.created_at,
       LEFT(mc.content, 120) as preview
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE mc.created_at > '<latest_before timestamp>'
ORDER BY mc.created_at DESC;
```

**What you should see:**
- New rows with `file_path` containing `setup_pgvector.py`
- `created_at` timestamps within seconds of when Claude read the file
- `content` containing the actual code from setup_pgvector.py

**Also check the hook log:**
```bash
# Check structured log for the hook event
python -m claude_rag search-log --last 5 --type hook_read
# Should show: timestamp, file_path=setup_pgvector.py, status=indexed
```

**Pass Criteria:**
- [ ] New chunk(s) exist for setup_pgvector.py
- [ ] Timestamp is within 10 seconds of when Claude responded
- [ ] Content matches the actual file

---

### TEST V2.2: Read Hook — Multi-File Task

**What this proves:** When Claude reads MULTIPLE files in one task, ALL are captured — not just the first one.

**Action (Terminal 2 — Claude Code):**
```
> Compare the database connection patterns in app.py versus
  lambda-s3-trigger/ingestion-worker/app/database.py.
  Which is better designed and why?
```

Claude will read at least 2 files. Wait for it to finish.

**Verify (Terminal 1 — Observer):**
```sql
-- Find all chunks created in the last 2 minutes
SELECT ms.file_path, COUNT(*) as chunks, MIN(mc.created_at), MAX(mc.created_at)
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE mc.created_at > NOW() - INTERVAL '2 minutes'
GROUP BY ms.file_path
ORDER BY MIN(mc.created_at);
```

**What you should see:**
- At least 2 distinct file_path entries (app.py AND database.py)
- Chunks for both files, not just one

**Pass Criteria:**
- [ ] Both `app.py` and `database.py` appear in results
- [ ] Chunk counts are proportional to file sizes (larger file → more chunks)

---

### TEST V2.3: Bash Hook — Command Output Capture

**What this proves:** When Claude runs shell commands (grep, find, etc.), the output gets indexed.

**Action (Terminal 2 — Claude Code):**
```
> Search the codebase for all places where psycopg2.connect is called.
  List each file and line number.
```

Claude will likely use `grep` or `Bash` with grep inside it.

**Verify (Terminal 1 — Observer):**
```sql
SELECT mc.block_type, LEFT(mc.content, 200) as preview, mc.created_at
FROM memory_chunks mc
WHERE mc.block_type IN ('bash_output', 'grep_result', 'tool_output')
  AND mc.created_at > NOW() - INTERVAL '2 minutes'
ORDER BY mc.created_at DESC;
```

**What you should see:**
- Chunk(s) with block_type indicating command output
- Content containing the grep/search results

**Pass Criteria:**
- [ ] At least 1 bash/grep output chunk captured
- [ ] Content contains file paths and `psycopg2.connect` references

---

### TEST V2.4: UserPromptSubmit Hook — Intent Capture

**What this proves:** The user's prompt text (the "intent" layer) is indexed, not just the code Claude reads.

**Action (Terminal 2 — Claude Code):**
```
> I need to add rate limiting to the /legal/search endpoint to prevent
  abuse. What's the best approach given the existing FastAPI setup?
```

**Verify (Terminal 1 — Observer):**
```sql
SELECT mc.block_type, LEFT(mc.content, 300) as preview, mc.created_at,
       mc.metadata->>'session_id' as session
FROM memory_chunks mc
WHERE mc.block_type = 'user_intent'
  AND mc.created_at > NOW() - INTERVAL '2 minutes'
ORDER BY mc.created_at DESC;
```

**What you should see:**
- A chunk with `block_type = 'user_intent'`
- Content containing "rate limiting" and "/legal/search"
- This captures WHY Claude was doing the work, not just what it read

**Pass Criteria:**
- [ ] user_intent chunk exists
- [ ] Content matches or closely reflects the prompt you typed
- [ ] Session ID is populated in metadata

---

### TEST V2.5: Subagent / Agent Team Capture

**What this proves:** Tokens spent by subagents and agent teammates are ALSO captured, not just the main session.

**Action (Terminal 2 — Claude Code):**
```
> Use a subagent to investigate the ingestion pipeline in
  lambda-s3-trigger/ingestion-worker/. Have it document all the
  classes and their responsibilities.
```

Wait for the subagent to complete.

**Verify (Terminal 1 — Observer):**
```sql
-- Check for chunks with subagent session IDs
SELECT mc.metadata->>'session_id' as session,
       mc.metadata->>'agent_type' as agent_type,
       ms.file_path,
       mc.block_type,
       mc.created_at
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE mc.created_at > NOW() - INTERVAL '5 minutes'
ORDER BY mc.created_at DESC
LIMIT 20;
```

**What you should see:**
- Chunks from the subagent's session (different session_id from the main session)
- Files the subagent read (processor.py, database.py, embeddings.py, etc.)

**Pass Criteria:**
- [ ] Multiple session IDs visible (main + subagent)
- [ ] Subagent's file reads are captured

**NOTE:** If your hook implementation passes session context via environment variables,
verify those are propagated to subagent processes. If subagent captures are missing,
this is the most likely failure point.

---

### TEST V2.6: Hook Latency — No Slowdown

**What this proves:** Hooks don't slow Claude Code down perceptibly. The async queue is doing its job.

**Action:** Time a Claude Code interaction WITH hooks enabled vs. with hooks temporarily disabled.

```bash
# Test 1: With hooks (normal operation)
# Note the time when you send the prompt
> Read app.py lines 1-50 and summarize.
# Note the time when Claude responds
# Record: T_with_hooks = response_time

# Test 2: Temporarily disable hooks
# Rename or comment out hooks in settings.json
# Restart Claude Code
> Read app.py lines 1-50 and summarize.
# Record: T_without_hooks = response_time
# RE-ENABLE HOOKS after this test
```

**What you should see:**
- `T_with_hooks` and `T_without_hooks` should be within ~1-2 seconds of each other
- The hook adds negligible overhead because it just enqueues, it doesn't embed synchronously

**Pass Criteria:**
- [ ] Hook overhead < 2 seconds per interaction
- [ ] Claude Code doesn't show any "waiting for hook" messages

---

## AREA B: Enrichment Layer Verification

**Goal:** Prove that raw code chunks are enriched into the 3 layers (semantic summaries, structural signatures, decision context).

---

### TEST V2.7: Layer 1 — Semantic Summaries Exist

**What this proves:** Every ingested code file has a human-readable semantic summary alongside the raw chunks.

**Verify (Terminal 1):**
```sql
-- Find files that have raw chunks but check if they also have summaries
SELECT ms.file_path,
       SUM(CASE WHEN mc.block_type IN ('code', 'raw', 'file_content') THEN 1 ELSE 0 END) as raw_chunks,
       SUM(CASE WHEN mc.block_type = 'semantic_summary' THEN 1 ELSE 0 END) as summaries,
       SUM(CASE WHEN mc.block_type = 'structural_signature' THEN 1 ELSE 0 END) as signatures,
       SUM(CASE WHEN mc.block_type = 'decision_context' THEN 1 ELSE 0 END) as decisions
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
GROUP BY ms.file_path
ORDER BY raw_chunks DESC
LIMIT 15;
```

**What you should see:**
- For each file: `raw_chunks > 0` AND `summaries > 0`
- If any file has raw_chunks but 0 summaries, enrichment pipeline has a gap

**Pass Criteria:**
- [ ] Every file with raw chunks also has at least 1 semantic_summary
- [ ] Summary count is reasonable (roughly 1 per major class/function group)

---

### TEST V2.8: Layer 1 — Summary Quality Check

**What this proves:** Semantic summaries are actually useful — they describe purpose and relationships in natural language.

**Verify (Terminal 1):**
```sql
-- Read the actual summaries for a well-known file
SELECT mc.content
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%app.py%'
  AND mc.block_type = 'semantic_summary'
LIMIT 5;
```

**Human judgment:** Read each summary. Ask yourself:
- Does it describe what the code DOES, not just what it IS?
- Could you use this to decide "should I read this file?" without seeing the code?
- Does it mention relationships (e.g., "calls DatabaseManager", "uses psycopg2")?

**Pass Criteria:**
- [ ] Summaries are in natural language (not code)
- [ ] They describe purpose, not just structure
- [ ] They mention dependencies or relationships
- [ ] They're 50-150 tokens (concise, not bloated)

---

### TEST V2.9: Layer 2 — Structural Signatures Exist and Are Compact

**What this proves:** Code files have API-surface-only representations that are dramatically smaller than the full code.

**Verify (Terminal 1):**
```sql
-- Compare raw code size vs signature size for the same file
SELECT ms.file_path,
       SUM(CASE WHEN mc.block_type IN ('code', 'raw', 'file_content')
           THEN LENGTH(mc.content) ELSE 0 END) as raw_chars,
       SUM(CASE WHEN mc.block_type = 'structural_signature'
           THEN LENGTH(mc.content) ELSE 0 END) as sig_chars,
       ROUND(
           SUM(CASE WHEN mc.block_type = 'structural_signature'
               THEN LENGTH(mc.content) ELSE 0 END)::numeric /
           NULLIF(SUM(CASE WHEN mc.block_type IN ('code', 'raw', 'file_content')
               THEN LENGTH(mc.content) ELSE 0 END), 0) * 100, 1
       ) as compression_pct
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
GROUP BY ms.file_path
HAVING SUM(CASE WHEN mc.block_type = 'structural_signature' THEN 1 ELSE 0 END) > 0
ORDER BY raw_chars DESC
LIMIT 10;
```

**What you should see:**
- `compression_pct` should be 5-25% — signatures are much smaller than raw code
- For `app.py` (59KB raw), the signature should be a few KB at most

**Also inspect a signature:**
```sql
SELECT mc.content
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%app.py%'
  AND mc.block_type = 'structural_signature'
LIMIT 1;
```

**Human judgment:** Does it look like a `.pyi` stub file? Class names, method signatures, type hints, but no implementation bodies?

**Pass Criteria:**
- [ ] Signatures exist for code files
- [ ] Compression ratio is 5-25% of raw code size
- [ ] Signatures contain class/function signatures but NOT implementation details

---

### TEST V2.10: Layer 3 — Decision Context Extracted

**What this proves:** Design decisions and reasoning from sessions are captured.

**Verify (Terminal 1):**
```sql
SELECT mc.content, mc.metadata, mc.created_at
FROM memory_chunks mc
WHERE mc.block_type = 'decision_context'
ORDER BY mc.created_at DESC
LIMIT 5;
```

**What you should see:**
- Chunks describing WHY certain choices were made
- References to tradeoffs, alternatives considered, or requirements

**If zero results:** Decision context extraction depends on Claude's thinking blocks.
Run this to check if thinking blocks are being captured:
```sql
SELECT mc.block_type, COUNT(*)
FROM memory_chunks mc
GROUP BY mc.block_type
ORDER BY COUNT(*) DESC;
```
If 'thinking' or 'reasoning' blocks exist but 'decision_context' doesn't, the
decision extractor may not be running.

**Pass Criteria:**
- [ ] At least 1 decision_context chunk exists (after several sessions)
- [ ] Content describes reasoning, not just code

---

### TEST V2.11: Enrichment Pipeline Timing

**What this proves:** Enrichment happens within a reasonable time after raw ingestion (not stuck in a queue forever).

**Action (Terminal 2 — Claude Code):**
```
> Read the file fine-tuning/config.py and explain the training parameters.
```

**Verify (Terminal 1 — Observer):**
```sql
-- Watch chunks appear for this file over time
-- Run this query repeatedly every 10 seconds for 2 minutes:
SELECT mc.block_type, mc.created_at,
       EXTRACT(EPOCH FROM mc.created_at - MIN(mc.created_at) OVER()) as seconds_after_first
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%fine-tuning/config.py%'
  AND mc.created_at > NOW() - INTERVAL '3 minutes'
ORDER BY mc.created_at;
```

**What you should see:**
- First: raw/code chunks appear (within seconds of Claude's Read)
- Then: semantic_summary appears (within 30-60 seconds)
- Then: structural_signature appears (within 30-60 seconds)
- The enrichment layers trail behind the raw chunks but arrive reasonably quickly

**Pass Criteria:**
- [ ] Raw chunks appear within 10 seconds of Read
- [ ] Enrichment layers appear within 120 seconds of raw chunks
- [ ] All 3 layers eventually present for this file

---

## AREA C: Deduplication Verification

**Goal:** Prove the system doesn't re-index content it's already seen.

---

### TEST V2.12: Same File Read Twice — No Duplicates

**What this proves:** If Claude reads the same unchanged file in two sessions, chunks aren't duplicated.

**Setup (Terminal 1):**
```sql
-- Record current state for setup_pgvector.py
SELECT COUNT(*) as chunks_before
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%setup_pgvector.py%';
```

**Action (Terminal 2 — Claude Code):**
```
> Read setup_pgvector.py and tell me if the vector index type is appropriate.
```

Wait. Then start a NEW Claude Code session (exit and restart):
```
> Read setup_pgvector.py again. Is ivfflat the right choice or should we use HNSW?
```

**Verify (Terminal 1):**
```sql
-- Check: chunk count should NOT have doubled
SELECT COUNT(*) as chunks_after
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%setup_pgvector.py%';

-- Check: source should have updated timestamp, not a second row
SELECT id, file_path, file_hash, last_ingested_at, chunk_count
FROM memory_sources
WHERE file_path LIKE '%setup_pgvector.py%';
```

**What you should see:**
- `chunks_after` equals `chunks_before` (not doubled)
- Only 1 row in `memory_sources` for this file
- `last_ingested_at` updated to the most recent read

**Also check the log for skip messages:**
```bash
python -m claude_rag search-log --last 10 --type dedup
# Should show: "setup_pgvector.py already indexed (hash match), skipping"
```

**Pass Criteria:**
- [ ] Chunk count unchanged after second read
- [ ] Single source row (not duplicated)
- [ ] Log shows skip/dedup message

---

### TEST V2.13: Modified File Detected and Re-Indexed

**What this proves:** If a file changes, the system detects it and updates the index.

**Setup:** Pick a file you can safely modify temporarily (e.g., a test fixture or create a temporary file).

```bash
# Create a test file
echo "# Test Module\ndef hello(): return 'world'" > C:\Users\ClayMorgan\PycharmProjects\llm-inference\test_temp.py
```

**Action (Terminal 2 — Claude Code):**
```
> Read test_temp.py and describe it.
```

**Verify initial ingestion (Terminal 1):**
```sql
SELECT file_hash, chunk_count FROM memory_sources WHERE file_path LIKE '%test_temp.py%';
-- Record the hash
```

**Now modify the file:**
```bash
echo "\ndef goodbye(): return 'farewell'" >> C:\Users\ClayMorgan\PycharmProjects\llm-inference\test_temp.py
```

**Action (Terminal 2 — Claude Code):**
```
> Read test_temp.py again. What changed?
```

**Verify re-ingestion (Terminal 1):**
```sql
SELECT file_hash, chunk_count, last_ingested_at FROM memory_sources WHERE file_path LIKE '%test_temp.py%';
-- Hash should be DIFFERENT from before
-- last_ingested_at should be updated
```

**Pass Criteria:**
- [ ] Hash changed after file modification
- [ ] Chunks were re-indexed (content includes new function)
- [ ] Only 1 source row (replaced, not duplicated)

**Cleanup:**
```bash
del C:\Users\ClayMorgan\PycharmProjects\llm-inference\test_temp.py
```

---

### TEST V2.14: Overlapping Line Ranges — No Redundant Embedding

**What this proves:** If Claude reads lines 1-100 of a file in session A and lines 50-150 in session B, the overlapping content (lines 50-100) isn't embedded twice.

**Action (Terminal 2 — Claude Code):**
Session 1:
```
> Read app.py lines 1 to 100 and explain the imports and models.
```

Exit, restart Claude Code. Session 2:
```
> Read app.py lines 50 to 200 and explain the helper functions.
```

**Verify (Terminal 1):**
```sql
-- Check for chunk-level deduplication
SELECT mc.id, mc.chunk_index, LEFT(mc.content, 80) as preview,
       mc.metadata->>'line_start' as lines,
       mc.created_at
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%app.py%'
  AND mc.block_type IN ('code', 'raw', 'file_content')
ORDER BY mc.chunk_index;

-- Count unique content hashes vs total chunks
SELECT COUNT(*) as total_chunks,
       COUNT(DISTINCT md5(mc.content)) as unique_content
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%app.py%'
  AND mc.block_type IN ('code', 'raw', 'file_content');
```

**What you should see:**
- `total_chunks` should equal `unique_content` (no duplicates)
- OR if there are duplicates, they should have been detected and merged

**Pass Criteria:**
- [ ] No duplicate content chunks for the same file
- [ ] Overlapping line ranges were handled (merged or deduplicated)

---

### TEST V2.15: Coverage Report Accuracy

**What this proves:** The coverage report correctly shows what's indexed and what isn't.

**Action (Terminal 1):**
```bash
python -m claude_rag coverage
```

**What you should see:**
```
=== RAG Coverage Report ===
Project: llm-inference
Files indexed: XX / YY total source files (ZZ%)
Sessions indexed: N
Total chunks: NNN (breakdown by type)
  - raw/code: ...
  - semantic_summary: ...
  - structural_signature: ...
  - decision_context: ...
  - user_intent: ...
Last ingestion: X minutes ago

Files read most often (top 5):
  1. app.py (read N times across M sessions)
  ...

Enrichment status:
  - Files with all 3 layers: XX
  - Files awaiting enrichment: YY
```

**Human judgment:**
- Does the file count match reality? (Check: `find . -name "*.py" | wc -l`)
- Do "files read most often" match your actual Claude Code usage patterns?
- Is enrichment status accurate? (Cross-reference with V2.7 query)

**Pass Criteria:**
- [ ] Report runs without errors
- [ ] File counts are plausible
- [ ] Enrichment status matches database reality

---

## AREA D: RAG Retrieval Verification

**Goal:** Prove that Claude Code actually USES the RAG system and that the context it receives is relevant and useful.

---

### TEST V2.16: RAG Search Returns Relevant Results

**What this proves:** The hybrid search (semantic + keyword) returns relevant chunks for natural language queries.

**Action (Terminal 1):**
```bash
# Search for something you KNOW is in the index
python -m claude_rag search "hybrid search reciprocal rank fusion"
```

**What you should see:**
- Top results should be chunks from `app.py` lines 1139-1191 (the RRF implementation)
- Semantic summaries should rank HIGHER than raw code chunks
- Results should show similarity scores, search method (hybrid/semantic/keyword)

**Also test a conceptual query:**
```bash
python -m claude_rag search "how does authentication work in this project"
```

**What you should see:**
- Results from the legal RAG system (JWT validation, system prompts)
- Semantic summaries should capture this even if "authentication" doesn't appear verbatim

**Pass Criteria:**
- [ ] Top 3 results are genuinely relevant (human judgment)
- [ ] Semantic summaries appear in results (not just raw code)
- [ ] Similarity scores for top results > 0.5
- [ ] Results include search_method tags (hybrid, semantic, or keyword)

---

### TEST V2.17: RAG Provides Token-Efficient Context

**What this proves:** The formatted context fits within the token budget and prioritizes the most relevant information.

**Action (Terminal 1):**
```bash
# Request formatted context with a specific token budget
python -m claude_rag search "database connection management" --format --budget 2000
```

**What you should see:**
- Formatted output with source attribution blocks
- Total output ≤ 2000 tokens
- Highest-relevance results appear first
- A mix of summaries and signatures (not just raw code dumps)

**Measure compression:**
```bash
# Compare: raw file sizes of the relevant files vs formatted context size
python -m claude_rag search "database connection management" --format --budget 2000 --stats
# Should show something like:
#   Source files total: ~15,000 tokens
#   RAG context: 1,847 tokens (12.3% of raw)
#   Compression ratio: 8.1x
```

**Pass Criteria:**
- [ ] Output fits within specified token budget
- [ ] Compression ratio > 3x vs reading raw files
- [ ] Context is useful (human judgment: could you complete a task with just this?)

---

### TEST V2.18: MCP Server Tool Call Round-Trip

**What this proves:** The MCP server correctly receives queries and returns formatted context.

**Action (Terminal 1):**
```bash
# Test MCP server directly (without Claude Code)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m claude_rag.mcp_server.server
```

**What you should see:**
- JSON response listing the `rag_search` tool with its input schema

**Then test a tool call:**
```bash
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"rag_search","arguments":{"query":"embedding generation batch processing","token_budget":2048}}}' | python -m claude_rag.mcp_server.server
```

**What you should see:**
- JSON response with formatted context about the EmbeddingGenerator class
- Content from semantic summaries and structural signatures

**Pass Criteria:**
- [ ] tools/list returns valid tool definition
- [ ] tools/call returns relevant context
- [ ] Response time < 3 seconds

---

### TEST V2.19: Claude Code Calls RAG Before Reading Files

**What this proves:** THE KEY TEST. Claude Code prioritizes `rag_search` over direct file reads when instructed by CLAUDE.md.

**Prerequisite:** Ensure your project CLAUDE.md contains the RAG-first instructions:
```markdown
## RAG-First Context Strategy
When starting any coding task:
1. ALWAYS call rag_search first with a description of the current task
2. Review the returned context...
```

**Action (Terminal 2 — Claude Code):**
Start a FRESH Claude Code session:
```
> What embedding models does this project use and how are they configured?
```

**Verify (Terminal 1 — Observer):**

Immediately after Claude responds, check the session JSONL:
```bash
# Find the most recent session
# On Windows:
dir /b /od %USERPROFILE%\.claude\projects\*llm-inference*\*.jsonl | tail -1

# Parse the session to find tool call order
python -c "
import json, sys, glob, os

# Find latest session JSONL (adjust path for your system)
session_dir = os.path.expanduser('~/.claude/projects')
jsonl_files = glob.glob(f'{session_dir}/**/*.jsonl', recursive=True)
latest = max(jsonl_files, key=os.path.getmtime)

print(f'Session: {latest}')
print(f'Tool call order:')
print('=' * 60)

tool_calls = []
with open(latest, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            record = json.loads(line)
            if record.get('type') == 'assistant':
                for block in record.get('message', {}).get('content', []):
                    if block.get('type') == 'tool_use':
                        name = block['name']
                        inp = block.get('input', {})
                        summary = ''
                        if name == 'rag_search':
                            summary = f'query={inp.get(\"query\", \"\")[:60]}'
                        elif name == 'Read':
                            summary = f'file={inp.get(\"file_path\", \"\")}'
                        elif name == 'Bash':
                            summary = f'cmd={inp.get(\"command\", \"\")[:60]}'
                        tool_calls.append((name, summary))
                        print(f'  {len(tool_calls)}. {name}: {summary}')
        except:
            continue

# Check: was rag_search called BEFORE any Read?
rag_idx = next((i for i, (n, _) in enumerate(tool_calls) if n == 'rag_search'), None)
read_idx = next((i for i, (n, _) in enumerate(tool_calls) if n == 'Read'), None)

print()
if rag_idx is not None and (read_idx is None or rag_idx < read_idx):
    print('✅ RAG-FIRST CONFIRMED: rag_search called before any Read')
elif rag_idx is None:
    print('❌ FAIL: rag_search was never called')
else:
    print('❌ FAIL: Read was called before rag_search')
"
```

**What you should see:**
```
Tool call order:
==================================================
  1. rag_search: query=embedding models configuration this project
  2. Read: file=app.py        ← only if RAG wasn't sufficient
```

**Pass Criteria:**
- [ ] `rag_search` appears as tool call #1 (BEFORE any Read/Bash/Grep)
- [ ] If Claude read files AFTER rag_search, it means RAG wasn't sufficient — check if the context was relevant

---

### TEST V2.20: RAG Fallback — Graceful When No Results

**What this proves:** When RAG has nothing relevant, Claude falls back to normal file reading without errors.

**Action (Terminal 2 — Claude Code):**
Ask about something that has NEVER been indexed:
```
> What does the Dockerfile do? Walk me through each step.
```
(Assuming Dockerfile hasn't been read in previous sessions, or ask about a completely
unrelated topic)

**Verify transcript order:**
```
Expected tool call order:
  1. rag_search: query=Dockerfile steps   ← returns empty/low relevance
  2. Read: file=Dockerfile                ← fallback to direct read
```

**What you should see:**
- rag_search is still called first (respecting CLAUDE.md instructions)
- It returns empty or low-relevance results
- Claude then proceeds to read the file directly
- No errors or crashes from the empty RAG response

**Pass Criteria:**
- [ ] rag_search called first (even for unknown content)
- [ ] Claude gracefully falls back to Read after low/no RAG results
- [ ] No error messages in Claude's output about the RAG system

---

## AREA E: Full Virtuous Loop — The Ultimate Tests

**Goal:** Prove the complete cycle: read → index → use RAG → avoid redundant reads.

---

### TEST V2.21: Session B Benefits from Session A's Work

**What this proves:** Knowledge from one session carries over to the next via RAG. Claude spends FEWER tokens in the second session because it gets context from RAG instead of re-reading files.

**Session A (Terminal 2 — Claude Code):**
```
> Analyze the complete legal search implementation. Explain how hybrid search
  works, what indexes are used, and how the RRF scoring formula works.
  Look at app.py, schema_legal.sql, and any related files.
```

Wait for Claude to finish. Note how many files it reads (check transcript or hook log).

**Exit Claude Code. Wait 60 seconds for enrichment to complete.**

Verify enrichment (Terminal 1):
```sql
SELECT mc.block_type, COUNT(*), SUM(LENGTH(mc.content)) as total_chars
FROM memory_chunks mc
JOIN memory_sources ms ON mc.source_id = ms.id
WHERE ms.file_path LIKE '%app.py%' OR ms.file_path LIKE '%schema_legal%'
GROUP BY mc.block_type;
-- Should show raw + semantic_summary + structural_signature
```

**Session B (Terminal 2 — new Claude Code session):**
```
> I need to modify the legal hybrid search to add a date weighting factor
  that boosts newer documents. What files need to change and where
  specifically should I make the modifications?
```

**Verify (Terminal 1 — parse Session B's transcript):**
```python
# Run the tool-call-order script from V2.19 against Session B's JSONL
# Compare:
#   - Session A: probably 3-5 Read calls (app.py, schema_legal.sql, etc.)
#   - Session B: rag_search first, then maybe 0-1 targeted Read calls
```

**What you should see:**
- Session B's first tool call is `rag_search`
- Claude gets enough context from RAG to answer specifically ("modify lines 1146-1191 in app.py, add a date_weight parameter to the CTE...")
- Session B makes FEWER file reads than Session A
- If Claude does read a file, it's a TARGETED read (specific line range), not a broad exploration

**Pass Criteria:**
- [ ] Session B calls rag_search before Read
- [ ] Session B has fewer Read calls than Session A
- [ ] Claude's answer in Session B is specific (mentions exact locations)
- [ ] Quality of answer in Session B is comparable to Session A

---

### TEST V2.22: Token Savings Measurement

**What this proves:** Quantitative evidence that RAG reduces token consumption.

**Setup:** You need token usage data from session JSONLs.

```python
import json, glob, os

def count_session_tokens(jsonl_path):
    """Count total input + output tokens for a session."""
    input_tokens = 0
    output_tokens = 0
    read_calls = 0

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get('type') == 'assistant':
                    usage = record.get('message', {}).get('usage', {})
                    input_tokens += usage.get('input_tokens', 0)
                    output_tokens += usage.get('output_tokens', 0)
                    # Count Read calls
                    for block in record.get('message', {}).get('content', []):
                        if block.get('type') == 'tool_use' and block.get('name') == 'Read':
                            read_calls += 1
            except:
                continue

    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'read_calls': read_calls
    }

# Compare Session A (exploration) vs Session B (RAG-assisted)
session_a = count_session_tokens(r"<session-a-jsonl-path>")
session_b = count_session_tokens(r"<session-b-jsonl-path>")

print(f"Session A (exploration):")
print(f"  Input tokens:  {session_a['input_tokens']:,}")
print(f"  Read calls:    {session_a['read_calls']}")
print()
print(f"Session B (RAG-assisted):")
print(f"  Input tokens:  {session_b['input_tokens']:,}")
print(f"  Read calls:    {session_b['read_calls']}")
print()

savings = session_a['input_tokens'] - session_b['input_tokens']
pct = (savings / session_a['input_tokens'] * 100) if session_a['input_tokens'] > 0 else 0
print(f"Token savings: {savings:,} ({pct:.1f}%)")
print(f"Read call reduction: {session_a['read_calls']} → {session_b['read_calls']}")
```

**What you should see:**
- Session B uses fewer input tokens than Session A for comparable tasks
- Read call count is lower in Session B

**Pass Criteria:**
- [ ] Session B input tokens < Session A input tokens
- [ ] Read calls reduced by at least 50%
- [ ] Token savings > 20%

---

### TEST V2.23: The "Week of Work" Simulation

**What this proves:** The system works reliably across many sessions and accumulates useful knowledge over time.

This is a 30-minute hands-on test simulating a week of Claude Code interactions.

**Step 1: Rapid-fire 5 diverse sessions** (2-3 minutes each):

```
Session 1: "Explain the product ingestion pipeline end to end"
Session 2: "How is error handling done across the API endpoints?"
Session 3: "What embedding models are used and what are their dimensions?"
Session 4: "Review the database schema for potential improvements"
Session 5: "How could we add a caching layer to the search endpoints?"
```

Exit and restart Claude Code between each session.

**Step 2: After all 5 sessions, check the database:**
```sql
-- Total system state
SELECT
    (SELECT COUNT(*) FROM memory_sources) as total_sources,
    (SELECT COUNT(*) FROM memory_chunks) as total_chunks,
    (SELECT COUNT(*) FROM memory_chunks WHERE block_type = 'semantic_summary') as summaries,
    (SELECT COUNT(*) FROM memory_chunks WHERE block_type = 'structural_signature') as signatures,
    (SELECT COUNT(*) FROM memory_chunks WHERE block_type = 'user_intent') as intents;
```

**Step 3: Run the synthesis session:**
```
Session 6: "Based on everything we've discussed about this project,
            create a technical architecture document describing the key
            components, their relationships, and design decisions."
```

**What you should see:**
- Session 6 calls rag_search and gets a WEALTH of context from sessions 1-5
- Claude produces a comprehensive document WITHOUT reading many files directly
- The architecture doc references specific decisions and patterns from earlier sessions

**Step 4: Final coverage report:**
```bash
python -m claude_rag coverage
```

**Pass Criteria:**
- [ ] 5 sessions produced growing index (monotonically increasing chunk count)
- [ ] Session 6 leveraged RAG heavily (check transcript for rag_search calls)
- [ ] Session 6 produced accurate architecture doc (human judgment)
- [ ] No duplicate chunks accumulated across the 5 sessions
- [ ] Coverage report shows meaningful % of codebase indexed

---

## VERIFICATION SCORECARD

Print and fill in as you complete each test:

```
AREA A: Hook Interception
  V2.1  Read Hook (single file)          [ ] PASS  [ ] FAIL  Notes: ________
  V2.2  Read Hook (multi-file)           [ ] PASS  [ ] FAIL  Notes: ________
  V2.3  Bash Hook (command output)       [ ] PASS  [ ] FAIL  Notes: ________
  V2.4  UserPromptSubmit (intent)        [ ] PASS  [ ] FAIL  Notes: ________
  V2.5  Subagent / Agent Team capture    [ ] PASS  [ ] FAIL  Notes: ________
  V2.6  Hook Latency (no slowdown)       [ ] PASS  [ ] FAIL  Notes: ________

AREA B: Enrichment Layers
  V2.7  Semantic summaries exist         [ ] PASS  [ ] FAIL  Notes: ________
  V2.8  Summary quality (human review)   [ ] PASS  [ ] FAIL  Notes: ________
  V2.9  Structural signatures compact    [ ] PASS  [ ] FAIL  Notes: ________
  V2.10 Decision context extracted       [ ] PASS  [ ] FAIL  Notes: ________
  V2.11 Enrichment pipeline timing       [ ] PASS  [ ] FAIL  Notes: ________

AREA C: Deduplication
  V2.12 Same file no duplicates          [ ] PASS  [ ] FAIL  Notes: ________
  V2.13 Modified file re-indexed         [ ] PASS  [ ] FAIL  Notes: ________
  V2.14 Overlapping ranges deduped       [ ] PASS  [ ] FAIL  Notes: ________
  V2.15 Coverage report accuracy         [ ] PASS  [ ] FAIL  Notes: ________

AREA D: RAG Retrieval
  V2.16 Search returns relevant results  [ ] PASS  [ ] FAIL  Notes: ________
  V2.17 Token-efficient context          [ ] PASS  [ ] FAIL  Notes: ________
  V2.18 MCP server round-trip            [ ] PASS  [ ] FAIL  Notes: ________
  V2.19 RAG called BEFORE file reads     [ ] PASS  [ ] FAIL  Notes: ________
  V2.20 Graceful fallback on empty RAG   [ ] PASS  [ ] FAIL  Notes: ________

AREA E: Full Loop
  V2.21 Session B benefits from A        [ ] PASS  [ ] FAIL  Notes: ________
  V2.22 Token savings measured           [ ] PASS  [ ] FAIL  Notes: ________
  V2.23 Week simulation                  [ ] PASS  [ ] FAIL  Notes: ________

TOTAL: ___/23 PASS

System ready for production: [ ] YES (22+/23)  [ ] NO (investigate failures)
```

---

## If Tests Fail: Diagnostic Flowchart

```
Hooks not firing (V2.1-V2.5)?
  → Check: settings.json has hooks configured
  → Check: hook script path is absolute and correct for Windows
  → Check: Python is on PATH for the hook process
  → Check: hook script has execute permissions
  → Check: async queue worker is running

No enrichment (V2.7-V2.11)?
  → Check: enrichment worker/pipeline is running
  → Check: enrichment queue is not stuck (inspect queue DB/file)
  → Check: LLM for summarization is accessible (local model loaded or API key set)

Duplicates appearing (V2.12-V2.14)?
  → Check: file hash comparison is using same algorithm (SHA-256)
  → Check: chunk content hash is computed before insert
  → Check: upsert logic deletes old chunks before inserting new

RAG not called first (V2.19)?
  → Check: CLAUDE.md contains RAG-first instructions
  → Check: MCP server is configured in Claude Code settings
  → Check: MCP server process is running
  → Check: rag_search tool appears in Claude Code's tool list
```
