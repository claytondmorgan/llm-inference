import os
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import SentenceTransformer
from llama_cpp import Llama
import torch
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
llm = None          # Phi-3.5 Mini GGUF for text generation
embedder = None     # all-MiniLM-L6-v2 for product embeddings (384-dim)
tokenizer = None    # tokenizer for product embedder
legal_embedder = None  # ModernBERT legal embedder (768-dim)


# ============================================================
# Pydantic Models
# ============================================================

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Input text prompt for generation")
    max_new_tokens: int = Field(default=100, ge=1, le=500, description="Maximum tokens to generate")
    temperature: float = Field(default=0.7, ge=0.1, le=2.0, description="Sampling temperature (lower = more focused)")

    model_config = {"json_schema_extra": {"examples": [{"prompt": "What is employment law?", "max_new_tokens": 100, "temperature": 0.7}]}}

class GenerateResponse(BaseModel):
    generated_text: str = Field(description="Generated text from Phi-3.5 Mini")
    model: str = Field(description="Model identifier used for generation")

class EmbedRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to generate an embedding for")

    model_config = {"json_schema_extra": {"examples": [{"text": "Wireless bluetooth headphones with noise cancellation"}]}}

class DocumentRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Document text to store and embed")
    metadata: dict = Field(default={}, description="Optional key-value metadata")

    model_config = {"json_schema_extra": {"examples": [{"content": "Wireless bluetooth headphones with noise cancellation", "metadata": {"category": "Electronics"}}]}}

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")

    model_config = {"json_schema_extra": {"examples": [{"query": "noise cancelling headphones", "top_k": 5}]}}

class SearchResult(BaseModel):
    id: int = Field(description="Document ID")
    content: str = Field(description="Document text content")
    metadata: dict = Field(description="Document metadata")
    similarity: float = Field(description="Cosine similarity score (0-1)")

class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language question to answer")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of source documents to retrieve")
    max_new_tokens: int = Field(default=200, ge=1, le=500, description="Maximum tokens to generate in the answer")

    model_config = {"json_schema_extra": {"examples": [{"query": "What products are good for working from home?", "top_k": 3, "max_new_tokens": 200}]}}

class IngestedSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results to return")
    category: Optional[str] = Field(default=None, description="Filter by product category")
    search_field: str = Field(default="content", description="Embedding field to search: 'content' or 'title'")

    model_config = {"json_schema_extra": {"examples": [{"query": "comfortable running shoes", "top_k": 5, "search_field": "content"}]}}

class IngestedSearchResult(BaseModel):
    id: int = Field(description="Record ID")
    title: Optional[str] = Field(description="Product title")
    description: Optional[str] = Field(description="Product description")
    category: Optional[str] = Field(description="Product category")
    tags: Optional[list] = Field(description="Product tags")
    raw_data: dict = Field(description="Full product record data")
    similarity: float = Field(description="Cosine similarity score (0-1)")

class RAGResponse(BaseModel):
    answer: str = Field(description="Generated answer from Phi-3.5 Mini based on retrieved sources")
    sources: List[IngestedSearchResult] = Field(description="Source product records used to generate the answer")


# ============================================================
# Legal Document Models
# ============================================================

class LegalDocument(BaseModel):
    doc_id: str = Field(description="Unique document identifier (e.g., 'case-001')")
    doc_type: str = Field(description="Document type: case_law, statute, regulation, practice_guide, headnote")
    title: str = Field(description="Document title or case name")
    citation: Optional[str] = Field(default=None, description="Legal citation (e.g., '384 U.S. 436 (1966)')")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction (e.g., 'CA', 'US_Supreme_Court')")
    date_decided: Optional[str] = Field(default=None, description="Date decided (YYYY-MM-DD)")
    court: Optional[str] = Field(default=None, description="Court name")
    content: str = Field(description="Full document text content")
    headnotes: Optional[str] = Field(default=None, description="Document headnotes or key points")
    practice_area: Optional[str] = Field(default=None, description="Practice area: employment, constitutional_law, criminal")
    status: str = Field(default="good_law", description="Shepard's-style status: good_law, questioned, overruled")

class LegalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language legal research query")
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")
    search_field: str = Field(default="content", description="Search mode: 'content', 'title', 'headnotes', or 'hybrid' (RRF)")
    jurisdiction: Optional[str] = Field(default=None, description="Filter by jurisdiction (e.g., 'CA', 'NY', 'US_Supreme_Court', 'Federal_9th_Circuit')")
    doc_type: Optional[str] = Field(default=None, description="Filter by type: 'case_law', 'statute', 'regulation', 'practice_guide'")
    practice_area: Optional[str] = Field(default=None, description="Filter by area: 'employment', 'constitutional_law', 'criminal'")
    status_filter: Optional[str] = Field(default=None, description="Set to 'exclude_overruled' to filter out overruled cases (Shepard's-style)")
    date_from: Optional[str] = Field(default=None, description="Filter: earliest date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(default=None, description="Filter: latest date (YYYY-MM-DD)")

    model_config = {"json_schema_extra": {"examples": [
        {"query": "employment discrimination reasonable accommodation", "top_k": 5, "search_field": "hybrid", "status_filter": "exclude_overruled"},
    ]}}

class LegalSearchResult(BaseModel):
    id: int = Field(description="Database row ID")
    doc_id: str = Field(description="Document identifier")
    doc_type: str = Field(description="Document type")
    title: str = Field(description="Document title or case name")
    citation: Optional[str] = Field(description="Legal citation")
    jurisdiction: Optional[str] = Field(description="Jurisdiction")
    court: Optional[str] = Field(description="Court name")
    practice_area: Optional[str] = Field(description="Practice area")
    status: Optional[str] = Field(description="Shepard's-style status")
    content_snippet: str = Field(description="First 500 characters of document content")
    similarity: float = Field(description="Relevance score (cosine similarity for semantic, RRF for hybrid)")
    search_method: str = Field(description="Search method used: 'semantic', 'keyword', or 'hybrid'")

class LegalRAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Legal research question to answer with citations")
    top_k: int = Field(default=3, ge=1, le=20, description="Number of source authorities to retrieve")
    jurisdiction: Optional[str] = Field(default=None, description="Filter sources by jurisdiction")
    practice_area: Optional[str] = Field(default=None, description="Filter sources by practice area")
    exclude_overruled: bool = Field(default=True, description="Exclude overruled authorities (Shepard's-style filtering)")

    model_config = {"json_schema_extra": {"examples": [
        {"query": "What are the requirements for filing a wrongful termination claim?", "top_k": 3, "jurisdiction": "CA"},
    ]}}

class LegalRAGResponse(BaseModel):
    query: str = Field(description="Original research query")
    answer: str = Field(description="Generated answer with bracketed source citations (e.g., [1], [2])")
    sources: List[LegalSearchResult] = Field(description="Source authorities used to generate the answer")
    citations_used: List[str] = Field(description="List of legal citations referenced in the answer")
    faithfulness_note: str = Field(description="Assessment of source grounding (e.g., 'Answer references 3 source(s) out of 3 retrieved.')")


# ============================================================
# Helper Functions
# ============================================================

def get_db_credentials():
    """Get database credentials from env vars (local dev) or Secrets Manager (AWS)."""
    if os.getenv('DB_HOST'):
        return {
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'llmdb'),
            'username': os.getenv('DB_USERNAME', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
        }

    secret_name = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
    region = os.getenv('AWS_REGION', 'us-east-1')

    try:
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to get DB credentials: {e}")
        raise


def get_db_connection():
    """Create a database connection."""
    creds = get_db_credentials()
    return psycopg2.connect(
        host=creds['host'],
        database=creds['database'],
        user=creds['username'],
        password=creds['password'],
        port=creds['port']
    )


def mean_pooling(model_output, attention_mask):
    """Mean pooling for sentence embeddings."""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)


def get_embedding(text: str) -> List[float]:
    """Generate embedding for text."""
    global embedder, tokenizer

    encoded = tokenizer(text, padding=True, truncation=True, max_length=512, return_tensors='pt')

    with torch.no_grad():
        model_output = embedder(**encoded)

    embedding = mean_pooling(model_output, encoded['attention_mask'])
    embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)

    return embedding[0].tolist()


def get_legal_embedding(text: str) -> List[float]:
    """Generate 768-dim embedding for legal text using ModernBERT legal model."""
    global legal_embedder
    embedding = legal_embedder.encode(text, normalize_embeddings=True)
    return embedding.tolist()


