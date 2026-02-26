"""Ingestion pipeline for the Claude Code RAG system.

Orchestrates the full flow: file hashing → parsing → chunking → embedding →
database storage.  Provides both single-file and directory-level entry points.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from claude_rag.config import Config
from claude_rag.db.manager import ChunkRecord, DatabaseManager
from claude_rag.embeddings.base import EmbeddingProvider
from claude_rag.embeddings.local import LocalEmbeddingProvider
from claude_rag.ingestion.chunker import Chunk, chunk_blocks
from claude_rag.ingestion.metadata import enrich_chunk_metadata
from claude_rag.ingestion.parser import ParsedBlock, parse_claude_md, parse_session_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class IngestionResult:
    """Outcome of ingesting a single file.

    Attributes:
        source_id: Database primary key for the ingested source.
        chunks_created: Number of chunks written to the database.
        duration_ms: Wall-clock time spent on the ingestion, in milliseconds.
        skipped: ``True`` when the file hash matched the existing record and
            no work was performed.
    """

    source_id: int
    chunks_created: int
    duration_ms: float
    skipped: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_file_hash(file_path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of a file's contents.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Lowercase hex string of the SHA-256 digest.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for buf in iter(lambda: fh.read(65_536), b""):
            hasher.update(buf)
    return hasher.hexdigest()


def _detect_file_type(file_path: Path) -> str:
    """Determine the semantic file type from the file name.

    Args:
        file_path: Path to the file.

    Returns:
        One of ``"claude_md"``, ``"session_log"``, or ``"settings"``.
    """
    name_upper = file_path.name.upper()
    if "CLAUDE" in name_upper:
        return "claude_md"
    if "SESSION" in name_upper:
        return "session_log"
    return "settings"


def _detect_project_path(file_path: Path) -> str | None:
    """Walk up from *file_path* to find the nearest directory containing ``.git``.

    If no ``.git`` directory is found, the file's immediate parent directory
    is returned as a fallback.

    Args:
        file_path: Resolved path to the ingested file.

    Returns:
        String representation of the project root, or the file's parent
        directory if no ``.git`` marker is found.
    """
    current = file_path.parent
    while True:
        if (current / ".git").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding .git
            break
        current = parent
    return str(file_path.parent)


def _chunks_to_records(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    source_path: str | None = None,
) -> list[ChunkRecord]:
    """Convert ``Chunk`` objects and their embeddings into ``ChunkRecord`` DTOs.

    Enriches each chunk's metadata with file references, language detection,
    intent classification, and project name via :func:`enrich_chunk_metadata`.

    Args:
        chunks: Ordered list of chunks produced by the chunker.
        embeddings: Parallel list of embedding vectors (one per chunk).
        source_path: File path the chunks were parsed from, used for
            project-name extraction.

    Returns:
        List of ``ChunkRecord`` objects ready for database insertion.
    """
    records: list[ChunkRecord] = []
    for chunk, embedding in zip(chunks, embeddings):
        # Determine the primary block type from chunk metadata
        block_types: list[str] = chunk.metadata.get("block_types", [])
        primary_type = block_types[0] if block_types else None

        # Enrich metadata with file refs, language, intent, project
        enriched_meta = enrich_chunk_metadata(
            content=chunk.content,
            block_type=primary_type,
            source_path=source_path,
            existing_metadata=chunk.metadata,
        )

        records.append(
            ChunkRecord(
                chunk_index=chunk.index,
                content=chunk.content,
                block_type=primary_type,
                metadata=enriched_meta,
                embedding=embedding,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class IngestionPipeline:
    """Orchestrates parser, chunker, embedder, and database storage.

    Accepts optional overrides for the config, embedding provider, and
    database manager.  When omitted, sensible defaults are constructed from
    the global ``Config``.

    Args:
        config: Application configuration.  Defaults to ``Config()``.
        embedding_provider: Provider used to generate embedding vectors.
            Defaults to ``LocalEmbeddingProvider``.
        db: Database manager for source and chunk persistence.  Defaults to
            ``DatabaseManager(config)``.
    """

    def __init__(
        self,
        config: Config | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        db: DatabaseManager | None = None,
    ) -> None:
        self.config = config or Config()
        self.embedder = embedding_provider or LocalEmbeddingProvider()
        self.db = db or DatabaseManager(self.config)

        logger.info(
            "IngestionPipeline initialized (chunk_size=%d, overlap=%d, embedding_dim=%d)",
            self.config.CHUNK_SIZE,
            self.config.CHUNK_OVERLAP,
            self.embedder.dimension,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_file(self, file_path: str) -> IngestionResult:
        """Ingest a single file into the RAG database.

        Steps performed:
            1. Compute SHA-256 hash of the file.
            2. Check if a source record with the same hash already exists;
               skip processing if the content is unchanged.
            3. Determine file type from the file name.
            4. Parse the file using the appropriate parser.
            5. Chunk the parsed blocks.
            6. Embed all chunks in batch.
            7. Upsert the source and chunks to the database.

        Args:
            file_path: Absolute or relative path to the file to ingest.

        Returns:
            An ``IngestionResult`` summarising the outcome.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            ValueError: If the file produces no parseable blocks.
        """
        t0 = time.perf_counter()
        resolved = Path(file_path).resolve()

        logger.info("Starting ingestion for %s", resolved)

        # 1. Compute file hash
        file_hash = _compute_file_hash(resolved)
        logger.debug("SHA-256 hash: %s", file_hash)

        # 2. Check for existing source with the same hash
        existing = self.db.get_source_by_path(str(resolved))
        if existing is not None and existing.file_hash == file_hash:
            elapsed_ms = (time.perf_counter() - t0) * 1_000
            logger.info(
                "Skipping %s — hash unchanged (source_id=%d, %.1f ms)",
                resolved,
                existing.id,
                elapsed_ms,
            )
            return IngestionResult(
                source_id=existing.id,
                chunks_created=existing.chunk_count,
                duration_ms=elapsed_ms,
                skipped=True,
            )

        # 3. Determine file type and project path
        file_type = _detect_file_type(resolved)
        project_path = _detect_project_path(resolved)
        logger.debug("file_type=%s, project_path=%s", file_type, project_path)

        # 4. Parse the file
        blocks = self._parse(resolved, file_type)
        logger.info("Parsed %d blocks from %s", len(blocks), resolved)

        # 5. Chunk the parsed blocks
        chunks = chunk_blocks(
            blocks,
            chunk_size=self.config.CHUNK_SIZE,
            overlap=self.config.CHUNK_OVERLAP,
        )
        logger.info("Created %d chunks from %d blocks", len(chunks), len(blocks))

        # 6. Embed all chunks in batch
        texts = [c.content for c in chunks]
        embeddings = self._embed_batch(texts)
        logger.info("Generated %d embeddings (dim=%d)", len(embeddings), self.embedder.dimension)

        # 7. Upsert source and chunks to the database
        source_id = self.db.upsert_source(
            file_path=str(resolved),
            file_hash=file_hash,
            file_type=file_type,
            project_path=project_path,
        )

        records = _chunks_to_records(chunks, embeddings, source_path=str(resolved))
        chunks_created = self.db.upsert_chunks(source_id, records)

        elapsed_ms = (time.perf_counter() - t0) * 1_000
        logger.info(
            "Ingested %s — source_id=%d, chunks=%d, %.1f ms",
            resolved,
            source_id,
            chunks_created,
            elapsed_ms,
        )

        return IngestionResult(
            source_id=source_id,
            chunks_created=chunks_created,
            duration_ms=elapsed_ms,
        )

    def ingest_directory(self, dir_path: str) -> list[IngestionResult]:
        """Ingest all ``.md`` files in a directory.

        Walks the directory tree and calls ``ingest_file`` on every
        Markdown file found.

        Args:
            dir_path: Path to the directory to scan.

        Returns:
            A list of ``IngestionResult`` objects, one per file processed.

        Raises:
            NotADirectoryError: If *dir_path* is not a directory.
        """
        directory = Path(dir_path).resolve()
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        md_files = sorted(directory.rglob("*.md"))
        logger.info("Found %d .md files in %s", len(md_files), directory)

        results: list[IngestionResult] = []
        for md_file in md_files:
            try:
                result = self.ingest_file(str(md_file))
                results.append(result)
            except Exception:
                logger.exception("Failed to ingest %s", md_file)

        ingested = sum(1 for r in results if not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        logger.info(
            "Directory ingestion complete: %d ingested, %d skipped, %d errors",
            ingested,
            skipped,
            len(md_files) - len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse(self, file_path: Path, file_type: str) -> list[ParsedBlock]:
        """Dispatch to the appropriate parser based on file type.

        Args:
            file_path: Resolved path to the file.
            file_type: One of ``"claude_md"``, ``"session_log"``, or
                ``"settings"``.

        Returns:
            List of ``ParsedBlock`` instances extracted from the file.
        """
        path_str = str(file_path)
        if file_type == "session_log":
            return parse_session_log(path_str)
        # Both claude_md and settings use the generic markdown parser
        return parse_claude_md(path_str)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, respecting the configured batch size.

        Splits the input into batches of ``Config.EMBEDDING_BATCH_SIZE``
        and concatenates the results.

        Args:
            texts: Strings to embed.

        Returns:
            Parallel list of embedding vectors.
        """
        if not texts:
            return []

        batch_size = self.config.EMBEDDING_BATCH_SIZE
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self.embedder.embed(batch)
            all_embeddings.extend(embeddings)
            logger.debug(
                "Embedded batch %d–%d of %d",
                i,
                min(i + batch_size, len(texts)),
                len(texts),
            )

        return all_embeddings
