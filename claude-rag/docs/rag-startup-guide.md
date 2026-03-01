# RAG System Startup & Monitoring Guide

## The Problem You're Solving

Every time Claude Code starts a session — whether you type a prompt, a subagent spawns,
or an agent team member wakes up — it needs to:

1. **WRITE side:** Capture every file read, command run, and prompt into the RAG pipeline
2. **READ side:** Query the RAG database before reading files directly

Both sides must be active for EVERY Claude Code process. Here's how to guarantee that.

---

## Step 1: Install the Hooks (settings.json)

Claude Code hooks are the mechanism that ensures every session and subagent automatically
participates in the RAG system. Hooks are inherited by subagents and agent team members.

Edit `~/.claude/settings.json` (on Windows: `%USERPROFILE%\.claude\settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/rag_preflight.py"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read",
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/post_read.py"
      },
      {
        "matcher": "Bash",
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/post_bash.py"
      },
      {
        "matcher": "Grep",
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/post_grep.py"
      }
    ],
    "UserPromptSubmit": [
      {
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/prompt_capture.py"
      }
    ],
    "Stop": [
      {
        "command": "python C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag/src/claude_rag/hooks/session_end.py"
      }
    ]
  },
  "mcpServers": {
    "claude-rag": {
      "command": "python",
      "args": [
        "-m", "claude_rag.mcp_server.server"
      ],
      "cwd": "C:/Users/ClayMorgan/PycharmProjects/llm-inference/claude-rag",
      "env": {
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGUSER": "postgres",
        "PGPASSWORD": "your_password",
        "PGDATABASE": "claude_rag"
      }
    }
  }
}
```

### Why this works for subagents and agent teams

Claude Code hooks defined in `~/.claude/settings.json` (global settings) are loaded by
EVERY Claude Code process on the machine. This includes:

- **Main sessions** you start manually
- **Subagents** spawned via the Task tool (they inherit the parent's settings)
- **Agent team members** (each teammate is a full Claude Code instance that loads settings.json)
- **Background agents** (same — they read settings.json on start)

The `SessionStart` hook (rag_preflight.py) runs for each of these, verifying both sides
are functional and injecting RAG status into that session's context.

The `PostToolUse` hooks fire for every tool call in every process. When a subagent reads
a file, the hook fires in that subagent's process and captures the read.

---

## Step 2: Start the Background Services

You need two background processes running before Claude Code sessions:

### Terminal 1: Enrichment Worker
```bash
cd C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag
python -m claude_rag.enrichment.worker
```
This processes the async queue — taking raw chunks and generating semantic summaries,
structural signatures, and decision context.

### Terminal 2: Stats Server (for the dashboard)
```bash
cd C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag
python rag_stats_server.py
```
Serves metrics at http://localhost:9473/stats for the live dashboard.

### Optional: Start both with one command
Create `start_rag.bat`:
```bat
@echo off
echo Starting RAG System...
start "RAG Enrichment" cmd /k "cd /d C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag && python -m claude_rag.enrichment.worker"
start "RAG Stats" cmd /k "cd /d C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag && python rag_stats_server.py"
echo.
echo RAG services started. Open Claude Code when ready.
echo Dashboard: open rag_dashboard.jsx artifact in Claude.ai
echo.
echo Running preflight check...
python -m claude_rag.hooks.rag_preflight
```

---

## Step 3: Verify It Works (The Preflight Check)

Run the preflight manually to see the status:

```bash
python C:\...\claude-rag\src\claude_rag\hooks\rag_preflight.py
```

You should see:
```
[RAG PREFLIGHT] ✅ RAG SYSTEM FULLY OPERATIONAL (127ms)

  DB: 23 files indexed, 342 chunks
      Layers: code=178, decision_context=23, semantic_summary=89, structural_signature=52
      Latest: 2026-02-26T14:32:01
  WRITE: ✅ All hooks configured (Read, Bash, Grep, Prompt capture)
  READ: ✅ MCP server configured (stdio)
        → Use rag_search tool BEFORE reading files directly

  Run 'python -m claude_rag preflight' for full diagnostic details.
```

**If any line shows ❌:**
- DB issues: check PostgreSQL is running, credentials correct
- WRITE issues: check hook paths in settings.json are absolute and correct
- READ issues: check mcpServers entry in settings.json

---

## Step 4: Watch It Live (The Dashboard)

The dashboard (rag_dashboard.jsx) starts in **demo mode** showing simulated data.
Click the "demo" button in the top right to switch to **live mode**, which polls
http://localhost:9473/stats (the stats server from Step 2).

### What to watch during a Claude Code session:

**Write side (left panels):**
- "Hooks Fired" counter should increment as Claude reads files
- "Chunks" should grow as new content is indexed
- "Dedup Hits" shows redundant reads being skipped (good!)
- "Hook Latency" should stay under 100ms (if it's over 200ms, the async queue isn't working)
- "Ingestion Queue" should stay near 0 — if it grows, enrichment is falling behind

**Read side (right panels):**
- "RAG Searches" should increment when Claude calls rag_search
- "Relevance" should be >70% — if lower, embedding quality may need tuning
- "RAG-First" should be >80% — if lower, CLAUDE.md instructions may need strengthening
- "Fallback" should be <15% — shows how often RAG had nothing useful

**Benchmark section:**
- Shows RAG ON vs OFF comparison after you run the benchmark
- Token savings and read reductions are the key metrics

---

## Step 5: Run the Benchmark (Baseline for Refinement)

The benchmark runs 6 standardized tasks with RAG on and off:

```bash
cd C:\Users\ClayMorgan\PycharmProjects\llm-inference\claude-rag

# See the tasks first
python rag_benchmark.py --list-tasks

# Run full benchmark (takes ~15-20 minutes)
python rag_benchmark.py --run-all

# View results
python rag_benchmark.py --report
```

The benchmark:
1. Runs 6 tasks with RAG enabled (hooks + MCP active)
2. Temporarily disables RAG (removes MCP, disables hooks)
3. Runs the same 6 tasks without RAG
4. Re-enables RAG
5. Produces a comparison report
6. Writes results to the dashboard's benchmark panel

**After the benchmark, rate each answer 1-5:**
```bash
python rag_benchmark.py --score <run_id>
```

### Re-running benchmarks for continuous improvement

After making changes to the RAG system (better chunking, different embeddings,
improved prompts), re-run the benchmark to measure improvement:

```bash
python rag_benchmark.py --run-all
# Results automatically update the dashboard's benchmark panel
```

---

## How Each Hook Works

### SessionStart → rag_preflight.py
- Fires when ANY Claude Code session starts (main, subagent, agent team member)
- Checks DB, hooks, MCP, enrichment worker, queue depth
- Prints status summary → injected into Claude's context
- Claude sees "[RAG PREFLIGHT] ✅ RAG SYSTEM FULLY OPERATIONAL" and knows to use rag_search
- Writes session metrics for the dashboard

### PostToolUse (Read) → post_read.py
- Fires AFTER Claude reads a file
- Receives file_path and file content
- Checks dedup (has this exact content been indexed already?)
- If new/changed: queues for chunking → embedding → storage
- Logs event to events.jsonl for dashboard

### PostToolUse (Bash) → post_bash.py
- Fires AFTER Claude runs a shell command
- Captures command + stdout/stderr
- Filters out trivial commands (ls, pwd, cd)
- Queues meaningful output for indexing

### PostToolUse (Grep) → post_grep.py
- Fires AFTER Claude searches with Grep/Glob
- Captures search patterns and results
- Especially valuable — shows WHAT Claude was looking for

### UserPromptSubmit → prompt_capture.py
- Fires when user sends a prompt
- Captures the intent ("I need to add rate limiting...")
- Indexes as block_type="user_intent"
- This is what makes future RAG searches match on TASK descriptions, not just code

### Stop → session_end.py
- Fires when session ends
- Waits for session-memory summary to be written
- Ingests the summary as a high-value chunk
- Persists hook counters for dashboard continuity

---

## Troubleshooting

### Hooks not firing for subagents
- Verify settings.json is in the GLOBAL location (~/.claude/settings.json)
- Project-level .claude/settings.json only applies to that project's main session
- Subagents read from the global settings

### MCP server not loading
- Check `claude --mcp-status` to see if claude-rag is listed
- Check the MCP server logs: `python -m claude_rag.mcp_server.server 2>&1`
- Verify the `cwd` path is correct and the module is importable

### Dashboard shows "Cannot reach stats server"
- Ensure rag_stats_server.py is running on port 9473
- Click the "demo/live" toggle to switch to demo mode for testing the UI
- Check firewall isn't blocking localhost:9473

### Queue depth keeps growing
- Enrichment worker may be crashed or slow
- Check: `python -m claude_rag.enrichment.worker status`
- If using LLM-based summarization, check model is accessible

### RAG-First percentage is low
- Strengthen CLAUDE.md instructions:
  ```markdown
  ## CRITICAL: RAG-First Context Strategy
  You have access to a rag_search MCP tool. ALWAYS call it FIRST before
  reading any files. It contains semantic summaries and structural signatures
  of code you've already analyzed. Only read files directly if rag_search
  returns insufficient context.
  ```
- Check that MCP server is actually responding to tool calls

---

## Architecture Summary

```
┌──────────────────────────────────────────────────────────────────┐
│                     Claude Code Session                          │
│  (main session, subagent, or agent team member)                  │
│                                                                  │
│  SessionStart ──→ rag_preflight.py ──→ status injected           │
│                                                                  │
│  User types prompt ──→ prompt_capture.py ──→ queue               │
│                                                                  │
│  Claude calls rag_search (MCP) ──→ MCP Server ──→ hybrid search  │
│          ↑ context returned                    ↓                 │
│                                          PostgreSQL              │
│  Claude calls Read ──→ post_read.py ──→ queue  ↓                 │
│  Claude calls Bash ──→ post_bash.py ──→ queue  ↓                 │
│  Claude calls Grep ──→ post_grep.py ──→ queue  ↓                 │
│                                                ↓                 │
│  Session ends ──→ session_end.py ──→ summary ingestion           │
└───────────────────────────────────┬──────────────────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │      Async Queue              │
                    │  (fast enqueue, ~50ms)        │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │    Enrichment Worker           │
                    │  raw → chunk → embed → store   │
                    │  raw → summarize → store        │
                    │  raw → extract sigs → store     │
                    │  raw → extract decisions         │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │     PostgreSQL + pgvector       │
                    │  memory_sources                 │
                    │  memory_chunks (with vectors)   │
                    │  HNSW + GIN indexes             │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │     Stats Server (port 9473)   │
                    │  polls DB + reads events.jsonl  │
                    │  serves /stats for dashboard   │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │     Live Dashboard (React)     │
                    │  write side: hooks, chunks     │
                    │  read side: searches, relevance│
                    │  benchmark: RAG on vs off      │
                    └────────────────────────────────┘
```