# ============================================================
# App Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    global llm, embedder, tokenizer, legal_embedder

    # Load text generation model (Phi-3.5 Mini GGUF for fast CPU inference)
    gen_repo = os.getenv("GEN_MODEL_REPO", "bartowski/Phi-3.5-mini-instruct-GGUF")
    gen_filename = os.getenv("GEN_MODEL_FILE", "Phi-3.5-mini-instruct-Q4_K_M.gguf")
    logger.info(f"Loading generation model: {gen_repo}/{gen_filename}")

    llm = Llama.from_pretrained(
        repo_id=gen_repo,
        filename=gen_filename,
        n_ctx=4096,
        n_threads=int(os.getenv("LLM_THREADS", "4")),
        verbose=False
    )

    logger.info("Generation model loaded (Phi-3.5 Mini GGUF)")

    # Load product embedding model (384-dim, for backward compatibility)
    embed_model_id = os.getenv("EMBED_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
    logger.info(f"Loading product embedding model: {embed_model_id}")

    tokenizer = AutoTokenizer.from_pretrained(embed_model_id)
    embedder = AutoModel.from_pretrained(embed_model_id)
    embedder.eval()

    logger.info("Product embedding model loaded (384-dim)")

    # Load legal embedding model (768-dim, fine-tuned on legal opinions)
    legal_model_id = os.getenv("LEGAL_EMBED_MODEL_ID", "freelawproject/modernbert-embed-base_finetune_512")
    logger.info(f"Loading legal embedding model: {legal_model_id}")

    legal_embedder = SentenceTransformer(legal_model_id)

    logger.info("Legal embedding model loaded (768-dim)")

    # Test database connection
    try:
        conn = get_db_connection()
        conn.close()
        logger.info("Database connection verified")
    except Exception as e:
        logger.warning(f"Database not available: {e}")

    yield

    logger.info("Shutting down...")


# ============================================================
# FastAPI App
# ============================================================

tags_metadata = [
    {"name": "Health & Info", "description": "Service health checks and API metadata"},
    {"name": "Text Generation", "description": "Generate text using Phi-3.5 Mini (3.8B params, GGUF Q4_K_M quantized, CPU inference via llama-cpp-python)"},
    {"name": "Embeddings", "description": "Generate 384-dimensional product embeddings using all-MiniLM-L6-v2"},
    {"name": "Document Management", "description": "CRUD operations for the documents vector store"},
    {"name": "Product Search", "description": "Semantic vector search over ingested product records (1,013 Amazon products, dual 384-dim embeddings for title and content)"},
    {"name": "Product RAG", "description": "Retrieval-Augmented Generation over the product catalog using Phi-3.5 Mini"},
    {"name": "Legal Search", "description": "Semantic, keyword, and hybrid search over 58 legal documents using 768-dim ModernBERT embeddings with HNSW and GIN indexes"},
    {"name": "Legal RAG", "description": "Legal Retrieval-Augmented Generation with source citation tracking, faithfulness verification, and Shepard's-style status filtering"},
    {"name": "Legal Documents", "description": "Legal document ingestion, retrieval, and count endpoints"},
    {"name": "Ingestion", "description": "Ingestion job tracking and statistics for the product data pipeline"},
    {"name": "Debug", "description": "Debug and diagnostic endpoints for troubleshooting"},
]

app = FastAPI(
    title="LLM Inference API with Vector Search & Legal Document Search",
    description="""## Three-Model Architecture

| Model | Purpose | Dimensions |
|---|---|---|
| **Phi-3.5 Mini** (GGUF Q4_K_M) | Text generation and RAG | 3.8B params, CPU-only |
| **all-MiniLM-L6-v2** | Product embeddings | 384-dim |
| **ModernBERT Legal** (freelawproject) | Legal document embeddings | 768-dim |

## Key Features
- **Semantic search** with pgvector HNSW indexes and cosine similarity
- **Hybrid search** combining semantic + full-text search via Reciprocal Rank Fusion (RRF)
- **RAG pipelines** for both products and legal documents with source citations
- **Legal document search** with jurisdiction, document type, practice area, and Shepard's-style status filtering
- **58 legal documents** across employment, constitutional, and criminal law
- **1,013 product records** from Amazon product catalog with dual embeddings

## Infrastructure
- **Compute**: AWS ECS Fargate (16 vCPU / 32 GB)
- **Database**: PostgreSQL with pgvector extension
- **Indexes**: HNSW (m=16, ef_construction=64) for vector search, GIN for full-text search
""",
    version="5.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata
)


# ============================================================
# Core Endpoints
# ============================================================

@app.get("/health", tags=["Health & Info"], summary="Health check",
    description="Returns service health status including model loading state, database connectivity, and legal document count.",
    response_description="Health status object")
async def health_check():
    """Health check endpoint."""
    db_status = "unknown"
    legal_docs_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        db_status = "connected"
        try:
            cur.execute("SELECT COUNT(*) FROM legal_documents")
            legal_docs_count = cur.fetchone()[0]
        except:
            pass
        cur.close()
        conn.close()
    except:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "generator_loaded": llm is not None,
        "generator_model": "Phi-3.5-mini-instruct-Q4_K_M",
        "embedder_loaded": embedder is not None,
        "legal_embedder_loaded": legal_embedder is not None,
        "legal_embed_model": "freelawproject/modernbert-embed-base_finetune_512",
        "database": db_status,
        "legal_documents_indexed": legal_docs_count
    }


@app.get("/", tags=["Health & Info"], summary="Service info",
    description="Returns service name, version, and a directory of all available API endpoints.",
    response_description="Service metadata and endpoint directory")
async def root():
    """Root endpoint."""
    return {
        "service": "LLM Inference API with Vector Search & Legal Document Search",
        "version": "5.0.0",
        "endpoints": {
            "generate": "POST /generate",
            "embed": "POST /embed",
            "add_document": "POST /documents",
            "add_documents_batch": "POST /documents/batch",
            "search_documents": "POST /search",
            "search_ingested": "POST /search/records",
            "rag": "POST /rag",
            "ingestion_jobs": "GET /ingestion/jobs",
            "ingestion_stats": "GET /ingestion/stats",
            "ingestion_count": "GET /ingestion/records/count",
            "health": "GET /health",
            "legal_ingest": "POST /legal/ingest",
            "legal_search": "POST /legal/search",
            "legal_rag": "POST /legal/rag",
            "legal_document_count": "GET /legal/documents/count",
            "legal_document_get": "GET /legal/documents/{doc_id}"
        }
    }


# ============================================================
# Embedding Generation (for Java service delegation)
# ============================================================

@app.post("/embed", tags=["Embeddings"], summary="Generate product embedding",
    description="""Generate a 384-dimensional embedding vector for the given text using all-MiniLM-L6-v2.

Used by the Java search service to delegate embedding generation to Python, ensuring a single source of truth for the embedding model.

**Note**: This produces product embeddings (384-dim). Legal endpoints use ModernBERT (768-dim) internally.""",
    response_description="Embedding vector with dimensions and model info")
async def generate_embedding(request: EmbedRequest):
    """Generate embedding vector for text."""
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    text = request.text.strip()

    try:
        embedding = get_embedding(text)

        return {
            "embedding": embedding,
            "dimensions": len(embedding),
            "model": os.getenv("EMBED_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2"),
            "note": "Product embedding model (384-dim). Legal endpoints use ModernBERT (768-dim)."
        }
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Text Generation
# ============================================================

