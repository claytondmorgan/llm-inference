"""Comprehensive deduplication tests — search-level, hook-level, and dashboard metrics."""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.search.formatter import deduplicate_results
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


def _jaccard(words_a: set[str], words_b: set[str]) -> float:
    """Compute Jaccard similarity between two word sets."""
    if not words_a and not words_b:
        return 1.0
    union = words_a | words_b
    if not union:
        return 0.0
    return len(words_a & words_b) / len(union)


def _make_content_with_jaccard(
    base_words: list[str],
    target_jaccard: float,
    extra_pool: list[str] | None = None,
) -> tuple[str, str]:
    """Build two strings whose word-set Jaccard similarity equals *target_jaccard*.

    Strategy: keep *n* shared words from *base_words*, then pad each side with
    unique words until Jaccard = |shared| / |union| equals the target.

    Returns (content_a, content_b).
    """
    if extra_pool is None:
        extra_pool = [f"extra{i}" for i in range(100)]

    n = len(base_words)
    # We want: jaccard = shared / (shared + unique_a + unique_b)
    # Simplest: content_a = shared + unique_a, content_b = shared + unique_b
    # with unique_a = unique_b = k.
    # jaccard = n / (n + 2k)  =>  k = n * (1 - j) / (2 * j)
    if target_jaccard >= 1.0:
        return " ".join(base_words), " ".join(base_words)
    if target_jaccard <= 0.0:
        a_words = extra_pool[:n]
        b_words = extra_pool[n : 2 * n]
        return " ".join(a_words), " ".join(b_words)

    k = round(n * (1 - target_jaccard) / (2 * target_jaccard))
    if k < 1:
        k = 1
    # Recalculate actual jaccard after rounding
    unique_a = extra_pool[:k]
    unique_b = extra_pool[k : 2 * k]
    content_a = " ".join(base_words + unique_a)
    content_b = " ".join(base_words + unique_b)
    return content_a, content_b


# ---------------------------------------------------------------------------
# TestSearchResultDedupThresholds
# ---------------------------------------------------------------------------


class TestSearchResultDedupThresholds:
    """Boundary behavior of the Jaccard similarity threshold."""

    def test_jaccard_exactly_at_threshold_is_duplicate(self) -> None:
        """Jaccard = 0.7 exactly -> >= threshold -> duplicate."""
        # 14 shared words, 3 unique to each side -> union=20, jaccard=14/20=0.7
        shared = ["word" + str(i) for i in range(14)]
        content_a = " ".join(shared + ["unqa1", "unqa2", "unqa3"])
        content_b = " ".join(shared + ["unqb1", "unqb2", "unqb3"])

        # Verify our constructed Jaccard
        words_a = set(content_a.lower().split())
        words_b = set(content_b.lower().split())
        assert _jaccard(words_a, words_b) == pytest.approx(0.7, abs=1e-9)

        r1 = _make_result(chunk_id=1, content=content_a)
        r2 = _make_result(chunk_id=2, content=content_b)
        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 1
        assert results[0].chunk_id == 1

    def test_jaccard_below_threshold_is_kept(self) -> None:
        """Jaccard = 0.6 -> below 0.7 -> both survive."""
        # 6 shared, 2 unique to each side -> union=10, jaccard=6/10=0.6
        shared = ["word" + str(i) for i in range(6)]
        content_a = " ".join(shared + ["ua1", "ua2"])
        content_b = " ".join(shared + ["ub1", "ub2"])

        words_a = set(content_a.lower().split())
        words_b = set(content_b.lower().split())
        assert _jaccard(words_a, words_b) == pytest.approx(0.6, abs=1e-9)

        r1 = _make_result(chunk_id=1, content=content_a)
        r2 = _make_result(chunk_id=2, content=content_b)
        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 2

    def test_jaccard_above_threshold_is_duplicate(self) -> None:
        """Jaccard > 0.7 -> duplicate."""
        # 5 shared, 1 unique each -> union=7, jaccard=5/7~=0.714
        shared = ["word" + str(i) for i in range(5)]
        content_a = " ".join(shared + ["xa1"])
        content_b = " ".join(shared + ["xb1"])

        words_a = set(content_a.lower().split())
        words_b = set(content_b.lower().split())
        j = _jaccard(words_a, words_b)
        assert j > 0.7

        r1 = _make_result(chunk_id=1, content=content_a)
        r2 = _make_result(chunk_id=2, content=content_b)
        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 1

    def test_threshold_zero_deduplicates_all_nonempty(self) -> None:
        """threshold=0.0 means any non-empty overlap triggers dedup.

        With threshold=0.0, >= 0.0 is always true for non-empty sets,
        so only the first result survives.
        """
        r1 = _make_result(chunk_id=1, content="alpha beta gamma")
        r2 = _make_result(chunk_id=2, content="delta epsilon zeta")
        r3 = _make_result(chunk_id=3, content="eta theta iota")
        results = deduplicate_results([r1, r2, r3], threshold=0.0)
        # Jaccard of disjoint non-empty sets = 0.0, which is >= 0.0
        assert len(results) == 1
        assert results[0].chunk_id == 1

    def test_threshold_one_only_removes_identical(self) -> None:
        """threshold=1.0 means only exact word-set matches are removed."""
        r1 = _make_result(chunk_id=1, content="alpha beta gamma")
        r2 = _make_result(chunk_id=2, content="alpha beta gamma delta")  # superset
        r3 = _make_result(chunk_id=3, content="gamma beta alpha")  # same set, different order
        results = deduplicate_results([r1, r2, r3], threshold=1.0)
        # r1 and r3 have identical word sets -> r3 dropped
        # r2 has a different word set -> kept
        assert len(results) == 2
        ids = {r.chunk_id for r in results}
        assert ids == {1, 2}


