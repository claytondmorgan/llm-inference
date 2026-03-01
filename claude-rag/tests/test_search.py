"""Tests for the Claude RAG search module (filtering, dedup, formatting)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.search.hybrid import build_filters
from claude_rag.search.formatter import deduplicate_results, format_context
from claude_rag.search.semantic import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    chunk_id: int = 1,
    content: str = "default content",
    similarity: float = 0.9,
    search_method: str = "semantic",
    block_type: str = "text",
    source_path: str = "/project/CLAUDE.md",
) -> SearchResult:
    """Build a minimal SearchResult for testing."""
    return SearchResult(
        chunk_id=chunk_id,
        content=content,
        similarity=similarity,
        search_method=search_method,
        block_type=block_type,
        metadata={},
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# build_filters
# ---------------------------------------------------------------------------


class TestBuildFiltersEmpty:
    """No filters should produce 'TRUE' and an empty param dict."""

    def test_build_filters_empty(self) -> None:
        clause, params = build_filters()
        assert clause == "TRUE"
        assert params == {}

    def test_build_filters_all_none_explicit(self) -> None:
        clause, params = build_filters(
            project_filter=None,
            block_type_filter=None,
            language_filter=None,
        )
        assert clause == "TRUE"
        assert params == {}


class TestBuildFiltersProject:
    """Project filter should produce the correct clause and param."""

    def test_build_filters_project(self) -> None:
        clause, params = build_filters(project_filter="/home/user/myproject")
        assert "ms.project_path" in clause
        assert "%(project_filter)s" in clause
        assert params["project_filter"] == "/home/user/myproject"

    def test_build_filters_block_type(self) -> None:
        clause, params = build_filters(block_type_filter="code")
        assert "mc.block_type" in clause
        assert params["block_type_filter"] == "code"

    def test_build_filters_language(self) -> None:
        clause, params = build_filters(language_filter="python")
        assert "language" in clause
        assert params["language_filter"] == "python"

    def test_build_filters_combined(self) -> None:
        clause, params = build_filters(
            project_filter="/myproject",
            block_type_filter="code",
            language_filter="python",
        )
        # All three conditions joined by AND
        assert "AND" in clause
        assert "ms.project_path" in clause
        assert "mc.block_type" in clause
        assert "language" in clause
        assert len(params) == 3


# ---------------------------------------------------------------------------
# deduplicate_results
# ---------------------------------------------------------------------------


class TestDeduplicateResults:
    """Similar results should get deduped based on Jaccard similarity."""

    def test_deduplicate_results_removes_near_duplicates(self) -> None:
        r1 = _make_result(chunk_id=1, content="the quick brown fox jumps over the lazy dog")
        r2 = _make_result(chunk_id=2, content="the quick brown fox leaps over the lazy dog")
        r3 = _make_result(chunk_id=3, content="completely different content about databases")

        results = deduplicate_results([r1, r2, r3], threshold=0.7)

        # r1 and r2 are very similar; one should be dropped
        assert len(results) <= 2
        # r3 is unique and should survive
        ids = {r.chunk_id for r in results}
        assert 3 in ids

    def test_deduplicate_results_keeps_distinct(self) -> None:
        r1 = _make_result(chunk_id=1, content="Python type hints improve code quality")
        r2 = _make_result(chunk_id=2, content="PostgreSQL pgvector enables semantic search")
        r3 = _make_result(chunk_id=3, content="Docker containers simplify deployment")

        results = deduplicate_results([r1, r2, r3], threshold=0.7)
        assert len(results) == 3

    def test_deduplicate_results_empty(self) -> None:
        results = deduplicate_results([], threshold=0.7)
        assert results == []

    def test_deduplicate_results_single(self) -> None:
        r1 = _make_result(chunk_id=1, content="only one result")
        results = deduplicate_results([r1])
        assert len(results) == 1
        assert results[0].chunk_id == 1

    def test_deduplicate_results_preserves_order(self) -> None:
        """The first (highest-ranked) duplicate should be kept, not the second."""
        r1 = _make_result(chunk_id=1, content="alpha beta gamma delta epsilon", similarity=0.95)
        r2 = _make_result(chunk_id=2, content="alpha beta gamma delta epsilon", similarity=0.80)

        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 1
        assert results[0].chunk_id == 1  # the first (higher relevance) survives


# ---------------------------------------------------------------------------
# format_context
# ---------------------------------------------------------------------------


class TestFormatContextBudget:
    """Context formatting should respect the token budget."""

    def test_format_context_budget_basic(self) -> None:
        results = [
            _make_result(chunk_id=i, content=f"Content for result number {i}.")
            for i in range(5)
        ]

        context, tokens_used = format_context(results, token_budget=4096)
        assert isinstance(context, str)
        assert len(context) > 0
        assert tokens_used > 0

        # Each result should have its header
        for r in results:
            if r.source_path in context:
                assert "Relevance:" in context

    def test_format_context_budget_limits_output(self) -> None:
        """With a tiny budget, not all results should fit."""
        results = [
            _make_result(
                chunk_id=i,
                content="A " * 200 + f"end of result {i}.",
            )
            for i in range(10)
        ]

        # A very small budget should truncate
        context, _ = format_context(results, token_budget=100)

        # Not all 10 results should appear in full
        end_markers_found = sum(
            1 for i in range(10) if f"end of result {i}" in context
        )
        assert end_markers_found < 10, (
            "Token budget should prevent all results from appearing in full"
        )

    def test_format_context_empty_results(self) -> None:
        context, tokens_used = format_context([], token_budget=4096)
        assert context == ""
        assert tokens_used == 0

    def test_format_context_contains_source_and_type(self) -> None:
        r = _make_result(
            chunk_id=1,
            content="Test content here.",
            source_path="/project/CLAUDE.md",
            block_type="code",
            similarity=0.850,
        )
        context, _ = format_context([r], token_budget=4096)

        assert "/project/CLAUDE.md" in context
        assert "code" in context
        assert "0.850" in context
        assert "Test content here." in context

    def test_format_context_separator(self) -> None:
        """Each formatted result should end with the --- separator."""
        results = [
            _make_result(chunk_id=1, content="First result."),
            _make_result(chunk_id=2, content="Second result."),
        ]
        context, _ = format_context(results, token_budget=4096)
        assert context.count("---") >= 1

    def test_format_context_large_budget_includes_all(self) -> None:
        """With a huge budget, all results should be included."""
        results = [
            _make_result(chunk_id=i, content=f"Short content {i}.")
            for i in range(3)
        ]
        context, _ = format_context(results, token_budget=100_000)

        for i in range(3):
            assert f"Short content {i}." in context