@app.post("/generate", response_model=GenerateResponse, tags=["Text Generation"],
    summary="Generate text from prompt",
    description="""Generate text using Phi-3.5 Mini (3.8B params, GGUF Q4_K_M quantized).

Uses chat completion format with the prompt as user message. Runs on CPU via llama-cpp-python with 16 threads.""",
    response_description="Generated text and model identifier")
async def generate_text(request: GenerateRequest):
    """Generate text from prompt."""
    if llm is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        output = llm.create_chat_completion(
            messages=[
                {"role": "user", "content": request.prompt}
            ],
            max_tokens=request.max_new_tokens,
            temperature=request.temperature,
        )

        generated_text = output["choices"][0]["message"]["content"]

        return GenerateResponse(
            generated_text=generated_text,
            model="Phi-3.5-mini-instruct-Q4_K_M"
        )
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Document Management (original documents table)
# ============================================================

@app.post("/documents", tags=["Document Management"], summary="Add a document",
    description="Add a single document to the vector store. The text is automatically embedded using all-MiniLM-L6-v2 (384-dim).",
    response_description="Created document ID")
async def add_document(request: DocumentRequest):
    """Add a document with its embedding to the database."""
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    try:
        embedding = get_embedding(request.content)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO documents (content, metadata, embedding)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (request.content, json.dumps(request.metadata), embedding)
        )

        doc_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return {"id": doc_id, "message": "Document added successfully"}

    except Exception as e:
        logger.error(f"Error adding document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents/batch", tags=["Document Management"], summary="Add documents in batch",
    description="Add multiple documents at once. Each document is embedded individually.",
    response_description="List of created document IDs")
async def add_documents_batch(documents: List[DocumentRequest]):
    """Add multiple documents at once."""
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        doc_ids = []
        for doc in documents:
            embedding = get_embedding(doc.content)
            cur.execute(
                """
                INSERT INTO documents (content, metadata, embedding)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (doc.content, json.dumps(doc.metadata), embedding)
            )
            doc_ids.append(cur.fetchone()[0])

        conn.commit()
        cur.close()
        conn.close()

        return {"ids": doc_ids, "message": f"{len(doc_ids)} documents added successfully"}

    except Exception as e:
        logger.error(f"Error adding documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/count", tags=["Document Management"], summary="Get document count",
    description="Returns the total number of documents in the vector store.",
    response_description="Document count")
async def get_document_count():
    """Get the total number of documents."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents/{doc_id}", tags=["Document Management"], summary="Delete a document",
    description="Delete a document by its ID. Returns 404 if document does not exist.",
    response_description="Deletion confirmation")
async def delete_document(doc_id: int):
    """Delete a document by ID."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM documents WHERE id = %s RETURNING id", (doc_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if deleted is None:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"message": f"Document {doc_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Document Search (original documents table)
# ============================================================

@app.post("/search", response_model=List[SearchResult], tags=["Product Search"],
    summary="Search documents (legacy table)",
    description="Semantic vector search over the original documents table using cosine similarity on 384-dim embeddings.",
    response_description="Ranked list of matching documents with similarity scores")
async def search_documents(request: SearchRequest):
    """Search for similar documents."""
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    try:
        query_embedding = get_embedding(request.query)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT
                id,
                content,
                metadata,
                1 - (embedding <=> %s::vector) as similarity
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, query_embedding, request.top_k)
        )

        results = cur.fetchall()
        cur.close()
        conn.close()

        return [
            SearchResult(
                id=r['id'],
                content=r['content'],
                metadata=r['metadata'] or {},
                similarity=float(r['similarity'])
            )
            for r in results
        ]

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# RAG (Retrieval-Augmented Generation)
# ============================================================

@app.post("/rag", response_model=RAGResponse, tags=["Product RAG"],
    summary="Product RAG query",
    description="""Retrieval-Augmented Generation over the product catalog.

1. Embeds the query using all-MiniLM-L6-v2 (384-dim)
2. Retrieves the top-k most similar products from ingested_records
3. Generates an answer using Phi-3.5 Mini with the retrieved products as context""",
    response_description="Generated answer with source product records")
async def rag_query(request: RAGRequest):
    """RAG: Retrieve from ingested products and generate answer."""
    if llm is None or embedder is None:
        raise HTTPException(status_code=503, detail="Models not loaded")

    try:
        # Step 1: Retrieve from ingested_records (not documents)
        query_embedding = get_embedding(request.query)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, title, description, category, tags, raw_data,
                   1 - (content_embedding <=> %s::vector) as similarity
            FROM ingested_records
            WHERE status = 'active'
              AND content_embedding IS NOT NULL
            ORDER BY content_embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, query_embedding, request.top_k)
        )

        results = cur.fetchall()
        cur.close()
        conn.close()

        search_results = [
            IngestedSearchResult(
                id=r['id'],
                title=r['title'],
                description=r['description'],
                category=r['category'],
                tags=r['tags'],
                raw_data=r['raw_data'] or {},
                similarity=float(r['similarity'])
            )
            for r in results
        ]

        # Step 2: Build context from product titles + descriptions
        context_parts = []
        for i, result in enumerate(search_results, 1):
            title = result.title or "Untitled"
            desc = result.description or ""
            context_parts.append(f"[{i}] {title}: {desc}")

        context = "\n\n".join(context_parts)

        # Step 3: Generate answer using Phi-3.5 Mini
        output = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful product search assistant. Answer questions based only on the provided product information. Be concise."},
                {"role": "user", "content": f"Products:\n{context}\n\nQuestion: {request.query}"}
            ],
            max_tokens=request.max_new_tokens,
            temperature=0.7,
        )

        answer = output["choices"][0]["message"]["content"]

        return RAGResponse(
            answer=answer,
            sources=search_results
        )

    except Exception as e:
        logger.error(f"RAG error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Ingested Records Search
# ============================================================

@app.post("/search/records", response_model=List[IngestedSearchResult], tags=["Product Search"],
    summary="Search product records",
    description="""Semantic vector search over 1,013 ingested Amazon product records.

