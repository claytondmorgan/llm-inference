Start all services locally for development and report health status.

## Steps

### 1. Start local dev environment
Run `./local-dev.sh` from the project root to:
- Ensure the PostgreSQL container (claude-rag-pg) is running on port 5433
- Create the `llmdb` database if it doesn't exist
- Run schema migration (migrate_schema.py)
- Start the Python FastAPI service on port 8000
- Build and start the Java Spring Boot service on port 8080

### 2. Verify health
After services are started, verify:
```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8080/api/health
```

### 3. Report results
- Print which services are running and their URLs
- If any service failed to start, check the log files in `logs/` and report the likely cause
- Mention `./local-dev-stop.sh` for clean shutdown