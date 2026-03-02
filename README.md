# LLM Inference API with Vector Search & Legal Document Search

## Models (v5.0.0)

| Component | Model | Details |
|-----------|-------|---------|
| **Legal Embeddings** | `freelawproject/modernbert-embed-base_finetune_512` | 768-dim, fine-tuned on millions of US legal opinions (Free Law Project) |
| **Product Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, general-purpose (backward compatible) |
| **Text Generation / RAG** | `microsoft/Phi-3.5-mini-instruct` (Q4_K_M GGUF) | 3.8B params, quantized for fast CPU inference via llama-cpp-python |

## Running the Services

### Local Development

Start all services locally (PostgreSQL, Python on port 8000, Java on port 8080) with a single command:

```bash
./local-dev.sh                # Start everything
./local-dev.sh --skip-java    # Python + DB only
./local-dev.sh --skip-python  # Java + DB only (Python already running)
./local-dev.sh --skip-build   # Skip Maven build (use existing JAR)
./local-dev.sh --dry-run      # Preview what would happen
```

Run the full test battery after startup:

```bash
./local-dev-test.sh                    # Start services + run all tests
./local-dev-test.sh --skip-startup     # Tests only (services already running)
./local-dev-test.sh --skip-rag-tests   # Skip claude-rag pytest suite
```

Stop services:

```bash
./local-dev-stop.sh    # Stops Python + Java (leaves PostgreSQL running)
```

**Prerequisites:** Docker (for PostgreSQL), Python 3.11+, Java 17+, Maven. The script auto-detects the `.venv` virtual environment and installs missing dependencies from `requirements.txt`.

**Architecture (local):**
```
localhost:8000  →  Python FastAPI  (embeddings, generation, search, legal)
localhost:8080  →  Java Spring Boot (search-engine, delegates to Python)
localhost:5433  →  PostgreSQL (claude-rag-pg container, database: llmdb)
```

### AWS

Start all AWS infrastructure (RDS + ECS services):

```bash
./aws-startup.sh               # Start RDS and scale ECS services
./aws-startup.sh --skip-rds    # Only manage ECS services
./aws-startup.sh --dry-run     # Preview what would happen
```

Shut down to minimize costs:

```bash
./aws-shutdown.sh              # Stop ECS services and RDS
./aws-shutdown.sh --skip-rds   # Only stop ECS services
./aws-shutdown.sh --dry-run    # Preview what would happen
```

## API Documentation (Swagger UI)

Interactive API documentation is auto-generated and available at:

- **Swagger UI**: [http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/docs](http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/docs)
- **ReDoc**: [http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/redoc](http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/redoc)
- **OpenAPI JSON**: [http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/openapi.json](http://llm-alb-1402483560.us-east-1.elb.amazonaws.com/openapi.json)

All 21 endpoints are grouped by domain (Legal Search, Legal RAG, Product Search, Text Generation, etc.) with descriptions, request examples, and "Try it out" support.

If running locally: `http://localhost:8080/docs`

## Running the API Tests

The `test-inference-api.sh` script provides comprehensive integration tests for the Python Inference Service API (51 tests). The `test-legal-api.sh` script tests the legal document search endpoints (41 tests).

### Running the Tests

**Local (after `./local-dev.sh`):**
```bash
./test-inference-api.sh http://localhost:8000
./test-legal-api.sh http://localhost:8000
```

**AWS:**
```bash
./test-inference-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com
./test-legal-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com
```

**Full battery (start + test + report):**
```bash
./local-dev-test.sh              # Local: start services, run all tests
./local-dev-test.sh -v           # Local: verbose mode
```

**Verbose mode (`-v` / `--verbose`):**

Both test scripts support a verbose flag that shows per-test curl commands, response latency and size, a performance summary, and an AWS cost estimate.

```bash
./test-inference-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com -v
./test-legal-api.sh http://llm-alb-1402483560.us-east-1.elb.amazonaws.com -v
./test-legal-api.sh --verbose http://llm-alb-1402483560.us-east-1.elb.amazonaws.com
```

The flag can appear before or after the base URL. Without `-v`, output remains the same compact format as before.

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

With `-v`, each test additionally shows the curl command, response latency, and response size. A performance summary and AWS cost estimate are appended at the end:

```
==============================================
Performance Summary
==============================================
  Total requests:     51
  Total data recv:    42.3 KB
  Test wall time:     38s
  Avg latency:        312ms
  Min latency:        18ms
  Max latency:        4521ms

==============================================
AWS Cost Estimate (for test duration only)
==============================================
  Duration:           38s (0.010556 hours)
  Data transferred:   42.3 KB (0.000000039 GB)

  ALB (us-east-1):    $0.0225/hr x 0.010556hr = $0.000238
  Compute (by instance type for test duration):
    t3.medium:        $0.0416/hr x 0.010556hr = $0.000439
    g4dn.xlarge:      $0.5260/hr x 0.010556hr = $0.005552

  Estimated total:    $0.0007 - $0.0058
```

## Fine-Tuning

### Product Fine-Tuning (`fine-tuning/`)

Demo pipeline for fine-tuning the product embedding model. See `fine-tuning/README.md` for details.

### Legal Fine-Tuning (`fine-tuning-legal/`)

Demo pipeline for fine-tuning the legal-domain ModernBERT embedding model. The pipeline includes:

1. **Extract** legal documents from `legal-documents.csv`
2. **Generate** training data (query-passage pairs with hard negatives)
3. **Baseline evaluation** of the pre-trained model
4. **Fine-tune** with contrastive learning (MultipleNegativesRankingLoss)
5. **Evaluate** improvement against baseline
6. **Re-embed** legal documents with the fine-tuned model
7. **Compare** search results before/after fine-tuning

```bash
cd fine-tuning-legal
pip install -r requirements.txt
python demo.py          # Run the full pipeline
python demo.py --steps 1,2,3   # Run specific steps
```

See `fine-tuning-legal/README.md` for full details and configuration.