Supports searching by `content` (description embedding) or `title` (title embedding), both 384-dim. Optional category filter for faceted search.""",
    response_description="Ranked list of matching products with similarity scores")
async def search_ingested_records(request: IngestedSearchRequest):
    """Search ingested records by vector similarity."""
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    try:
        query_embedding = get_embedding(request.query)

        embedding_field = "title_embedding" if request.search_field == "title" else "content_embedding"

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.category:
            cur.execute(
                f"""
                SELECT id, title, description, category, tags, raw_data,
                       1 - ({embedding_field} <=> %s::vector) as similarity
                FROM ingested_records
                WHERE status = 'active'
                  AND category = %s
                  AND {embedding_field} IS NOT NULL
                ORDER BY {embedding_field} <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, request.category, query_embedding, request.top_k)
            )
        else:
            cur.execute(
                f"""
                SELECT id, title, description, category, tags, raw_data,
                       1 - ({embedding_field} <=> %s::vector) as similarity
                FROM ingested_records
                WHERE status = 'active'
                  AND {embedding_field} IS NOT NULL
                ORDER BY {embedding_field} <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, request.top_k)
            )

        results = cur.fetchall()
        cur.close()
        conn.close()

        return [
            IngestedSearchResult(
                id=r['id'],
                title=r['title'],
                description=r['description'],
                category=r['category'],
                tags=r['tags'],
                raw_data=r['raw_data'] or {},
                similarity=float(r['similarity'])
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"Ingested search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Ingestion Management
# ============================================================

@app.get("/ingestion/jobs", tags=["Ingestion"], summary="List ingestion jobs",
    description="List recent product data ingestion jobs with status, row counts, and timestamps.",
    response_description="List of ingestion job records")
async def list_ingestion_jobs(limit: int = 20):
    """List recent ingestion jobs."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT job_id, source_file, status, total_rows, processed_rows,
                   failed_rows, started_at, completed_at, created_at
            FROM ingestion_jobs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,)
        )

        jobs = cur.fetchall()
        cur.close()
        conn.close()

        return [dict(j) for j in jobs]
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ingestion/stats", tags=["Ingestion"], summary="Get ingestion statistics",
    description="Returns aggregate statistics: total records, files, categories, and ingestion date range.",
    response_description="Ingestion statistics summary")
async def get_ingestion_stats():
    """Get overall ingestion statistics."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT source_file) as total_files,
                COUNT(DISTINCT category) as total_categories,
                MIN(ingested_at) as earliest_ingestion,
                MAX(ingested_at) as latest_ingestion
            FROM ingested_records
            WHERE status = 'active'
            """
        )

        stats = cur.fetchone()
        cur.close()
        conn.close()

        return dict(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ingestion/records/count", tags=["Ingestion"], summary="Get ingested record count",
    description="Returns the total number of active ingested product records.",
    response_description="Record count")
async def get_ingested_record_count():
    """Get count of ingested records."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ingested_records WHERE status = 'active'")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Debug Endpoints
# ============================================================

@app.get("/debug/documents", tags=["Debug"], summary="Debug document embeddings",
    description="Check document count, embedding dimensions, and sample content for troubleshooting.",
    response_description="Debug information about stored documents")
async def debug_documents():
    """Debug: Check document embeddings."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                LEFT(content, 50) as content_preview,
                embedding IS NOT NULL as has_embedding,
                CASE WHEN embedding IS NOT NULL
                     THEN vector_dims(embedding)
                     ELSE NULL
                END as embedding_dims
            FROM documents
            ORDER BY id DESC
            LIMIT 10
        """)

        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur.fetchall()]

        cur.close()
        conn.close()

        return {"documents": results}
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug/search-test", tags=["Debug"], summary="Test vector search",
    description="Run a test vector search with a hardcoded query to verify the search pipeline is working end-to-end.",
    response_description="Test search results with similarity scores")
async def debug_search_test():
    """Debug: Test vector search directly."""
    try:
        test_query = "pets and animals"
        query_embedding = get_embedding(test_query)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                LEFT(content, 50) as content_preview,
                (embedding <=> %s::vector) as cosine_distance
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT 5
            """,
            (query_embedding, query_embedding)
        )

        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur.fetchall()]

        cur.execute("SELECT vector_dims(embedding) FROM documents LIMIT 1")
        db_dims = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "query": test_query,
            "query_embedding_length": len(query_embedding),
            "db_embedding_dims": db_dims,
            "results": results
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


# ============================================================
# Legal Document Endpoints
# ============================================================

@app.post("/legal/ingest", tags=["Legal Documents"], summary="Ingest legal documents",
    description="""Ingest legal-documents.csv into the legal_documents table.

Drops and recreates the table, then processes all 58 documents:
- Generates **triple embeddings** (content, title, headnote) using ModernBERT (768-dim)
- Creates HNSW indexes (m=16, ef_construction=64) for each embedding column
- Creates GIN index on tsvector column for full-text search
- Processes documents in batches of 10""",
    response_description="Ingestion summary with document count")
