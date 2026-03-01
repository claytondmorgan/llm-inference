# Session Summary — AWS Cost Management & Test Fixes

## New Files Created

### 1. `aws-shutdown.sh` — Shuts down all AWS infrastructure
- Scales all 3 ECS services (llm-inference-service, llm-search-engine, llm-ingestion-worker) to desired=0
- Waits for running tasks to drain (polls every 10s, timeout 120s)
- Stops RDS instance (llm-postgres)
- Flags: `--dry-run`, `--skip-rds`, `--help`
- Idempotent — safe to re-run, skips resources already at target state
- Color output with plain-text fallback

### 2. `aws-startup.sh` — Brings all AWS infrastructure back up
- Starts RDS and waits for `available` status (polls every 30s, timeout 600s)
- Scales llm-inference-service → 1, llm-search-engine → 2 (ingestion-worker stays at 0)
- Waits for tasks to reach RUNNING (polls every 15s, timeout 300s)
- Hits ALB health endpoint to confirm system is live
- Flags: `--dry-run`, `--skip-rds`, `--help`

### 3. `.claude/commands/startup-and-test.md` — Skill (`/startup-and-test`)
- Runs `aws-startup.sh`, then runs full test suite with `PGPORT=5433`

### 4. `.claude/commands/shutdown.md` — Skill (`/shutdown`)
- Runs `aws-shutdown.sh` and reports final state

## Files Modified

### 5. `claude-rag/tests/test_dedup.py` — Fixed `TestHookEventDedup` (4 tests)
- **Problem:** Tests referenced `post_tool_use._dedup_cache` (in-memory dict) which was refactored to a file-backed JSON cache using `_load_dedup_cache(state_dir)`
- **Fix:** Updated `setup_method` to create a temp directory instead of clearing an in-memory dict. Updated all 4 test methods to pass `self._state_dir` as the `state_dir` argument to `_check_dedup_cache()`. Updated time mocking from `mock_time.monotonic` to `mock_time.time` to match the refactored implementation.

### 6. `claude-rag/CLAUDE.md` — Updated Environment Setup section
- Docker port mapping changed from `-p 5432:5432` to `-p 5433:5432`
- Added `PGPORT=5433` to migration and test commands
- **Reason:** Local machine has another Postgres on 5432; the claude-rag-pg container is mapped to 5433

## Key Details for Another Machine

- The docker container `claude-rag-pg` must map to a free port. If 5432 is available, use `-p 5432:5432` and skip `PGPORT`. If not, use `-p 5433:5432` and set `PGPORT=5433`.
- Both shell scripts use Bash 3.2-compatible syntax (no associative arrays) for macOS compatibility.
- Test command: `cd claude-rag && source .venv/bin/activate && PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=src python -m pytest tests/ -v`
- Full test results: **162 passed, 11 skipped** (skips are Phase 2 tests requiring live MCP server / multi-session simulation)

## AWS Cost Reference

| State | Cost/day |
|-------|----------|
| Everything running | ~$12.94 |
| Everything stopped | ~$0.80 |
| ECS off, RDS on | ~$2.24 |
