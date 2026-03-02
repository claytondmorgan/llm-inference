Start all services locally and run the full test battery to verify everything works.

## Steps

### 1. Start local services and run all tests
Run `./local-dev-test.sh` from the project root to:
- Start PostgreSQL, Python FastAPI, and Java Spring Boot services locally via `local-dev.sh`
- Run the Python Inference API test suite (`test-inference-api.sh`)
- Run the Legal Document Search API test suite (`test-legal-api.sh`)
- Run the claude-rag pytest suite (`claude-rag/tests/`)

### 2. Report results
- Print a summary of which test suites passed/failed
- If any tests failed, investigate the log files in `logs/` and report the likely cause
- Confirm the overall system health status
- Mention `./local-dev-stop.sh` for clean shutdown