async def ingest_legal_documents():
    """Ingest legal-documents.csv into the legal_documents table."""
    if legal_embedder is None:
        raise HTTPException(status_code=503, detail="Legal embedding model not loaded")

    try:
        import csv

        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal-documents.csv")
        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="legal-documents.csv not found. Run generate_legal_data.py first.")

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        conn = get_db_connection()
        cur = conn.cursor()

        # Drop and recreate table to ensure correct 768-dim columns
        cur.execute("DROP TABLE IF EXISTS legal_documents CASCADE;")
        cur.execute("""
            CREATE TABLE legal_documents (
                id SERIAL PRIMARY KEY,
                doc_id VARCHAR(50) UNIQUE NOT NULL,
                doc_type VARCHAR(50) NOT NULL,
                title TEXT NOT NULL,
                citation VARCHAR(200),
                jurisdiction VARCHAR(100),
                date_decided DATE,
                court VARCHAR(200),
                content TEXT NOT NULL,
                headnotes TEXT,
                practice_area VARCHAR(100),
                status VARCHAR(50) DEFAULT 'good_law',
                title_embedding vector(768),
                content_embedding vector(768),
                headnote_embedding vector(768),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                title_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, ''))) STORED,
                content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
            );
        """)
        conn.commit()

        ingested = 0
        skipped = 0

        for row in rows:
            # Generate embeddings using legal-domain ModernBERT model (768-dim)
            title_emb = get_legal_embedding(row["title"])
            content_emb = get_legal_embedding(row["content"])
            headnote_text = row.get("headnotes") or row["title"]
            headnote_emb = get_legal_embedding(headnote_text)

            # Parse date
            date_val = row.get("date_decided") or None
            if date_val == "":
                date_val = None

            cur.execute(
                """
                INSERT INTO legal_documents
                    (doc_id, doc_type, title, citation, jurisdiction, date_decided,
                     court, content, headnotes, practice_area, status,
                     title_embedding, content_embedding, headnote_embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["doc_id"], row["doc_type"], row["title"], row.get("citation"),
                    row.get("jurisdiction"), date_val, row.get("court"),
                    row["content"], row.get("headnotes"), row.get("practice_area"),
                    row.get("status", "good_law"),
                    title_emb, content_emb, headnote_emb
                )
            )
            ingested += 1

            if ingested % 10 == 0:
                conn.commit()
                logger.info(f"Ingested {ingested} legal documents...")

        conn.commit()

        # Create indexes if they don't exist
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_legal_title_hnsw ON legal_documents USING hnsw (title_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
            "CREATE INDEX IF NOT EXISTS idx_legal_content_hnsw ON legal_documents USING hnsw (content_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
            "CREATE INDEX IF NOT EXISTS idx_legal_headnote_hnsw ON legal_documents USING hnsw (headnote_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
            "CREATE INDEX IF NOT EXISTS idx_legal_title_fts ON legal_documents USING gin(title_tsv)",
            "CREATE INDEX IF NOT EXISTS idx_legal_content_fts ON legal_documents USING gin(content_tsv)",
            "CREATE INDEX IF NOT EXISTS idx_legal_jurisdiction ON legal_documents(jurisdiction)",
            "CREATE INDEX IF NOT EXISTS idx_legal_doc_type ON legal_documents(doc_type)",
            "CREATE INDEX IF NOT EXISTS idx_legal_practice_area ON legal_documents(practice_area)",
            "CREATE INDEX IF NOT EXISTS idx_legal_status ON legal_documents(status)",
            "CREATE INDEX IF NOT EXISTS idx_legal_date ON legal_documents(date_decided)",
        ]
        for stmt in index_statements:
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception as idx_err:
                logger.warning(f"Index creation warning: {idx_err}")
                conn.rollback()

        cur.close()
        conn.close()

        return {
            "message": f"Ingested {ingested} legal documents, skipped {skipped} (already exist)",
            "total_in_csv": len(rows),
            "ingested": ingested,
            "skipped": skipped
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legal ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_legal_filters(request):
    """Build SQL WHERE clauses and params for legal search filters."""
    conditions = []
    params = {}

    if request.jurisdiction:
        conditions.append("jurisdiction = %(jurisdiction)s")
        params["jurisdiction"] = request.jurisdiction
    if request.doc_type:
        conditions.append("doc_type = %(doc_type)s")
        params["doc_type"] = request.doc_type
    if request.practice_area:
        conditions.append("practice_area = %(practice_area)s")
        params["practice_area"] = request.practice_area
    if request.status_filter == "exclude_overruled":
        conditions.append("status != 'overruled'")
    if hasattr(request, 'date_from') and request.date_from:
        conditions.append("date_decided >= %(date_from)s")
        params["date_from"] = request.date_from
    if hasattr(request, 'date_to') and request.date_to:
        conditions.append("date_decided <= %(date_to)s")
        params["date_to"] = request.date_to

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    return where_clause, params


@app.post("/legal/search", response_model=List[LegalSearchResult], tags=["Legal Search"],
    summary="Search legal documents",
    description="""Search 58 legal documents using semantic, keyword, or hybrid search.

**Search modes** (via `search_field`):
- `content` — Cosine similarity on 768-dim content embeddings (HNSW index)
- `title` — Cosine similarity on 768-dim title embeddings
- `headnotes` — Cosine similarity on 768-dim headnote embeddings
- `hybrid` — **Reciprocal Rank Fusion** combining semantic (content) + full-text keyword search (GIN index)

**Filters**:
- `jurisdiction` — e.g., CA, NY, US_Supreme_Court, Federal_9th_Circuit
- `doc_type` — case_law, statute, regulation, practice_guide
- `practice_area` — employment, constitutional_law, criminal
- `status_filter` — Set to `exclude_overruled` for Shepard's-style filtering
- `date_from` / `date_to` — Date range filtering""",
    response_description="Ranked list of matching legal documents with similarity scores and search method")
async def search_legal_documents(request: LegalSearchRequest):
    """Search legal documents with semantic, keyword, or hybrid search and metadata filters."""
    if legal_embedder is None:
        raise HTTPException(status_code=503, detail="Legal embedding model not loaded")

    try:
        filter_clause, filter_params = _build_legal_filters(request)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.search_field == "hybrid":
            # HYBRID SEARCH: semantic + keyword with Reciprocal Rank Fusion
            query_embedding = get_legal_embedding(request.query)
            filter_params["query_vec"] = query_embedding
            filter_params["query_text"] = request.query
            filter_params["top_k"] = request.top_k

            sql = f"""
                WITH semantic AS (
                    SELECT id, doc_id, doc_type, title, citation, jurisdiction, court,
                           practice_area, status, LEFT(content, 300) as content_snippet,
                           1 - (content_embedding <=> %(query_vec)s::vector) AS similarity,
                           ROW_NUMBER() OVER (ORDER BY content_embedding <=> %(query_vec)s::vector) AS sem_rank
                    FROM legal_documents
                    WHERE {filter_clause}
                      AND content_embedding IS NOT NULL
                    LIMIT 20
                ),
                keyword AS (
                    SELECT id, doc_id, doc_type, title, citation, jurisdiction, court,
                           practice_area, status, LEFT(content, 300) as content_snippet,
                           ts_rank(content_tsv, plainto_tsquery('english', %(query_text)s)) AS kw_score,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %(query_text)s)) DESC
                           ) AS kw_rank
                    FROM legal_documents
                    WHERE content_tsv @@ plainto_tsquery('english', %(query_text)s)
                      AND {filter_clause}
                    LIMIT 20
                )
                SELECT
                    COALESCE(s.id, k.id) as id,
                    COALESCE(s.doc_id, k.doc_id) as doc_id,
                    COALESCE(s.doc_type, k.doc_type) as doc_type,
                    COALESCE(s.title, k.title) as title,
                    COALESCE(s.citation, k.citation) as citation,
                    COALESCE(s.jurisdiction, k.jurisdiction) as jurisdiction,
                    COALESCE(s.court, k.court) as court,
                    COALESCE(s.practice_area, k.practice_area) as practice_area,
                    COALESCE(s.status, k.status) as status,
                    COALESCE(s.content_snippet, k.content_snippet) as content_snippet,
                    COALESCE(s.similarity, 0) as similarity,
                    COALESCE(1.0/(60 + s.sem_rank), 0) + COALESCE(1.0/(60 + k.kw_rank), 0) AS rrf_score,
                    CASE
                        WHEN s.id IS NOT NULL AND k.id IS NOT NULL THEN 'hybrid'
                        WHEN s.id IS NOT NULL THEN 'semantic'
                        ELSE 'keyword'
                    END as search_method
                FROM semantic s
                FULL OUTER JOIN keyword k ON s.id = k.id
                ORDER BY rrf_score DESC
                LIMIT %(top_k)s
            """

            cur.execute(sql, filter_params)

        else:
            # SEMANTIC SEARCH on specified field
            query_embedding = get_legal_embedding(request.query)
            filter_params["query_vec"] = query_embedding
            filter_params["top_k"] = request.top_k

            embedding_col = {
                "title": "title_embedding",
                "headnotes": "headnote_embedding",
            }.get(request.search_field, "content_embedding")

            sql = f"""
                SELECT id, doc_id, doc_type, title, citation, jurisdiction, court,
                       practice_area, status, LEFT(content, 300) as content_snippet,
                       1 - ({embedding_col} <=> %(query_vec)s::vector) AS similarity,
                       'semantic' as search_method
                FROM legal_documents
                WHERE {filter_clause}
                  AND {embedding_col} IS NOT NULL
                ORDER BY {embedding_col} <=> %(query_vec)s::vector
                LIMIT %(top_k)s
            """

            cur.execute(sql, filter_params)

        results = cur.fetchall()
        cur.close()
        conn.close()

        return [
            LegalSearchResult(
                id=r["id"],
                doc_id=r["doc_id"],
                doc_type=r["doc_type"],
                title=r["title"],
                citation=r.get("citation"),
                jurisdiction=r.get("jurisdiction"),
                court=r.get("court"),
                practice_area=r.get("practice_area"),
                status=r.get("status"),
                content_snippet=r.get("content_snippet", ""),
                similarity=float(r.get("similarity", 0)),
                search_method=r.get("search_method", "semantic")
            )
            for r in results
        ]

    except Exception as e:
        logger.error(f"Legal search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/legal/rag", response_model=LegalRAGResponse, tags=["Legal RAG"],
    summary="Legal RAG with citations",
    description="""Legal Retrieval-Augmented Generation with source citation tracking.

