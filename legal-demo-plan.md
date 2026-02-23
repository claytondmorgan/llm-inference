# Technical Plan: Convert Product Search Demo → Legal Document Search Demo

## Context
**Interview:** LexisNexis Data Scientist — AI Solutions for Legal Content, Mon Feb 23 at 3pm EST  
**Goal:** Modify the existing VectorSearchDemo (Java) + llm-inference (Python) to process legal documents instead of Amazon product data, then explain the differences to the interviewer.

**Repos:**
- `VectorSearchDemo` — Java Spring Boot REST API for semantic vector search (pgvector, HNSW, cosine similarity)
- `llm-inference` — Python FastAPI for embedding generation, text generation, document CRUD, search, RAG, and ingestion

---

## PHASE 1: Sample Legal Data

### 1.1 Create `legal-documents.csv` (replaces `amazon-products.csv`)

Create a CSV file with ~50-100 sample legal documents covering multiple document types. This demonstrates awareness of the LexisNexis content types.

**CSV Schema:**
```csv
doc_id,doc_type,title,citation,jurisdiction,date_decided,court,content,headnotes,practice_area,status
```

**Column descriptions:**
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `doc_id` | string | Unique identifier | `case-001` |
| `doc_type` | string | One of: `case_law`, `statute`, `regulation`, `practice_guide`, `headnote` | `case_law` |
| `title` | string | Case name or statute title | `Miranda v. Arizona` |
| `citation` | string | Legal citation in Bluebook format | `384 U.S. 436 (1966)` |
| `jurisdiction` | string | State or federal jurisdiction | `US_Supreme_Court`, `CA`, `NY`, `TX`, `Federal_9th_Circuit` |
| `date_decided` | string | Date of decision/enactment | `1966-06-13` |
| `court` | string | Issuing court or legislature | `Supreme Court of the United States` |
| `content` | string | Full text body (or representative excerpt) | The actual legal text |
| `headnotes` | string | Summary/headnote text | A brief summary of the holding |
| `practice_area` | string | Legal practice area | `constitutional_law`, `employment`, `criminal`, `tort`, `contract`, `ip` |
| `status` | string | Shepard's-style status | `good_law`, `distinguished`, `overruled`, `questioned` |

**Content to include (generate realistic but synthetic):**
1. **Landmark cases** (10-15): Miranda v. Arizona, Brown v. Board, Roe v. Wade, Mapp v. Ohio, Gideon v. Wainwright, Terry v. Ohio, etc. — write ~300-500 word summaries of the holdings and reasoning.
2. **Employment discrimination cases** (10-15): Synthetic California and federal cases about Title VII, ADA, FMLA, wrongful termination. Mix of good law and overruled/distinguished.
3. **Statutes** (10-15): Key sections of Title VII (42 U.S.C. § 2000e), ADA (42 U.S.C. § 12101), California FEHA (Gov. Code § 12940), FMLA (29 U.S.C. § 2601). Write short statutory text excerpts.
4. **Practice guides** (5-10): Synthetic "How to file an employment discrimination claim in California" type content, "Checklist for ADA reasonable accommodation requests", etc.
5. **Regulations** (5-10): EEOC guidelines, DOL regulations, California DFEH procedures.

**Why this mix matters for the demo:**
- Shows you understand LexisNexis handles multiple document types, not just cases
- The `status` field demonstrates awareness of Shepard's citation validation
- The `jurisdiction` field enables filtered search (a key legal requirement)
- The `practice_area` field enables domain-specific retrieval

### 1.2 Generate the CSV

Write a Python script `generate_legal_data.py` that creates the CSV. Use realistic but synthetic legal content. Do NOT copy real case text — write paraphrased summaries of well-known holdings.

```python
# generate_legal_data.py
# Generates legal-documents.csv with ~75 synthetic legal documents
# Run once to create the dataset, then ingest via the API
```

---

## PHASE 2: Database Schema Changes

### 2.1 New Table: `legal_documents` (replaces `ingested_records` for legal data)

