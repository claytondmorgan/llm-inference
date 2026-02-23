-- ============================================================
-- Legal Documents Table Schema
-- For LexisNexis Legal Document Search Demo
-- ============================================================

-- Ensure pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Legal documents table (runs alongside ingested_records)
CREATE TABLE IF NOT EXISTS legal_documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(50) UNIQUE NOT NULL,
    doc_type VARCHAR(50) NOT NULL,           -- case_law, statute, regulation, practice_guide, headnote
    title TEXT NOT NULL,
    citation VARCHAR(200),                   -- Bluebook citation
    jurisdiction VARCHAR(100),               -- US_Supreme_Court, CA, NY, Federal_9th_Circuit, etc.
    date_decided DATE,
    court VARCHAR(200),
    content TEXT NOT NULL,                    -- Full text body
    headnotes TEXT,                           -- Summary text
    practice_area VARCHAR(100),              -- constitutional_law, employment, criminal, etc.
    status VARCHAR(50) DEFAULT 'good_law',   -- good_law, distinguished, overruled, questioned

    -- Embeddings (768-dim, ModernBERT legal fine-tuned)
    title_embedding vector(768),
    content_embedding vector(768),
    headnote_embedding vector(768),          -- Separate embedding for headnotes

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Full-text search columns for BM25-style hybrid search
    title_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, ''))) STORED,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
);

-- HNSW indexes for vector search (3 embedding columns)
CREATE INDEX IF NOT EXISTS idx_legal_title_hnsw ON legal_documents
    USING hnsw (title_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_legal_content_hnsw ON legal_documents
    USING hnsw (content_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_legal_headnote_hnsw ON legal_documents
    USING hnsw (headnote_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- GIN indexes for full-text search (hybrid search)
CREATE INDEX IF NOT EXISTS idx_legal_title_fts ON legal_documents USING gin(title_tsv);
CREATE INDEX IF NOT EXISTS idx_legal_content_fts ON legal_documents USING gin(content_tsv);

-- B-tree indexes for metadata filtering
CREATE INDEX IF NOT EXISTS idx_legal_jurisdiction ON legal_documents(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_legal_doc_type ON legal_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_legal_practice_area ON legal_documents(practice_area);
CREATE INDEX IF NOT EXISTS idx_legal_status ON legal_documents(status);
CREATE INDEX IF NOT EXISTS idx_legal_date ON legal_documents(date_decided);