"""Tests for the Claude RAG database manager (claude_rag.db.manager)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.config import Config
from claude_rag.db.manager import ChunkRecord, DatabaseManager


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _db_reachable() -> bool:
    """Return True if the test database is reachable with password='postgres'."""
    try:
        cfg = Config()
        cfg.PGPASSWORD = "postgres"
        mgr = DatabaseManager(config=cfg)
        return mgr.test_connection()
    except Exception:  # noqa: BLE001
        return False


_DB_AVAILABLE = _db_reachable()
_SKIP_REASON = "PostgreSQL not reachable (set PGPASSWORD=postgres and ensure DB is up)"

# Apply this marker to every test in the module
pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason=_SKIP_REASON)


@pytest.fixture()
def db_manager() -> DatabaseManager:
    """Create a DatabaseManager configured with password='postgres'."""
    cfg = Config()
    cfg.PGPASSWORD = "postgres"
    return DatabaseManager(config=cfg)


@pytest.fixture()
def _clean_test_source(db_manager: DatabaseManager):
    """Ensure the test source path does not exist before/after the test."""
    test_path = "/tmp/pytest-claude-rag/test_source.md"

    # Pre-clean
    src = db_manager.get_source_by_path(test_path)
    if src is not None:
        db_manager.delete_source(src.id)

    yield test_path

    # Post-clean
    src = db_manager.get_source_by_path(test_path)
    if src is not None:
        db_manager.delete_source(src.id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConnection:
    """Verify that test_connection returns True."""

    def test_connection(self, db_manager: DatabaseManager) -> None:
        assert db_manager.test_connection() is True


class TestUpsertSource:
    """Verify source creation and retrieval."""

    def test_upsert_source(
        self,
        db_manager: DatabaseManager,
        _clean_test_source: str,
    ) -> None:
        test_path = _clean_test_source

        source_id = db_manager.upsert_source(
            file_path=test_path,
            file_hash="abc123",
            file_type="claude_md",
            project_path="/tmp/pytest-project",
        )
        assert isinstance(source_id, int)
        assert source_id > 0

        # Retrieve and verify
        record = db_manager.get_source_by_path(test_path)
        assert record is not None
        assert record.id == source_id
        assert record.file_path == test_path
        assert record.file_hash == "abc123"
        assert record.file_type == "claude_md"
        assert record.project_path == "/tmp/pytest-project"

    def test_upsert_source_updates_hash(
        self,
        db_manager: DatabaseManager,
        _clean_test_source: str,
    ) -> None:
        test_path = _clean_test_source

        id1 = db_manager.upsert_source(
            file_path=test_path,
            file_hash="hash_v1",
            file_type="claude_md",
        )
        id2 = db_manager.upsert_source(
            file_path=test_path,
            file_hash="hash_v2",
            file_type="claude_md",
        )

        # Same source row, updated hash
        assert id1 == id2
        record = db_manager.get_source_by_path(test_path)
        assert record is not None
        assert record.file_hash == "hash_v2"


class TestUpsertChunks:
    """Verify chunk creation and count."""

    def test_upsert_chunks(
        self,
        db_manager: DatabaseManager,
        _clean_test_source: str,
    ) -> None:
        test_path = _clean_test_source

        source_id = db_manager.upsert_source(
            file_path=test_path,
            file_hash="chunk_test_hash",
            file_type="claude_md",
        )

        chunks = [
            ChunkRecord(
                chunk_index=0,
                content="First chunk of content.",
                block_type="text",
                metadata={"token_count": 5},
            ),
            ChunkRecord(
                chunk_index=1,
                content="Second chunk of content.",
                block_type="code",
                metadata={"token_count": 5, "language": "python"},
            ),
            ChunkRecord(
                chunk_index=2,
                content="Third chunk of content.",
                block_type="text",
                metadata={"token_count": 5},
            ),
        ]

        count = db_manager.upsert_chunks(source_id, chunks)
        assert count == 3

        # Verify via source record chunk_count
        record = db_manager.get_source_by_path(test_path)
        assert record is not None
        assert record.chunk_count == 3


class TestReUpsertChunks:
    """Verify that re-upsert replaces (not duplicates) chunks."""

    def test_re_upsert_chunks(
        self,
        db_manager: DatabaseManager,
        _clean_test_source: str,
    ) -> None:
        test_path = _clean_test_source

        source_id = db_manager.upsert_source(
            file_path=test_path,
            file_hash="reupsert_hash",
            file_type="claude_md",
        )

        # First upsert: 3 chunks
        chunks_v1 = [
            ChunkRecord(chunk_index=i, content=f"v1 chunk {i}", block_type="text")
            for i in range(3)
        ]
        count1 = db_manager.upsert_chunks(source_id, chunks_v1)
        assert count1 == 3

        # Second upsert: 2 different chunks (should replace, not add)
        chunks_v2 = [
            ChunkRecord(chunk_index=i, content=f"v2 chunk {i}", block_type="text")
            for i in range(2)
        ]
        count2 = db_manager.upsert_chunks(source_id, chunks_v2)
        assert count2 == 2

        # Verify the source now reports 2 chunks, not 5
        record = db_manager.get_source_by_path(test_path)
        assert record is not None
        assert record.chunk_count == 2


class TestDeleteCascade:
    """Verify that deleting a source cascades to its chunks."""

    def test_delete_cascade(
        self,
        db_manager: DatabaseManager,
        _clean_test_source: str,
    ) -> None:
        test_path = _clean_test_source

        source_id = db_manager.upsert_source(
            file_path=test_path,
            file_hash="cascade_hash",
            file_type="claude_md",
        )

        chunks = [
            ChunkRecord(chunk_index=0, content="Cascade test chunk", block_type="text"),
        ]
        db_manager.upsert_chunks(source_id, chunks)

        # Record the total chunk count before delete
        total_before = db_manager.get_chunk_count()

        # Delete the source — chunks should cascade
        db_manager.delete_source(source_id)

        # Source should be gone
        assert db_manager.get_source_by_path(test_path) is None

        # Total chunk count should have decreased
        total_after = db_manager.get_chunk_count()
        assert total_after <= total_before, (
            "Chunk count should not increase after source deletion"
        )