# ---------------------------------------------------------------------------
# TestSearchResultDedupContentVsPath
# ---------------------------------------------------------------------------


class TestSearchResultDedupContentVsPath:
    """Dedup is content-based, not path-based."""

    def test_same_content_different_paths_deduplicates(self) -> None:
        """Identical content from different files -> deduped to 1."""
        content = "the quick brown fox jumps over the lazy dog"
        r1 = _make_result(chunk_id=1, content=content, source_path="/a.py")
        r2 = _make_result(chunk_id=2, content=content, source_path="/b.py")
        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 1

    def test_different_content_same_path_kept(self) -> None:
        """Different content from the same source -> both kept."""
        r1 = _make_result(
            chunk_id=1, content="database connection pooling strategies", source_path="/shared.py"
        )
        r2 = _make_result(
            chunk_id=2, content="user authentication with JWT tokens", source_path="/shared.py"
        )
        results = deduplicate_results([r1, r2], threshold=0.7)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# TestSearchResultDedupLargeBatch
# ---------------------------------------------------------------------------


class TestSearchResultDedupLargeBatch:
    """Stress tests with 25+ results."""

    def test_large_batch_mixed_duplicates(self) -> None:
        """2 clusters of 5 dupes each + 15 unique -> 17 results."""
        results: list[SearchResult] = []
        cid = 1

        # Cluster A: 5 near-identical results
        base_a = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        for i in range(5):
            results.append(_make_result(chunk_id=cid, content=base_a, similarity=0.9 - i * 0.01))
            cid += 1

        # Cluster B: 5 near-identical results
        base_b = "lambda mu nu xi omicron pi rho sigma tau upsilon"
        for i in range(5):
            results.append(_make_result(chunk_id=cid, content=base_b, similarity=0.85 - i * 0.01))
            cid += 1

        # 15 unique results
        for i in range(15):
            unique_content = f"unique_topic_{i} " + " ".join(f"word{i}_{j}" for j in range(8))
            results.append(_make_result(chunk_id=cid, content=unique_content, similarity=0.7))
            cid += 1

        deduped = deduplicate_results(results, threshold=0.7)
        # Each cluster collapses to 1, plus 15 unique = 17
        assert len(deduped) == 17

    def test_all_identical_reduces_to_one(self) -> None:
        """20 identical results -> 1."""
        content = "identical content repeated many times across chunks"
        results = [
            _make_result(chunk_id=i, content=content) for i in range(20)
        ]
        deduped = deduplicate_results(results, threshold=0.7)
        assert len(deduped) == 1
        assert deduped[0].chunk_id == 0  # first one survives

    def test_dedup_across_search_methods(self) -> None:
        """Semantic + keyword dupes with same content are still deduped."""
        content = "postgres pgvector cosine similarity search optimization"
        r1 = _make_result(chunk_id=1, content=content, search_method="semantic")
        r2 = _make_result(chunk_id=2, content=content, search_method="keyword")
        r3 = _make_result(chunk_id=3, content="completely different content here", search_method="semantic")

        deduped = deduplicate_results([r1, r2, r3], threshold=0.7)
        assert len(deduped) == 2
        ids = {r.chunk_id for r in deduped}
        assert 1 in ids  # semantic version kept (first)
        assert 3 in ids  # unique result kept


