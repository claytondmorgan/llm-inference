"""Idempotent schema migration for the Claude RAG database.

Modeled after migrate_schema.py in the parent project.  Safe to run
multiple times — every step checks for existing objects before creating.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from claude_rag.config import Config


def _connect(cfg: Config) -> psycopg2.extensions.connection:
    """Create a database connection from the local config."""
    return psycopg2.connect(
        host=cfg.PGHOST,
        port=cfg.PGPORT,
        database=cfg.PGDATABASE,
        user=cfg.PGUSER,
        password=cfg.PGPASSWORD,
    )


def _table_exists(cur: psycopg2.extensions.cursor, table: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
        (table,),
    )
    return cur.fetchone()[0]


def _index_exists(cur: psycopg2.extensions.cursor, index: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = %s);",
        (index,),
    )
    return cur.fetchone()[0]


def run_migration(cfg: Config | None = None) -> None:
    """Execute the full migration against the configured database."""
    cfg = cfg or Config()

    conn = _connect(cfg)
    conn.autocommit = True
    cur = conn.cursor()

    print("=" * 60)
    print("Claude RAG — Database Migration")
    print("=" * 60)

    # Step 1: pgvector extension
    print("\n[1/5] Ensuring pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print("  OK — pgvector ready")

    # Step 2: memory_sources table
    print("\n[2/5] memory_sources table...")
    if _table_exists(cur, "memory_sources"):
        cur.execute("SELECT COUNT(*) FROM memory_sources;")
        print(f"  EXISTS — {cur.fetchone()[0]} rows")
    else:
        cur.execute(
            """
            CREATE TABLE memory_sources (
                id SERIAL PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                file_hash VARCHAR(64) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                project_path TEXT,
                last_ingested_at TIMESTAMP DEFAULT NOW(),
                chunk_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        print("  CREATED")

    # Step 3: memory_chunks table
    print("\n[3/5] memory_chunks table...")
    if _table_exists(cur, "memory_chunks"):
        cur.execute("SELECT COUNT(*) FROM memory_chunks;")
        print(f"  EXISTS — {cur.fetchone()[0]} rows")
    else:
        cur.execute(
            f"""
            CREATE TABLE memory_chunks (
                id SERIAL PRIMARY KEY,
                source_id INTEGER REFERENCES memory_sources(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                block_type VARCHAR(50),
                metadata JSONB DEFAULT '{{}}'::jsonb,
                embedding vector({cfg.EMBEDDING_DIM}),
                content_tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', coalesce(content, ''))
                ) STORED,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(source_id, chunk_index)
            );
            """
        )
        print("  CREATED")

    # Step 4: Indexes
    print("\n[4/5] Creating indexes...")
    indexes = [
        (
            "idx_chunks_embedding_hnsw",
            "CREATE INDEX idx_chunks_embedding_hnsw ON memory_chunks "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
        ),
        (
            "idx_chunks_content_fts",
            "CREATE INDEX idx_chunks_content_fts ON memory_chunks USING gin(content_tsv);",
        ),
        (
            "idx_chunks_source_id",
            "CREATE INDEX idx_chunks_source_id ON memory_chunks(source_id);",
        ),
        (
            "idx_chunks_block_type",
            "CREATE INDEX idx_chunks_block_type ON memory_chunks(block_type);",
        ),
        (
            "idx_sources_project",
            "CREATE INDEX idx_sources_project ON memory_sources(project_path);",
        ),
        (
            "idx_sources_file_type",
            "CREATE INDEX idx_sources_file_type ON memory_sources(file_type);",
        ),
        (
            "idx_chunks_metadata",
            "CREATE INDEX idx_chunks_metadata ON memory_chunks USING gin(metadata);",
        ),
    ]

    for name, ddl in indexes:
        if _index_exists(cur, name):
            print(f"  EXISTS — {name}")
        else:
            cur.execute(ddl)
            print(f"  CREATED — {name}")

    # Step 5: Verify
    print("\n[5/5] Verifying migration...")
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name;"
    )
    tables = [r[0] for r in cur.fetchall()]
    print(f"  Tables: {', '.join(tables)}")

    cur.execute(
        "SELECT indexname, tablename FROM pg_indexes "
        "WHERE schemaname = 'public' ORDER BY tablename, indexname;"
    )
    print("  Indexes:")
    for row in cur.fetchall():
        print(f"    {row[0]} (on {row[1]})")

    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    ver = cur.fetchone()
    if ver:
        print(f"  pgvector version: {ver[0]}")

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as exc:
        print(f"\nMigration failed: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
