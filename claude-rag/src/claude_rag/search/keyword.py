"""Full-text keyword search against the memory_chunks table.

Uses PostgreSQL ``ts_rank`` / ``plainto_tsquery`` over the ``content_tsv``
generated column.  Modeled after the keyword CTE in app.py lines 1157-1167.
"""

from __future__ import annotations

import logging

import psycopg2
from psycopg2.extras import RealDictCursor

from claude_rag.search.semantic import SearchResult

logger = logging.getLogger(__name__)


def keyword_search(
    query: str,
    top_k: int,
    db_conn: psycopg2.extensions.connection,
    filter_clause: str = "TRUE",
    filter_params: dict | None = None,
) -> list[SearchResult]:
    """Run a full-text keyword search on memory_chunks.

    Args:
        query: Natural-language query string.  Converted to a tsquery
            via ``plainto_tsquery('english', ...)``.
        top_k: Maximum number of results to return.
        db_conn: An open psycopg2 connection.
        filter_clause: A SQL WHERE fragment (e.g. ``"ms.project_path = %(project)s"``).
            Defaults to ``"TRUE"`` (no filtering).
        filter_params: Parameter dict referenced by *filter_clause*.  These are
            merged with the query's own parameters before execution.

    Returns:
        A list of :class:`SearchResult` objects ordered by descending
        ts_rank score.
    """
    params: dict = {"query_text": query, "top_k": top_k}
    if filter_params:
        params.update(filter_params)

    sql = f"""
        SELECT
            mc.id          AS chunk_id,
            mc.content,
            mc.block_type,
            mc.metadata,
            ms.file_path   AS source_path,
            ts_rank(mc.content_tsv, plainto_tsquery('english', %(query_text)s)) AS rank_score
        FROM memory_chunks mc
        JOIN memory_sources ms ON ms.id = mc.source_id
        WHERE mc.content_tsv @@ plainto_tsquery('english', %(query_text)s)
          AND {filter_clause}
        ORDER BY rank_score DESC
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
                similarity=float(row["rank_score"]),
                search_method="keyword",
                block_type=row["block_type"],
                metadata=row["metadata"] or {},
                source_path=row["source_path"],
            )
        )

    logger.debug(
        "keyword_search returned %d results (top_k=%d)", len(results), top_k
    )
    return results