```sql
CREATE TABLE IF NOT EXISTS legal_documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(50) UNIQUE NOT NULL,
    doc_type VARCHAR(50) NOT NULL,       -- case_law, statute, regulation, practice_guide, headnote
    title TEXT NOT NULL,
    citation VARCHAR(200),               -- Bluebook citation
    jurisdiction VARCHAR(100),           -- US_Supreme_Court, CA, NY, Federal_9th_Circuit, etc.
    date_decided DATE,
    court VARCHAR(200),
    content TEXT NOT NULL,                -- Full text body
    headnotes TEXT,                       -- Summary text
    practice_area VARCHAR(100),          -- constitutional_law, employment, criminal, etc.
    status VARCHAR(50) DEFAULT 'good_law', -- good_law, distinguished, overruled, questioned
    
    -- Embeddings (same 384-dim as current, same model)
    title_embedding vector(384),
    content_embedding vector(384),
    headnote_embedding vector(384),      -- NEW: separate embedding for headnotes
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Full-text search columns for BM25-style hybrid search
    title_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, ''))) STORED,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
);

-- HNSW indexes for vector search (same as current, but 3 columns now)
CREATE INDEX IF NOT EXISTS idx_legal_title_hnsw ON legal_documents 
    USING hnsw (title_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_legal_content_hnsw ON legal_documents 
    USING hnsw (content_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_legal_headnote_hnsw ON legal_documents 
    USING hnsw (headnote_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- GIN indexes for full-text search (NEW: enables hybrid search)
CREATE INDEX IF NOT EXISTS idx_legal_title_fts ON legal_documents USING gin(title_tsv);
CREATE INDEX IF NOT EXISTS idx_legal_content_fts ON legal_documents USING gin(content_tsv);

-- B-tree indexes for metadata filtering
CREATE INDEX IF NOT EXISTS idx_legal_jurisdiction ON legal_documents(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_legal_doc_type ON legal_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_legal_practice_area ON legal_documents(practice_area);
CREATE INDEX IF NOT EXISTS idx_legal_status ON legal_documents(status);
CREATE INDEX IF NOT EXISTS idx_legal_date ON legal_documents(date_decided);
```

**Key differences from current schema to explain in interview:**
1. **Triple embeddings** (title, content, headnote) vs dual (title, content) — legal docs have distinct searchable sections
2. **tsvector columns** — enables PostgreSQL full-text search for hybrid search (BM25-equivalent)
3. **Metadata indexes** — jurisdiction, doc_type, practice_area, status enable filtered search
4. **status field** — maps to Shepard's citation signals
5. **citation field** — exact citation matching is critical in legal (42 U.S.C. § 1983 must be exact)

### 2.2 Keep existing tables intact
Do NOT drop `ingested_records` or `documents` tables. The legal demo runs alongside the product demo. This lets you show both during the interview and explicitly compare them.

---

## PHASE 3: Python Service Changes (llm-inference/app.py)

### 3.1 New Pydantic Models

