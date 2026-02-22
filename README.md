# LLM Inference API with Vector Search & Legal Document Search

## Models (v5.0.0)

| Component | Model | Details |
|-----------|-------|---------|
| **Legal Embeddings** | `freelawproject/modernbert-embed-base_finetune_512` | 768-dim, fine-tuned on millions of US legal opinions (Free Law Project) |
| **Product Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, general-purpose (backward compatible) |
| **Text Generation / RAG** | `microsoft/Phi-3.5-mini-instruct` (Q4_K_M GGUF) | 3.8B params, quantized for fast CPU inference via llama-cpp-python |

## Running the API Tests

IMPORTANT! : for ease of evaluation the inference service and java search service have been deployed to aws. To run locally takes multiple setup steps: database, server you can skip Prerequisites and goto Running Tests below. Everything is setup in aws. Also after running inference tests you can test fine tuning by cd fine-tuning/ then README

The `test-inference-api.sh` script provides comprehensive integration tests for the Python Inference Service API. The `test-legal-api.sh` script tests the legal document search endpoints. To run see Running the Tests.

### Prerequisites

1. **Python inference service running** - Start the API server first:
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 8080
   ```

2. **Database with data** - Some tests require documents/ingested records in the database for search operations to return meaningful results.

3. **curl and Python 3** - Required for making HTTP requests and parsing JSON responses.

### Running the Tests

**With a custom base URL (AWS):**
```bash
./test-inference-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com
./test-legal-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com
```

**Basic usage (localhost:8080):**
```bash
./test-inference-api.sh
./test-legal-api.sh
```

### Deploying to AWS

To deploy the updated service with legal document search to AWS:
```bash
./deploy-legal.sh
```

This builds the Docker image, pushes to ECR, runs the DB migration, updates the ECS service, and ingests legal documents. Options:
- `--skip-db` - Skip DB migration if already done
- `--skip-ingest` - Skip legal document ingestion if already done

After deployment, ingest legal documents if not done during deploy:
```bash
curl -X POST http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/legal/ingest
```

### Test Coverage

The test suite includes 51 tests for product search plus 41 tests for legal search covering:

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

#### Legal Document Search Tests (`test-legal-api.sh`)

| Category | Tests |
|----------|-------|
| Health & Info | Health check with legal doc count |
| Document Count & Retrieval | `/legal/documents/count`, `/legal/documents/{doc_id}` |
| Semantic Search | Content, title, and headnotes field search |
| Hybrid Search | Semantic + keyword with RRF, citation search |
| Semantic vs Hybrid Comparison | Demonstrates why legal search needs hybrid |
| Jurisdiction Filtering | CA, NY, US Supreme Court, Federal circuits |
| Status Filtering (Shepard's) | Exclude overruled cases (e.g., Plessy v. Ferguson) |
| Document Type Filtering | Statutes, case law, practice guides, regulations |
| Practice Area Filtering | Employment, constitutional law, criminal |
| Combined Filters | Multiple filters applied simultaneously |
| Legal RAG | Citation-aware RAG with faithfulness checking |
| Error Handling | Invalid inputs |
| Performance | Semantic and hybrid search latency |

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
GET / shows version 5.0.0                               PASS

...

==============================================
Test Results
==============================================
Passed: 51
Failed: 0

All tests passed!
```