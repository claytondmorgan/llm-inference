"""Semantic (vector) search against the memory_chunks table.

Uses pgvector cosine distance to find the most similar chunks to a
query embedding.  Modeled after the semantic search in app.py lines 586-618.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result returned by any search method.

    Attributes:
        chunk_id: Primary key of the memory_chunks row.
        content: The chunk text.
        similarity: Cosine similarity (semantic) or RRF score (hybrid).
        search_method: One of 'semantic', 'keyword', or 'hybrid'.
        block_type: Optional block type label (e.g. 'code', 'markdown').
        metadata: JSONB metadata dict from the chunk row.
        source_path: File path from the parent memory_sources row.
    """

    chunk_id: int
    content: str
    similarity: float
    search_method: str
    block_type: str | None = None
    metadata: dict = field(default_factory=dict)
    source_path: str | None = None


def semantic_search(
    query_embedding: list[float],
    top_k: int,
    db_conn: psycopg2.extensions.connection,
    filter_clause: str = "TRUE",
    filter_params: dict | None = None,
) -> list[SearchResult]:
    """Run a pure vector-similarity search on memory_chunks.

    Args:
        query_embedding: The query vector (dimension must match the table's
            embedding column, typically 384).
        top_k: Maximum number of results to return.
        db_conn: An open psycopg2 connection.
        filter_clause: A SQL WHERE fragment (e.g. ``"ms.project_path = %(project)s"``).
            Defaults to ``"TRUE"`` (no filtering).
        filter_params: Parameter dict referenced by *filter_clause*.  These are
            merged with the query's own parameters before execution.

    Returns:
        A list of :class:`SearchResult` objects ordered by descending
        cosine similarity.
    """
    params: dict = {"query_vec": query_embedding, "top_k": top_k}
    if filter_params:
        params.update(filter_params)

    sql = f"""
        SELECT
            mc.id          AS chunk_id,
            mc.content,
            mc.block_type,
            mc.metadata,
            ms.file_path   AS source_path,
            1 - (mc.embedding <=> %(query_vec)s::vector) AS similarity
        FROM memory_chunks mc
        JOIN memory_sources ms ON ms.id = mc.source_id
        WHERE mc.embedding IS NOT NULL
          AND {filter_clause}
        ORDER BY mc.embedding <=> %(query_vec)s::vector
        LIMIT %(top_k)s
    """

    cur = db_conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()

    results: list[SearchResult] = []
    for row in rows:
        results.append(
            SearchResult(
                chunk_id=row["chunk_id"],
                content=row["content"],
                similarity=float(row["similarity"]),
                search_method="semantic",
                block_type=row["block_type"],
                metadata=row["metadata"] or {},
                source_path=row["source_path"],
            )
        )

    logger.debug(
        "semantic_search returned %d results (top_k=%d)", len(results), top_k
    )
    return results
