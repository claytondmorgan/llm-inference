import os
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import pipeline, AutoTokenizer, AutoModel
import torch
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
generator = None
embedder = None
tokenizer = None


# ============================================================
# Pydantic Models
# ============================================================

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Input text prompt")
    max_new_tokens: int = Field(default=100, ge=1, le=500)
    temperature: float = Field(default=0.7, ge=0.1, le=2.0)

class GenerateResponse(BaseModel):
    generated_text: str
    model: str

class DocumentRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Document text to store")
    metadata: dict = Field(default={}, description="Optional metadata")

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")

class SearchResult(BaseModel):
    id: int
    content: str
    metadata: dict
    similarity: float

class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")
    top_k: int = Field(default=3, ge=1, le=10)
    max_new_tokens: int = Field(default=200, ge=1, le=500)

class RAGResponse(BaseModel):
    answer: str
    sources: List[SearchResult]

class IngestedSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=10, ge=1, le=50)
    category: Optional[str] = Field(default=None, description="Filter by category")
    search_field: str = Field(default="content", description="'content' or 'title'")

class IngestedSearchResult(BaseModel):
    id: int
    title: Optional[str]
    description: Optional[str]
    category: Optional[str]
    tags: Optional[list]
    raw_data: dict
    similarity: float


# ============================================================
# Helper Functions
# ============================================================

def get_db_credentials():
    """Get database credentials from Secrets Manager."""
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


# ============================================================
# App Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    global generator, embedder, tokenizer

    # Load text generation model
    gen_model_id = os.getenv("MODEL_ID", "distilgpt2")
    logger.info(f"Loading generation model: {gen_model_id}")

    hf_token = os.getenv("HF_TOKEN", None)

    generator = pipeline(
        "text-generation",
        model=gen_model_id,
        token=hf_token,
        torch_dtype=torch.float32,
        device=-1
    )

    if generator.tokenizer.pad_token is None:
        generator.tokenizer.pad_token = generator.tokenizer.eos_token

    logger.info("Generation model loaded")

    # Load embedding model
    embed_model_id = os.getenv("EMBED_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
    logger.info(f"Loading embedding model: {embed_model_id}")

    tokenizer = AutoTokenizer.from_pretrained(embed_model_id)
    embedder = AutoModel.from_pretrained(embed_model_id)
    embedder.eval()

    logger.info("Embedding model loaded")

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

app = FastAPI(
    title="LLM Inference API with Vector Search",
    description="Hugging Face model inference with pgvector RAG capabilities",
    version="3.0.0",
    lifespan=lifespan
)


# ============================================================
# Core Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_status = "unknown"
    try:
        conn = get_db_connection()
        conn.close()
        db_status = "connected"
    except:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "generator_loaded": generator is not None,
        "embedder_loaded": embedder is not None,
        "database": db_status
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "LLM Inference API with Vector Search",
        "version": "3.0.0",
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
            "health": "GET /health"
        }
    }


# ============================================================
# Embedding Generation (for Java service delegation)
# ============================================================

@app.post("/embed")
async def generate_embedding(request: dict):
    """Generate embedding vector for text.

    This endpoint is used by the Java search service to delegate
    embedding generation to Python, ensuring a single source of truth
    for the embedding model.
    """
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    text = request.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text field is required")

    try:
        embedding = get_embedding(text)

        return {
            "embedding": embedding,
            "dimensions": len(embedding),
            "model": os.getenv("EMBED_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
        }
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Text Generation
# ============================================================

@app.post("/generate", response_model=GenerateResponse)
async def generate_text(request: GenerateRequest):
    """Generate text from prompt."""
    if generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        outputs = generator(
            request.prompt,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            do_sample=True,
            pad_token_id=generator.tokenizer.eos_token_id
        )

        return GenerateResponse(
            generated_text=outputs[0]["generated_text"],
            model=os.getenv("MODEL_ID", "distilgpt2")
        )
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Document Management (original documents table)
# ============================================================

@app.post("/documents")
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


@app.post("/documents/batch")
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


@app.get("/documents/count")
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


@app.delete("/documents/{doc_id}")
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

@app.post("/search", response_model=List[SearchResult])
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

@app.post("/rag", response_model=RAGResponse)
async def rag_query(request: RAGRequest):
    """RAG: Retrieve documents and generate answer."""
    if generator is None or embedder is None:
        raise HTTPException(status_code=503, detail="Models not loaded")

    try:
        search_results = await search_documents(
            SearchRequest(query=request.query, top_k=request.top_k)
        )

        context_parts = []
        for i, result in enumerate(search_results, 1):
            context_parts.append(f"[{i}] {result.content}")

        context = "\n\n".join(context_parts)

        prompt = f"""Based on the following context, answer the question.

Context:
{context}

Question: {request.query}

Answer:"""

        outputs = generator(
            prompt,
            max_new_tokens=request.max_new_tokens,
            temperature=0.7,
            do_sample=True,
            pad_token_id=generator.tokenizer.eos_token_id
        )

        generated = outputs[0]["generated_text"]
        answer = generated.split("Answer:")[-1].strip()

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

@app.post("/search/records", response_model=List[IngestedSearchResult])
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

@app.get("/ingestion/jobs")
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


@app.get("/ingestion/stats")
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


@app.get("/ingestion/records/count")
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

@app.get("/debug/documents")
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


@app.get("/debug/search-test")
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