Add these models alongside the existing ones (don't replace):

```python
# ============================================================
# Legal Document Models
# ============================================================

class LegalDocument(BaseModel):
    doc_id: str
    doc_type: str  # case_law, statute, regulation, practice_guide, headnote
    title: str
    citation: Optional[str] = None
    jurisdiction: Optional[str] = None
    date_decided: Optional[str] = None
    court: Optional[str] = None
    content: str
    headnotes: Optional[str] = None
    practice_area: Optional[str] = None
    status: str = "good_law"

class LegalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    search_field: str = Field(default="content")  # content, title, headnotes, hybrid
    jurisdiction: Optional[str] = None  # Filter by jurisdiction
    doc_type: Optional[str] = None      # Filter by document type
    practice_area: Optional[str] = None # Filter by practice area
    status_filter: Optional[str] = None # Filter by Shepard's status (e.g., exclude overruled)
    date_from: Optional[str] = None     # Filter by date range
    date_to: Optional[str] = None

class LegalSearchResult(BaseModel):
    id: int
    doc_id: str
    doc_type: str
    title: str
    citation: Optional[str]
    jurisdiction: Optional[str]
    court: Optional[str]
    practice_area: Optional[str]
    status: Optional[str]
    content_snippet: str  # Truncated content for display
    similarity: float
    search_method: str  # "semantic", "keyword", or "hybrid"

class LegalRAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    jurisdiction: Optional[str] = None
    practice_area: Optional[str] = None
    exclude_overruled: bool = True  # By default, don't cite overruled cases

class LegalRAGResponse(BaseModel):
    query: str
    answer: str
    sources: List[LegalSearchResult]
    citations_used: List[str]  # List of legal citations referenced in the answer
    faithfulness_note: str     # Flag if any claim lacks source support
```

### 3.2 New Endpoints

Add these endpoints to `app.py`. Keep all existing endpoints working.

#### POST /legal/ingest
Ingest legal documents from the CSV. Similar to existing ingestion but targets `legal_documents` table and generates triple embeddings.

```python
@app.post("/legal/ingest")
async def ingest_legal_documents():
    """Ingest legal-documents.csv into the legal_documents table."""
    # 1. Read legal-documents.csv
    # 2. For each row:
    #    a. Generate title_embedding from title
    #    b. Generate content_embedding from content  
    #    c. Generate headnote_embedding from headnotes (if present, else from title)
    # 3. Batch insert into legal_documents table using executemany
    # 4. Return count of documents ingested
```

#### POST /legal/search
Legal-specific search with jurisdiction filtering and hybrid search option.

```python
@app.post("/legal/search", response_model=List[LegalSearchResult])
async def search_legal_documents(request: LegalSearchRequest):
    """Search legal documents with optional jurisdiction/type/area filters."""
    
    if request.search_field == "hybrid":
        # HYBRID SEARCH: combine semantic + keyword using RRF
        # 1. Run semantic search (vector cosine similarity)
        # 2. Run keyword search (PostgreSQL ts_rank with to_tsquery)
        # 3. Combine using Reciprocal Rank Fusion: RRF(d) = Σ 1/(k + rank_i(d)), k=60
        # 4. Return top-k by combined RRF score
        pass
    else:
        # SEMANTIC SEARCH: same as current but with metadata filters
        # 1. Generate query embedding
        # 2. Build SQL with optional WHERE clauses for jurisdiction, doc_type, etc.
        # 3. If status_filter is set, exclude overruled cases
        # 4. ORDER BY embedding <=> query_vector LIMIT top_k
        pass
```

**The hybrid search SQL pattern:**
```sql
-- Semantic search component
WITH semantic AS (
    SELECT id, doc_id, title, citation, jurisdiction, court, practice_area, 
           status, LEFT(content, 300) as content_snippet,
           1 - (content_embedding <=> %(query_vec)s::vector) AS similarity,
           ROW_NUMBER() OVER (ORDER BY content_embedding <=> %(query_vec)s::vector) AS sem_rank
    FROM legal_documents
    WHERE ($jurisdiction_filter)
      AND ($doc_type_filter)
      AND ($status_filter)
    LIMIT 20
),
-- Keyword search component  
keyword AS (
    SELECT id, doc_id, title, citation, jurisdiction, court, practice_area,
           status, LEFT(content, 300) as content_snippet,
           ts_rank(content_tsv, plainto_tsquery('english', %(query)s)) AS kw_score,
           ROW_NUMBER() OVER (ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %(query)s)) DESC) AS kw_rank
    FROM legal_documents
    WHERE content_tsv @@ plainto_tsquery('english', %(query)s)
      AND ($jurisdiction_filter)
      AND ($doc_type_filter)
      AND ($status_filter)
    LIMIT 20
)
-- Reciprocal Rank Fusion
SELECT COALESCE(s.id, k.id) as id,
       COALESCE(s.doc_id, k.doc_id) as doc_id,
       -- ... other fields ...
       COALESCE(1.0/(60 + s.sem_rank), 0) + COALESCE(1.0/(60 + k.kw_rank), 0) AS rrf_score,
       CASE 
           WHEN s.id IS NOT NULL AND k.id IS NOT NULL THEN 'hybrid'
           WHEN s.id IS NOT NULL THEN 'semantic'
           ELSE 'keyword'
       END as search_method
FROM semantic s
FULL OUTER JOIN keyword k ON s.id = k.id
ORDER BY rrf_score DESC
LIMIT %(top_k)s;
```

#### POST /legal/rag
Legal-specific RAG with citation-aware prompting.

```python
@app.post("/legal/rag", response_model=LegalRAGResponse)
async def legal_rag_query(request: LegalRAGRequest):
    """Legal RAG: retrieve authorities then generate cited answer."""
    
    # 1. Search for relevant legal documents (using hybrid by default)
    search_request = LegalSearchRequest(
        query=request.query,
        top_k=request.top_k,
        search_field="hybrid",
        jurisdiction=request.jurisdiction,
        practice_area=request.practice_area,
        status_filter="exclude_overruled" if request.exclude_overruled else None
    )
    results = await search_legal_documents(search_request)
    
    # 2. Assemble context with citation information
    context_parts = []
    for i, result in enumerate(results, 1):
        citation_str = f" ({result.citation})" if result.citation else ""
        status_str = f" [STATUS: {result.status}]" if result.status != "good_law" else ""
        context_parts.append(
            f"[{i}] {result.title}{citation_str}{status_str}\n"
            f"Type: {result.doc_type} | Jurisdiction: {result.jurisdiction}\n"
            f"{result.content_snippet}"
        )
    context = "\n\n".join(context_parts)
    
    # 3. Legal-specific prompt template
    prompt = f"""You are a legal content editor at a major legal publisher.

RULES:
1. ONLY use information from the provided source documents. Do not add facts from training data.
2. Every factual claim must include a citation in [brackets] referencing the source number.
3. If uncertain about any legal interpretation, prefix with [NEEDS REVIEW].
4. If sources are insufficient to answer the question, say "Insufficient sources" rather than guessing.
5. Note if any cited authority has been overruled or questioned.

SOURCES:
{context}

QUESTION: {request.query}

ANSWER (with citations):"""
    
    # 4. Generate with the LLM
    # 5. Extract citations used from the generated text
    # 6. Return with faithfulness note
```

#### GET /legal/documents/count
```python
@app.get("/legal/documents/count")
async def get_legal_document_count():
    """Get total count of legal documents by type."""
    # Return counts grouped by doc_type
```

#### GET /legal/documents/{doc_id}
```python
@app.get("/legal/documents/{doc_id}")
async def get_legal_document(doc_id: str):
    """Get a specific legal document by doc_id."""
```

### 3.3 Update the Ingestion Worker

In the ingestion worker logic, add a branch that detects legal CSV format:

```python
# In the ingestion/processing logic:
# Detect if the CSV has legal columns (doc_type, citation, jurisdiction)
# If so, route to legal_documents table with triple embeddings
# If not, route to ingested_records table (existing behavior)

def detect_data_type(df):
    """Detect if CSV contains legal data or product data."""
    legal_columns = {'doc_type', 'citation', 'jurisdiction', 'court'}
    if legal_columns.intersection(set(df.columns)):
        return 'legal'
    return 'product'
```

---

## PHASE 4: Java Service Changes (VectorSearchDemo)

### 4.1 New DTOs

Create new DTOs in the `dto` package. Keep existing product DTOs.

**`LegalSearchRequest.java`:**
```java
package com.llm.searchengine.dto;

public class LegalSearchRequest {
    private String query;                  // required
    private Integer topK;                  // default 10
    private String searchField;            // content, title, headnotes, hybrid
    private String jurisdiction;           // optional filter
    private String docType;                // optional filter
    private String practiceArea;           // optional filter
    private String statusFilter;           // optional: exclude_overruled
    private Double similarityThreshold;    // default 0.0
    // getters/setters
}
```

**`LegalSearchResult.java`:**
```java
package com.llm.searchengine.dto;

public class LegalSearchResult {
    private Integer id;
    private String docId;
    private String docType;
    private String title;
    private String citation;
    private String jurisdiction;
    private String court;
    private String practiceArea;
    private String status;
    private String contentSnippet;
    private Double similarity;
    private String searchMethod;
    // getters/setters
}
```

**`LegalSearchResponse.java`:**
```java
package com.llm.searchengine.dto;

import java.util.List;

public class LegalSearchResponse {
    private String query;
    private String searchField;
    private Integer totalResults;
    private List<LegalSearchResult> results;
    private Long latencyMs;
    private String searchMethod;  // semantic, keyword, or hybrid
    // getters/setters
}
```

### 4.2 New Repository

**`LegalSearchRepository.java`:**
```java
package com.llm.searchengine.repository;

// Same pattern as VectorSearchRepository but queries legal_documents table
// Key differences:
// 1. Queries legal_documents table instead of ingested_records
// 2. Supports jurisdiction/docType/practiceArea/status WHERE clause filtering
// 3. Adds searchByHeadnote() method (third embedding column)
// 4. Adds hybridSearch() method that combines semantic + keyword with RRF
// 5. getIndexedCount() queries legal_documents

@Repository
public class LegalSearchRepository {
    
    private final JdbcTemplate jdbcTemplate;
    
    // searchByContent(embedding, topK, threshold, jurisdiction, docType, practiceArea, statusFilter)
    // searchByTitle(embedding, topK, threshold, ...)
    // searchByHeadnote(embedding, topK, threshold, ...)
    // hybridSearch(embedding, queryText, topK, threshold, ...) — combines vector + FTS
    // getIndexedCount()
    // getCountByType() — returns map of doc_type → count
}
```

### 4.3 New Service

**`LegalSearchService.java`:**
```java
package com.llm.searchengine.service;

@Service
public class LegalSearchService {
    
    private final EmbeddingService embeddingService;  // Reuse existing
    private final LegalSearchRepository legalSearchRepository;
    
    public LegalSearchResponse search(LegalSearchRequest request) {
        // Same flow as SearchService but:
        // 1. Support "hybrid" search_field option
        // 2. Pass jurisdiction/docType/practiceArea/status filters to repository
        // 3. For hybrid: call hybridSearch() which does RRF internally
        // 4. Track searchMethod in response (semantic vs keyword vs hybrid)
    }
}
```

### 4.4 New Controller

**`LegalSearchController.java`:**
```java
package com.llm.searchengine.controller;

@RestController
@RequestMapping("/api/legal")
@Tag(name = "Legal Document Search", description = "Semantic and hybrid search for legal documents")
public class LegalSearchController {
    
    // POST /api/legal/search — Legal document search with filters
    // GET  /api/legal/health  — Health check for legal document index
    // GET  /api/legal/info    — Service info including legal document counts by type
    // GET  /api/legal/stats   — Document counts by jurisdiction, practice area, status
}
```

### 4.5 Swagger Examples

Update the Swagger examples to show legal queries instead of product queries:

```java
@ExampleObject(name = "Semantic legal search",
    value = """
    {
        "query": "employment discrimination reasonable accommodation",
        "top_k": 10,
        "search_field": "content"
    }"""),
@ExampleObject(name = "Hybrid search with jurisdiction filter",
    value = """
    {
        "query": "duty of care negligence standard",
        "top_k": 5,
        "search_field": "hybrid",
        "jurisdiction": "CA"
    }"""),
@ExampleObject(name = "Search excluding overruled cases",
    value = """
    {
        "query": "Miranda rights custodial interrogation",
        "top_k": 10,
        "search_field": "hybrid",
        "status_filter": "exclude_overruled"
    }"""),
@ExampleObject(name = "Citation-specific search",
    value = """
    {
        "query": "42 U.S.C. § 1983 civil rights",
        "top_k": 5,
        "search_field": "hybrid"
    }""")
```

---

## PHASE 5: Test Script Updates

### 5.1 Create `test-legal-api.sh`

New test script specifically for legal search endpoints. Pattern matches `test-search-api.sh` but uses legal queries.

**Test cases to include:**

```bash
# 1. Health & Info
GET /api/legal/health
GET /api/legal/info
GET /api/legal/stats

# 2. Semantic search — conceptual legal queries
POST /api/legal/search {"query": "employment discrimination reasonable accommodation", "top_k": 5}
POST /api/legal/search {"query": "duty of care negligence standard", "top_k": 5}
POST /api/legal/search {"query": "constitutional right to counsel", "top_k": 5}

# 3. Hybrid search — demonstrates keyword + semantic combination
POST /api/legal/search {"query": "42 U.S.C. § 1983", "search_field": "hybrid", "top_k": 5}
# Keyword catches exact "§ 1983", semantic catches conceptual "civil rights violation"

# 4. Jurisdiction filtering
POST /api/legal/search {"query": "wrongful termination", "jurisdiction": "CA", "top_k": 5}
POST /api/legal/search {"query": "wrongful termination", "jurisdiction": "NY", "top_k": 5}
# Same query, different jurisdiction — different results

# 5. Status filtering (Shepard's demo)
POST /api/legal/search {"query": "separate but equal", "status_filter": "exclude_overruled", "top_k": 5}
# Should NOT return Plessy v. Ferguson (overruled by Brown v. Board)

# 6. Document type filtering
POST /api/legal/search {"query": "disability accommodation", "doc_type": "statute", "top_k": 5}
POST /api/legal/search {"query": "disability accommodation", "doc_type": "case_law", "top_k": 5}

# 7. Legal RAG
POST /legal/rag {"query": "What are the requirements for a reasonable accommodation under the ADA?", "top_k": 5}
POST /legal/rag {"query": "Can an employer fire someone for filing a discrimination complaint?", "top_k": 5, "jurisdiction": "CA"}

# 8. Compare semantic vs hybrid
# Show that "§ 1983" gets ZERO results with pure semantic (embeddings don't understand citation symbols)
# but FINDS results with hybrid (keyword catches the exact text)
POST /api/legal/search {"query": "§ 1983", "search_field": "content", "top_k": 5}
POST /api/legal/search {"query": "§ 1983", "search_field": "hybrid", "top_k": 5}
```

---

## PHASE 6: Key Differences to Explain in the Interview

These are the technical differences between processing product data vs legal documents that you should be prepared to discuss:

### 6.1 Data Model Differences

| Aspect | Product Data | Legal Documents | Why It Matters |
|--------|-------------|-----------------|----------------|
| **Document length** | Short (title + 1-2 sentence description) | Long (cases can be 50+ pages) | Need chunking strategy for legal docs |
| **Searchable fields** | 2 (title, content) | 3+ (title, content, headnotes, citations) | More embedding columns, more HNSW indexes |
| **Metadata filtering** | Minimal (category, price) | Critical (jurisdiction, court, date, status, practice area) | Pre-filter or post-filter with HNSW affects result quality |
| **Exact match needs** | Low (semantic is sufficient for products) | High (legal citations like "42 U.S.C. § 1983" must be exact) | Hybrid search (semantic + keyword) is mandatory for legal |
| **Temporal relevance** | Products are current | Law changes over time; cases get overruled | Need status tracking and date filtering |
| **Authority hierarchy** | All products are equal | Supreme Court > Circuit > District; Statutes > Cases | Ranking must account for authority level, not just similarity |
| **Cross-references** | Minimal | Dense citation graph between cases/statutes | Citation graph search is a future enhancement |

### 6.2 Chunking Strategy (Not in current demo, but explain the need)

Current system: Each product is one row, one embedding. Works because products are short.

Legal documents need chunking:
- A Supreme Court opinion can be 50+ pages
- all-MiniLM-L6-v2 has a 512 token limit
- Solution: Split into overlapping chunks of ~400 tokens with 50-token overlap
- Each chunk gets its own embedding row, linked back to the parent document via `doc_id`
- At retrieval time, return the parent document, not just the matching chunk

**For this demo:** Use short document summaries (300-500 words) to avoid the chunking complexity while still demonstrating the concept. Explain that production systems need chunking.

### 6.3 Hybrid Search Justification

**Product search:** Pure semantic works well. "comfortable running shoes" → finds similar products by meaning.

**Legal search:** Must combine semantic + keyword because:
1. **Citation matching:** "42 U.S.C. § 1983" is a specific symbol string. Embeddings don't encode special characters well. BM25 catches it exactly.
2. **Legal terminology:** "res ipsa loquitur" needs exact matching. The embedding model may not have seen enough Latin legal terms.
3. **Conceptual search:** "What's the standard for employment discrimination?" needs semantic understanding — BM25 can't find "disparate impact" from this query.
4. **Best of both:** Hybrid with RRF gives you exact matches for citations AND conceptual matches for natural language queries.

### 6.4 RAG Prompt Differences

**Product RAG prompt:**
```
Based on the following product information: {context}
Question: {query}
Answer:
```

**Legal RAG prompt:**
```
You are a legal content editor at a major legal publisher.
RULES:
1. ONLY use information from the provided source documents.
2. Every factual claim must include a citation in [brackets].
3. If uncertain, prefix with [NEEDS REVIEW].
4. If sources insufficient, say "Insufficient sources" rather than guessing.
5. Note if any cited authority has been overruled or questioned.
```

**Why the difference:** Legal content requires grounding (no hallucination), citation formatting, uncertainty flagging, and awareness of case status. Product descriptions can be more creative. This maps directly to LexisNexis's "courtroom-grade AI" standard.

---

## PHASE 7: Files to Create/Modify (Summary for Claude Code)

### New files to CREATE:

| File | Language | Description |
|------|----------|-------------|
| `llm-inference/generate_legal_data.py` | Python | Generate `legal-documents.csv` with ~75 synthetic legal documents |
| `llm-inference/legal-documents.csv` | CSV | The generated legal dataset |
| `llm-inference/schema_legal.sql` | SQL | DDL for `legal_documents` table, indexes |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/dto/LegalSearchRequest.java` | Java | Request DTO |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/dto/LegalSearchResult.java` | Java | Result DTO |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/dto/LegalSearchResponse.java` | Java | Response DTO |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/repository/LegalSearchRepository.java` | Java | Repository with legal-specific queries |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/service/LegalSearchService.java` | Java | Service with legal search logic |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/controller/LegalSearchController.java` | Java | REST controller for /api/legal/* |
| `test-legal-api.sh` | Bash | Integration test script for legal endpoints |

### Existing files to MODIFY:

| File | Changes |
|------|---------|
| `llm-inference/app.py` | Add legal Pydantic models, `/legal/ingest`, `/legal/search`, `/legal/rag`, `/legal/documents/*` endpoints |
| `llm-inference/requirements.txt` | No changes needed (same dependencies) |
| `VectorSearchDemo/src/main/resources/application.properties` | Add legal search config properties |
| `VectorSearchDemo/src/main/java/com/llm/searchengine/config/` | Add legal search configuration if needed |
| `VectorSearchDemo/README.md` | Add legal search documentation |
| `llm-inference/README.md` | Add legal search documentation |

### Files to NOT modify:
- All existing product search endpoints (keep working)
- Existing DTOs, services, repositories (keep as-is)
- Existing test scripts (keep working)
- Dockerfile (no dependency changes needed)
- AWS deployment scripts (no infra changes)

---

## PHASE 8: Demo Script (What to Show in the Interview)

Suggested order for demonstrating the system:

1. **Show the architecture** — "Here's my system: Java Spring Boot for the search API, Python FastAPI for embeddings, RAG, and ingestion, both on AWS ECS behind an ALB, with pgvector on RDS."

2. **Show the original product search** — "Originally built for Amazon products. Here's a semantic search for 'comfortable shoes'." (Shows the existing capability)

3. **Show the legal adaptation** — "I adapted it for legal documents. Same architecture, different data model. Here's the legal document search."

4. **Demo semantic search** — `POST /api/legal/search {"query": "employment discrimination reasonable accommodation", "top_k": 5}`

5. **Demo hybrid search** — "Watch what happens when I search for a statute citation with pure semantic vs hybrid:"
   - Semantic: `§ 1983` → poor results
   - Hybrid: `§ 1983` → finds the right statute
   - "This is why legal search needs hybrid. Embeddings don't understand citation symbols."

6. **Demo jurisdiction filtering** — Same query, CA vs NY — different results.

7. **Demo status filtering** — Search for "separate but equal" excluding overruled → Plessy doesn't appear.

8. **Demo legal RAG** — "What are the requirements for ADA reasonable accommodation?" → Get a cited answer with source references.

9. **Explain what's next** — "The building blocks are here: semantic + hybrid search, filtered retrieval, cited RAG. What's missing is the Orchestrator agent that ties these into an agentic workflow, and the Reviewer agent that validates citations against Shepard's. That's exactly what this role builds."

---

## Implementation Priority

If time is limited, implement in this order:

1. **P0 (Must have):** `legal-documents.csv` + `schema_legal.sql` + Python `/legal/search` endpoint with metadata filtering
2. **P0 (Must have):** Python `/legal/rag` endpoint with legal prompt template
3. **P1 (Should have):** Hybrid search (semantic + keyword with RRF)
4. **P1 (Should have):** Java `LegalSearchController` + DTOs + Repository
5. **P2 (Nice to have):** Status filtering (Shepard's demo)
6. **P2 (Nice to have):** `test-legal-api.sh` script
7. **P3 (Stretch):** Headnote embedding (third vector column)
