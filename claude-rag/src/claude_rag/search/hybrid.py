"""Hybrid RRF (Reciprocal Rank Fusion) search combining semantic and keyword.

Directly adapted from the SQL in app.py lines 1146-1191:
  * ``semantic`` CTE — vector cosine similarity with ROW_NUMBER() ranking
  * ``keyword`` CTE  — ts_rank with ROW_NUMBER() ranking
  * FULL OUTER JOIN   — RRF score = 1/(k + sem_rank) + 1/(k + kw_rank)

Also provides :func:`build_filters`, modeled after ``_build_legal_filters``
in app.py lines 1084-1108.
"""

from __future__ import annotations

import logging

import psycopg2
from psycopg2.extras import RealDictCursor

from claude_rag.search.semantic import SearchResult

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Filter builder
# ------------------------------------------------------------------

def build_filters(
    project_filter: str | None = None,
    block_type_filter: str | None = None,
    language_filter: str | None = None,
    intent_filter: str | None = None,
    file_reference_filter: str | None = None,
) -> tuple[str, dict]:
    """Build a SQL WHERE clause and parameter dict from optional filters.

    Modeled after ``_build_legal_filters`` in app.py (lines 1084-1108).
    Each non-``None`` filter appends a condition and a corresponding
    named parameter.

    Args:
        project_filter: If provided, restrict to chunks whose source
            has this ``project_path``.
        block_type_filter: If provided, restrict to chunks with this
            ``block_type`` (e.g. ``'code'``, ``'text'``).
        language_filter: If provided, restrict to chunks whose JSONB
            ``metadata->>'language'`` matches this value.
        intent_filter: If provided, restrict to chunks whose JSONB
            ``metadata->>'intent'`` matches this value (e.g.
            ``'bug-fix'``, ``'new-feature'``).
        file_reference_filter: If provided, restrict to chunks whose
            JSONB ``metadata->'files'`` array contains this path.

    Returns:
        A ``(where_clause, params)`` tuple.  When no filters are active
        the clause is ``"TRUE"`` and params is an empty dict.
    """
    conditions: list[str] = []
    params: dict = {}

    if project_filter:
        conditions.append("ms.project_path = %(project_filter)s")
        params["project_filter"] = project_filter

    if block_type_filter:
        conditions.append("mc.block_type = %(block_type_filter)s")
        params["block_type_filter"] = block_type_filter

    if language_filter:
        conditions.append("mc.metadata ->> 'language' = %(language_filter)s")
        params["language_filter"] = language_filter

    if intent_filter:
        conditions.append("mc.metadata ->> 'intent' = %(intent_filter)s")
        params["intent_filter"] = intent_filter

    if file_reference_filter:
        conditions.append("mc.metadata -> 'files' ? %(file_reference_filter)s")
        params["file_reference_filter"] = file_reference_filter

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    return where_clause, params


# ------------------------------------------------------------------
# Hybrid search
# ------------------------------------------------------------------

def hybrid_search(
    query_embedding: list[float],
    query_text: str,
    top_k: int,
    db_conn: psycopg2.extensions.connection,
    rrf_k: int = 60,
    filter_clause: str = "TRUE",
    filter_params: dict | None = None,
) -> list[SearchResult]:
    """Run a hybrid RRF search combining semantic and keyword signals.

    The query is executed as a single SQL statement with two CTEs
    (``semantic`` and ``keyword``) joined via ``FULL OUTER JOIN``.
    The final score is computed using Reciprocal Rank Fusion::

        rrf_score = 1.0 / (rrf_k + sem_rank) + 1.0 / (rrf_k + kw_rank)

    Results where only one signal matched are still included; the
    missing signal contributes 0 to the RRF sum.

    Args:
        query_embedding: The query vector (dimension must match the
            table's embedding column).
        query_text: Natural-language query string for keyword matching.
        top_k: Maximum number of results to return.
        db_conn: An open psycopg2 connection.
        rrf_k: The RRF constant (default 60, matching the literature
            standard).  Higher values flatten the rank curve.
        filter_clause: A SQL WHERE fragment.  Applied inside *both*
            CTEs so filtering is consistent across signals.
        filter_params: Parameter dict referenced by *filter_clause*.

    Returns:
        A list of :class:`SearchResult` objects ordered by descending
        RRF score.  Each result's ``search_method`` is tagged as
        ``'hybrid'``, ``'semantic'``, or ``'keyword'`` depending on
        which CTEs contributed.
    """
    # Theoretical max RRF score: rank 1 in both signals = 2 / (k + 1)
    rrf_max = 2.0 / (rrf_k + 1)

    params: dict = {
        "query_vec": query_embedding,
        "query_text": query_text,
        "top_k": top_k,
        "rrf_k": rrf_k,
        "rrf_max": rrf_max,
    }
    if filter_params:
        params.update(filter_params)

    sql = f"""
        WITH semantic AS (
            SELECT
                mc.id,
                mc.content,
                mc.block_type,
                mc.metadata,
                ms.file_path   AS source_path,
                1 - (mc.embedding <=> %(query_vec)s::vector) AS similarity,
                ROW_NUMBER() OVER (
                    ORDER BY mc.embedding <=> %(query_vec)s::vector
                ) AS sem_rank
            FROM memory_chunks mc
            JOIN memory_sources ms ON ms.id = mc.source_id
            WHERE mc.embedding IS NOT NULL
              AND {filter_clause}
            LIMIT 20
        ),
        keyword AS (
            SELECT
                mc.id,
                mc.content,
                mc.block_type,
                mc.metadata,
                ms.file_path   AS source_path,
                ts_rank(
                    mc.content_tsv,
                    plainto_tsquery('english', %(query_text)s)
                ) AS kw_score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(
                        mc.content_tsv,
                        plainto_tsquery('english', %(query_text)s)
                    ) DESC
                ) AS kw_rank
            FROM memory_chunks mc
            JOIN memory_sources ms ON ms.id = mc.source_id
            WHERE mc.content_tsv @@ plainto_tsquery('english', %(query_text)s)
              AND {filter_clause}
            LIMIT 20
        )
        SELECT
            COALESCE(s.id, k.id)                    AS chunk_id,
            COALESCE(s.content, k.content)          AS content,
            COALESCE(s.block_type, k.block_type)    AS block_type,
            COALESCE(s.metadata, k.metadata)        AS metadata,
            COALESCE(s.source_path, k.source_path)  AS source_path,
            COALESCE(s.similarity, 0)               AS cosine_similarity,
            (
                COALESCE(1.0 / (%(rrf_k)s + s.sem_rank), 0)
                + COALESCE(1.0 / (%(rrf_k)s + k.kw_rank), 0)
            ) / %(rrf_max)s                         AS rrf_score,
            CASE
                WHEN s.id IS NOT NULL AND k.id IS NOT NULL THEN 'hybrid'
                WHEN s.id IS NOT NULL THEN 'semantic'
                ELSE 'keyword'
            END AS search_method
        FROM semantic s
        FULL OUTER JOIN keyword k ON s.id = k.id
        ORDER BY rrf_score DESC
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
        meta = dict(row["metadata"] or {})
        meta["cosine_similarity"] = float(row["cosine_similarity"])
        results.append(
            SearchResult(
                chunk_id=row["chunk_id"],
                content=row["content"],
                similarity=float(row["rrf_score"]),
                search_method=row["search_method"],
                block_type=row["block_type"],
                metadata=meta,
                source_path=row["source_path"],
            )
        )

    logger.debug(
        "hybrid_search returned %d results (top_k=%d, rrf_k=%d)",
        len(results),
        top_k,
        rrf_k,
    )
    return results
