Bring up all AWS infrastructure and run the full test suite to verify everything works.

## Steps

### 1. Start AWS infrastructure
Run `./aws-startup.sh` from the project root to:
- Check if RDS instance (llm-postgres) exists
  - If deleted: restore from snapshot (llm-postgres-dormant) — takes ~10 min
  - If stopped: start it normally
  - If available: skip
- Wait for RDS to become available
- Scale ECS services: llm-inference-service to 1, llm-search-engine to 2
- Wait for all tasks to reach RUNNING state
- Hit the ALB health endpoint to confirm the system is live

### 2. Run all tests
After infrastructure is confirmed up, run the full claude-rag test suite:

```bash
cd claude-rag && PGPASSWORD=postgres PYTHONPATH=src python -m pytest tests/ -v --tb=short 2>&1; cd ..
```

### 3. Report results
- Print a summary of which tests passed/failed
- If any tests failed, investigate and report the likely cause
- Confirm the overall system health status