**Pipeline**:
1. Hybrid search retrieves the top-k most relevant legal authorities
2. Assembles numbered context with citations, jurisdiction, and document type
3. Phi-3.5 Mini generates an answer using a **legal publisher system prompt** requiring bracketed citations
4. Extracts citation references from the answer and maps them to source documents
5. Returns faithfulness assessment (how many sources were actually cited)

**Quality controls**: Overruled authorities excluded by default. System prompt requires `[NEEDS REVIEW]` prefix for uncertain interpretations and `Insufficient sources` when context is inadequate.""",
    response_description="Generated legal answer with citations, source documents, and faithfulness assessment")
async def legal_rag_query(request: LegalRAGRequest):
    """Legal RAG: retrieve relevant authorities then generate a cited answer."""
    if llm is None or legal_embedder is None:
        raise HTTPException(status_code=503, detail="Models not loaded")

    try:
        # Step 1: Search for relevant legal documents using hybrid search
        search_request = LegalSearchRequest(
            query=request.query,
            top_k=request.top_k,
            search_field="hybrid",
            jurisdiction=request.jurisdiction,
            practice_area=request.practice_area,
            status_filter="exclude_overruled" if request.exclude_overruled else None
        )
        results = await search_legal_documents(search_request)

        # Step 2: Build context with citation information
        context_parts = []
        for i, result in enumerate(results, 1):
            citation_str = f" ({result.citation})" if result.citation else ""
            status_str = f" [STATUS: {result.status}]" if result.status and result.status != "good_law" else ""
            context_parts.append(
                f"[{i}] {result.title}{citation_str}{status_str}\n"
                f"Type: {result.doc_type} | Jurisdiction: {result.jurisdiction}\n"
                f"{result.content_snippet}"
            )
        context = "\n\n".join(context_parts)

        # Step 3: Generate answer using Phi-3.5 Mini with legal-specific system prompt
        system_prompt = """You are a legal content editor at a major legal publisher.

