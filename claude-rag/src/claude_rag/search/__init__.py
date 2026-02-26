"""Search layer for the Claude Code RAG system.

Public API re-exports for convenient importing::

    from claude_rag.search import (
        SearchResult,
        semantic_search,
        keyword_search,
        hybrid_search,
        build_filters,
        format_context,
        deduplicate_results,
    )
"""

from claude_rag.search.semantic import SearchResult, semantic_search
from claude_rag.search.keyword import keyword_search
from claude_rag.search.hybrid import build_filters, hybrid_search
from claude_rag.search.formatter import deduplicate_results, format_context

__all__ = [
    "SearchResult",
    "semantic_search",
    "keyword_search",
    "hybrid_search",
    "build_filters",
    "format_context",
    "deduplicate_results",
]
