"""Database manager for the Claude RAG system.

Extends the pattern from lambda-s3-trigger/ingestion-worker/app/database.py
with local config support and memory-chunk–specific operations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from claude_rag.config import Config

logger = logging.getLogger(__name__)


@dataclass
class SourceRecord:
    """Represents a row in memory_sources."""

    id: int
    file_path: str
    file_hash: str
    file_type: str
    project_path: Optional[str] = None
    last_ingested_at: Optional[datetime] = None
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ChunkRecord:
    """Data transfer object for inserting/updating a memory chunk."""

    chunk_index: int
    content: str
    block_type: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    embedding: Optional[list[float]] = None


class DatabaseManager:
    """Manages connections and CRUD for memory_sources / memory_chunks."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        logger.info("DatabaseManager initialized (host=%s, db=%s)", self.config.PGHOST, self.config.PGDATABASE)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Create a new database connection using local config."""
        return psycopg2.connect(
            host=self.config.PGHOST,
            port=self.config.PGPORT,
            database=self.config.PGDATABASE,
            user=self.config.PGUSER,
            password=self.config.PGPASSWORD,
        )

    def test_connection(self) -> bool:
        """Return True if the database is reachable."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            return True
        except Exception as exc:
            logger.error("Connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Source operations
    # ------------------------------------------------------------------

    def upsert_source(
        self,
        file_path: str,
        file_hash: str,
        file_type: str,
        project_path: Optional[str] = None,
    ) -> int:
        """Insert or update a memory source, returning the source id."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO memory_sources (file_path, file_hash, file_type, project_path, last_ingested_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (file_path) DO UPDATE SET
                file_hash = EXCLUDED.file_hash,
                file_type = EXCLUDED.file_type,
                project_path = EXCLUDED.project_path,
                last_ingested_at = NOW(),
                updated_at = NOW()
            RETURNING id
            """,
            (file_path, file_hash, file_type, project_path),
        )
        source_id: int = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Upserted source %s (id=%d)", file_path, source_id)
        return source_id

    def get_source_by_path(self, file_path: str) -> Optional[SourceRecord]:
        """Look up a source by its file path."""
        conn = self._get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM memory_sources WHERE file_path = %s", (file_path,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row is None:
            return None
        return SourceRecord(**row)

    def delete_source(self, source_id: int) -> None:
        """Delete a source and its chunks (cascade)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM memory_sources WHERE id = %s", (source_id,))
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Deleted source id=%d (cascaded chunks)", source_id)

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    def upsert_chunks(self, source_id: int, chunks: list[ChunkRecord]) -> int:
        """Replace all chunks for a source with the given list.

        Deletes existing chunks for the source then bulk-inserts the new ones.
        Updates the source's chunk_count.
        """
        conn = self._get_connection()
        cur = conn.cursor()

        # Delete old chunks
        cur.execute("DELETE FROM memory_chunks WHERE source_id = %s", (source_id,))

        if not chunks:
            cur.execute(
                "UPDATE memory_sources SET chunk_count = 0, updated_at = NOW() WHERE id = %s",
                (source_id,),
            )
            conn.commit()
            cur.close()
            conn.close()
            return 0

        values = [
            (
                source_id,
                c.chunk_index,
                c.content,
                c.block_type,
                json.dumps(c.metadata),
                c.embedding,
            )
            for c in chunks
        ]

        execute_values(
            cur,
            """
            INSERT INTO memory_chunks
                (source_id, chunk_index, content, block_type, metadata, embedding)
            VALUES %s
            """,
            values,
            template="(%s, %s, %s, %s, %s::jsonb, %s::vector)",
        )

        cur.execute(
            "UPDATE memory_sources SET chunk_count = %s, updated_at = NOW() WHERE id = %s",
            (len(chunks), source_id),
        )

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Upserted %d chunks for source_id=%d", len(chunks), source_id)
        return len(chunks)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_chunk_count(self) -> int:
        """Return total number of memory chunks."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM memory_chunks")
        count: int = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count

    def get_source_count(self) -> int:
        """Return total number of tracked sources."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM memory_sources")
        count: int = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