RULES:
1. ONLY use information from the provided source documents. Do not add facts from training data.
2. Every factual claim must include a citation in [brackets] referencing the source number.
3. If uncertain about any legal interpretation, prefix with [NEEDS REVIEW].
4. If sources are insufficient to answer the question, say "Insufficient sources" rather than guessing.
5. Note if any cited authority has been overruled or questioned."""

        user_prompt = f"""SOURCES:
{context}

QUESTION: {request.query}

Provide your answer with citations:"""

        # Step 4: Generate answer using Phi-3.5 Mini chat completion
        output = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150,
            temperature=0.3,
        )

        answer = output["choices"][0]["message"]["content"]

        # Step 5: Extract citations used from the answer
        import re
        citation_refs = re.findall(r'\[(\d+)\]', answer)
        citations_used = []
        for ref in set(citation_refs):
            idx = int(ref) - 1
            if 0 <= idx < len(results) and results[idx].citation:
                citations_used.append(results[idx].citation)

        # Step 6: Faithfulness note
        if not citation_refs:
            faithfulness_note = "WARNING: No source citations found in generated answer. Claims may not be grounded."
        elif len(results) == 0:
            faithfulness_note = "WARNING: No source documents retrieved. Answer may not be grounded."
        else:
            faithfulness_note = f"Answer references {len(set(citation_refs))} source(s) out of {len(results)} retrieved."

        return LegalRAGResponse(
            query=request.query,
            answer=answer,
            sources=results,
            citations_used=citations_used,
            faithfulness_note=faithfulness_note
        )

    except Exception as e:
        logger.error(f"Legal RAG error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/legal/documents/count", tags=["Legal Documents"], summary="Get legal document count",
    description="Returns the total number of legal documents, grouped by document type (case_law, statute, regulation, practice_guide).",
    response_description="Total count and breakdown by document type")
async def get_legal_document_count():
    """Get total count of legal documents, grouped by type."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT doc_type, COUNT(*) as count
            FROM legal_documents
            GROUP BY doc_type
            ORDER BY count DESC
        """)
        by_type = {r["doc_type"]: r["count"] for r in cur.fetchall()}

        cur.execute("SELECT COUNT(*) as total FROM legal_documents")
        total = cur.fetchone()["total"]

        cur.close()
        conn.close()

        return {"total": total, "by_type": by_type}

    except Exception as e:
        logger.error(f"Error getting legal doc count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/legal/documents/{doc_id}", tags=["Legal Documents"], summary="Get legal document by ID",
    description="Retrieve a specific legal document by its doc_id (e.g., 'case-001'). Returns full document including content, citation, jurisdiction, and status.",
    response_description="Full legal document record")
async def get_legal_document(doc_id: str):
    """Get a specific legal document by doc_id."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, doc_id, doc_type, title, citation, jurisdiction,
                   date_decided, court, content, headnotes, practice_area, status,
                   created_at
            FROM legal_documents
            WHERE doc_id = %s
            """,
            (doc_id,)
        )

        result = cur.fetchone()
        cur.close()
        conn.close()

        if result is None:
            raise HTTPException(status_code=404, detail=f"Legal document '{doc_id}' not found")

        # Convert date to string for JSON serialization
        result_dict = dict(result)
        if result_dict.get("date_decided"):
            result_dict["date_decided"] = str(result_dict["date_decided"])
        if result_dict.get("created_at"):
            result_dict["created_at"] = str(result_dict["created_at"])

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting legal document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
