-- ============================================================
-- Claude RAG Memory Chunks Schema
-- Modeled after schema_legal.sql from the parent project
-- ============================================================

-- Ensure pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Source files tracked by the RAG system
CREATE TABLE IF NOT EXISTS memory_sources (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(50) NOT NULL,       -- 'claude_md', 'session_log', 'settings'
    project_path TEXT,                     -- project root this file belongs to
    last_ingested_at TIMESTAMP DEFAULT NOW(),
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Chunks of memory content with embeddings and full-text search
CREATE TABLE IF NOT EXISTS memory_chunks (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES memory_sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    block_type VARCHAR(50),               -- 'instruction', 'code', 'reasoning', 'tool_output'
    metadata JSONB DEFAULT '{}',          -- file_references, language, intent, etc.

    -- Embeddings (384-dim, matching all-MiniLM-L6-v2)
    embedding vector(384),

    -- Full-text search
    content_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(source_id, chunk_index)
);

-- HNSW index for vector search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON memory_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON memory_chunks USING gin(content_tsv);

-- B-tree indexes for metadata filtering
CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON memory_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_block_type ON memory_chunks(block_type);
CREATE INDEX IF NOT EXISTS idx_sources_project ON memory_sources(project_path);
CREATE INDEX IF NOT EXISTS idx_sources_file_type ON memory_sources(file_type);

-- JSONB index for metadata queries
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON memory_chunks USING gin(metadata);