# ---------------------------------------------------------------------------
# TestHookEventDedup
# ---------------------------------------------------------------------------


class TestHookEventDedup:
    """Hook-level dedup in post_tool_use.py using content hash + TTL cache."""

    def setup_method(self) -> None:
        """Clear the dedup cache before each test."""
        from claude_rag.hooks import post_tool_use
        post_tool_use._dedup_cache.clear()

    def test_same_file_same_hash_within_ttl_is_dedup(self) -> None:
        """Second Read of unchanged file within TTL -> dedup=True."""
        from claude_rag.hooks.post_tool_use import _check_dedup_cache

        content_hash = hashlib.sha256(b"file content here").hexdigest()
        path = "/project/src/main.py"

        # First call: not a dup
        assert _check_dedup_cache(path, content_hash, ttl=30.0) is False
        # Second call: same path + hash within TTL -> dup
        assert _check_dedup_cache(path, content_hash, ttl=30.0) is True

    def test_same_file_changed_content_not_dedup(self) -> None:
        """File changed between reads -> not a dup."""
        from claude_rag.hooks.post_tool_use import _check_dedup_cache

        path = "/project/src/main.py"
        hash_v1 = hashlib.sha256(b"version 1 content").hexdigest()
        hash_v2 = hashlib.sha256(b"version 2 content").hexdigest()

        assert _check_dedup_cache(path, hash_v1, ttl=30.0) is False
        assert _check_dedup_cache(path, hash_v2, ttl=30.0) is False

    def test_different_files_not_dedup(self) -> None:
        """Two different files -> both processed, no dedup."""
        from claude_rag.hooks.post_tool_use import _check_dedup_cache

        content_hash = hashlib.sha256(b"same content").hexdigest()

        assert _check_dedup_cache("/a.py", content_hash, ttl=30.0) is False
        assert _check_dedup_cache("/b.py", content_hash, ttl=30.0) is False

    def test_cache_expires_after_ttl(self) -> None:
        """After TTL expires, same file + hash is no longer a dup."""
        from claude_rag.hooks.post_tool_use import _check_dedup_cache

        content_hash = hashlib.sha256(b"content").hexdigest()
        path = "/project/README.md"

        # First call at t=1000
        with patch("claude_rag.hooks.post_tool_use.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            mock_time.strftime = time.strftime
            mock_time.time = time.time
            assert _check_dedup_cache(path, content_hash, ttl=30.0) is False

        # Second call at t=1031 (past TTL of 30s)
        with patch("claude_rag.hooks.post_tool_use.time") as mock_time:
            mock_time.monotonic.return_value = 1031.0
            mock_time.strftime = time.strftime
            mock_time.time = time.time
            assert _check_dedup_cache(path, content_hash, ttl=30.0) is False


# ---------------------------------------------------------------------------
# TestDashboardDedupMetrics
# ---------------------------------------------------------------------------


class TestDashboardDedupMetrics:
    """StatsCollector processes dedup events correctly."""

    def _make_collector(self) -> "StatsCollector":
        """Create a StatsCollector with IO operations stubbed out."""
        from claude_rag.monitoring.stats_server import StatsCollector

        with (
            patch.object(StatsCollector, "_start_log_tailer"),
            patch.object(StatsCollector, "_load_persisted_counters"),
        ):
            return StatsCollector()

    def test_dedup_true_increments_counter(self) -> None:
        collector = self._make_collector()
        collector._process_event({"type": "hook_read", "dedup": True, "session_id": "s1"})
        assert collector._hook_counters["dedup_hits"] == 1

    def test_dedup_false_does_not_increment(self) -> None:
        collector = self._make_collector()
        collector._process_event({"type": "hook_read", "dedup": False, "session_id": "s1"})
        assert collector._hook_counters["dedup_hits"] == 0

    def test_dedup_missing_does_not_increment(self) -> None:
        collector = self._make_collector()
        collector._process_event({"type": "hook_read", "session_id": "s1"})
        assert collector._hook_counters["dedup_hits"] == 0

    def test_multiple_dedup_events_accumulate(self) -> None:
        collector = self._make_collector()

        # 5 dedup events
        for i in range(5):
            collector._process_event({"type": "hook_read", "dedup": True, "session_id": f"s{i}"})

        # 3 non-dedup events
        for i in range(3):
            collector._process_event({"type": "hook_read", "dedup": False, "session_id": f"s{i+10}"})

        assert collector._hook_counters["dedup_hits"] == 5
        assert collector._hook_counters["hooks_read"] == 8
        assert collector._hook_counters["hooks_total"] == 8
