Stress-test the RAG pipeline with 10 agents that each independently scan the entire project.

## Pre-flight: Ensure All Services Are Running

Before spawning agents, verify and start all required services:

```bash
# 1. Check PostgreSQL is up and schema exists
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d claude_rag -c "SELECT COUNT(*) FROM memory_chunks;" 2>&1

# 2. Run migration if needed
PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag.db.migrate

# 3. Start the background ingestion worker (processes hook queue -> DB)
PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src nohup python3 -m claude_rag worker > /tmp/claude-rag-worker.log 2>&1 &

# 4. Kill any stale stats server and start fresh
lsof -ti :9473 | xargs kill -9 2>/dev/null
PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src nohup python3 -m claude_rag.monitoring.stats_server > /dev/null 2>&1 &

# 5. Verify services
sleep 3
curl -s http://localhost:9473/health
```

Wait for all services to be confirmed healthy before proceeding.

## Agent Tasks

Create a team called `rag-full-scan` with 10 identical tasks. Each agent performs ALL of the following independently (no work sharing):

1. **RAG SEARCHES FIRST**: Run 5 searches via CLI. If RAG returns results, use them. If not, fall back to grep.
   ```
   PGPASSWORD=postgres PGPORT=5433 PYTHONPATH=claude-rag/src python3 -m claude_rag search "QUERY"
   ```
   Queries:
   - "hybrid search RRF scoring"
   - "hook deduplication cache"
   - "embedding generation pipeline"
   - "database schema migration"
   - "MCP server tool registration"

2. **STRUCTURE**: Glob for all Python, SQL, shell script, and markdown files. Report counts by type.

3. **CODE READS**: Read and summarize these key files:
   - claude-rag/src/claude_rag/search/hybrid.py
   - claude-rag/src/claude_rag/mcp_server/server.py
   - claude-rag/src/claude_rag/hooks/post_tool_use.py
   - claude-rag/src/claude_rag/config.py
   - claude-rag/src/claude_rag/monitoring/stats_server.py

4. **GREP SEARCHES**: Search the codebase for:
   - "RELEVANCE_THRESHOLD"
   - "def hybrid_search"
   - "log_event"
   - "cosine_similarity"

Spawn all 10 agents in parallel. When all agents report back, show the final dashboard stats from `curl -s http://localhost:9473/stats` and shut down the team.

## What to Look For

The key metric is **rag_first_pct** — as early agents read and index files, later agents (or later searches by the same agents) should find that content via RAG search instead of needing to grep. The dashboard should show:
- **rag_first rising** as the DB fills with indexed content
- **fallback_rate dropping** as RAG starts returning useful results
- **chunks_total growing** as the worker ingests staging files
- **dedup_hits increasing** as agents read files already in the dedup cache