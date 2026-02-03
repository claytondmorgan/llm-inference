# LLM Inference API with Vector Search

## Running the API Tests

Note: for ease of evaluation the inference service and java search service have been deployed to aws. To run locally takes multiple setup steps: database, 2 servers

The `test-inference-api.sh` script provides comprehensive integration tests for the Python Inference Service API.

### Prerequisites

1. **Python inference service running** - Start the API server first:
   ```bash
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 8080
   ```

2. **Database with data** - Some tests require documents/ingested records in the database for search operations to return meaningful results.

3. **curl and Python 3** - Required for making HTTP requests and parsing JSON responses.

### Running the Tests

**Basic usage (localhost:8080):**
```bash
./test-inference-api.sh
```

**With a custom base URL:**
```bash
./test-inference-api.sh http://lm-alb-1402483560.us-east-1.elb.amazonaws.com
./test-inference-api.sh http://192.168.1.100:8080
```

### Test Coverage

The test suite includes 37 tests covering:

| Category | Tests |
|----------|-------|
| Health & Info Endpoints | `/health`, `/` service info |
| Embed Endpoint | Text embedding, dimension validation, error handling |
| Text Generation | `/generate` with various parameters |
| Document Endpoints | Add, batch add, count, delete documents |
| Search (documents table) | `/search` with query and top_k parameters |
| Search (ingested_records) | `/search/records` with filters and field selection |
| Semantic Search | Natural language queries |
| RAG Endpoint | `/rag` query with answer and sources |
| Ingestion Endpoints | Jobs listing, stats, record counts |
| Error Handling | Invalid inputs, missing resources |
| Performance | Latency checks, sequential request handling |

### Interpreting Results

- **PASS** (green) - Test succeeded
- **FAIL** (red) - Test failed with details shown
- **WARN** (yellow) - Test passed but with a warning (e.g., slow latency)

The script exits with code `0` if all tests pass, or `1` if any test fails.

### Example Output

```
==============================================
Python Inference Service API Tests
Base URL: http://localhost:8080
==============================================

--- Health & Info Endpoints ---

GET /health returns 200                                 PASS
GET / returns service info                              PASS
GET / shows version 3.0.0                               PASS

...

==============================================
Test Results
==============================================
Passed: 37
Failed: 0

All tests passed!
```