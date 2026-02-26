"""Integration tests for the ingestion pipeline with metadata enrichment."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.config import Config

# Skip if DB is not available
try:
    _cfg = Config()
    _cfg.PGPASSWORD = "postgres"
    import psycopg2

    conn = psycopg2.connect(
        host=_cfg.PGHOST,
        port=_cfg.PGPORT,
        database=_cfg.PGDATABASE,
        user=_cfg.PGUSER,
        password=_cfg.PGPASSWORD,
    )
    conn.close()
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE, reason="PostgreSQL not available"
)


@pytest.fixture()
def pipeline():
    """Create an IngestionPipeline with test config."""
    from claude_rag.db.manager import DatabaseManager
    from claude_rag.ingestion.pipeline import IngestionPipeline

    cfg = Config()
    cfg.PGPASSWORD = "postgres"
    return IngestionPipeline(config=cfg)


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """Write a sample CLAUDE.md with references and code."""
    content = """\
# Project Instructions

## Architecture
This is a FastAPI app with PostgreSQL + pgvector for semantic search.

## Bug Fix
Fixed the failing test in tests/test_search.py that compared float equality.
Also updated src/search/hybrid.py to round RRF scores.

```python
def get_embedding(text: str) -> list[float]:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text).tolist()
```

## Configuration
Set PGHOST=localhost and PGPORT=5432 in your .env file.
"""
    p = tmp_path / "CLAUDE_test.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestPipelineMetadataEnrichment:
    """Verify that metadata enrichment works end-to-end."""

    @pytest.mark.slow
    def test_ingest_enriches_metadata(self, pipeline, sample_file) -> None:
        """Ingested chunks should have enriched metadata (files, language, intent)."""
        result = pipeline.ingest_file(str(sample_file))
        assert result.chunks_created > 0
        assert not result.skipped

        # Query the DB for the chunks
        from claude_rag.db.manager import DatabaseManager

        cfg = Config()
        cfg.PGPASSWORD = "postgres"
        db = DatabaseManager(cfg)
        conn = db._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT content, block_type, metadata FROM memory_chunks WHERE source_id = %s ORDER BY chunk_index",
            (result.source_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        assert len(rows) == result.chunks_created

        # Check that at least one chunk has file references
        all_metadata = [row[2] for row in rows]
        has_files = any(m.get("files") for m in all_metadata if m)
        assert has_files, "At least one chunk should have file references"

        # Check that the code chunk has a language
        code_chunks = [
            (row[1], row[2]) for row in rows if row[1] == "code"
        ]
        if code_chunks:
            assert code_chunks[0][1].get("language") == "python"

        # Cleanup
        db.delete_source(result.source_id)

    @pytest.mark.slow
    def test_ingest_skip_unchanged(self, pipeline, sample_file) -> None:
        """Re-ingesting an unchanged file should be skipped."""
        r1 = pipeline.ingest_file(str(sample_file))
        r2 = pipeline.ingest_file(str(sample_file))
        assert not r1.skipped
        assert r2.skipped
        assert r1.source_id == r2.source_id

        # Cleanup
        from claude_rag.db.manager import DatabaseManager

        cfg = Config()
        cfg.PGPASSWORD = "postgres"
        db = DatabaseManager(cfg)
        db.delete_source(r1.source_id)
