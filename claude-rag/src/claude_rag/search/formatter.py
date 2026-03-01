"""Context formatter and deduplication for search results.

Packs ranked :class:`SearchResult` objects into a token-budgeted string
suitable for injection into an LLM prompt.  Uses ``tiktoken`` (cl100k_base)
for accurate token counting.
"""

from __future__ import annotations

import logging

import tiktoken

from claude_rag.search.semantic import SearchResult

logger = logging.getLogger(__name__)

# Lazy-initialised encoder (shared across calls).
_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Return the cached cl100k_base encoder, initialising on first call."""
    global _encoder  # noqa: PLW0603
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def _count_tokens(text: str) -> int:
    """Return the token count for *text* using the cl100k_base encoding.

    Args:
        text: The string to measure.

    Returns:
        Number of tokens.
    """
    return len(_get_encoder().encode(text))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* to at most *max_tokens* tokens.

    Args:
        text: The string to truncate.
        max_tokens: Maximum number of tokens to keep.

    Returns:
        The truncated string.  If the input is already within budget it
        is returned unchanged.
    """
    enc = _get_encoder()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])


# ------------------------------------------------------------------
# Deduplication
# ------------------------------------------------------------------

def deduplicate_results(
    results: list[SearchResult],
    threshold: float = 0.7,
) -> list[SearchResult]:
    """Remove near-duplicate results using Jaccard similarity on word sets.

    Iterates results in rank order (the input list is assumed to be
    sorted by descending relevance).  For each candidate, if its word-set
    Jaccard similarity with any already-accepted result exceeds
    *threshold*, it is dropped.

    Args:
        results: Search results sorted by relevance (best first).
        threshold: Jaccard similarity threshold above which a result is
            considered a duplicate.  Default 0.7.

    Returns:
        A filtered list preserving the original order, with
        near-duplicates removed.
    """
    if not results:
        return []

    accepted: list[SearchResult] = []
    accepted_word_sets: list[set[str]] = []

    for result in results:
        words = set(result.content.lower().split())
        is_duplicate = False
        for existing_words in accepted_word_sets:
            intersection = words & existing_words
            union = words | existing_words
            if union and (len(intersection) / len(union)) >= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            accepted.append(result)
            accepted_word_sets.append(words)

    removed = len(results) - len(accepted)
    if removed:
        logger.debug(
            "deduplicate_results removed %d/%d results (threshold=%.2f)",
            removed,
            len(results),
            threshold,
        )
    return accepted


# ------------------------------------------------------------------
# Context formatting
# ------------------------------------------------------------------

_SEPARATOR = "---"

_RESULT_TEMPLATE = (
    "[Source: {source_path} | Type: {block_type} | Relevance: {similarity:.3f}]\n"
    "{content}\n"
    "{separator}"
)


def format_context(
    results: list[SearchResult],
    token_budget: int = 4096,
) -> tuple[str, int]:
    """Pack search results into a token-budgeted context string.

    Iterates results in rank order (the caller is responsible for sorting,
    though all search functions already return results sorted).  Each result
    is formatted as::

        [Source: <source_path> | Type: <block_type> | Relevance: <similarity:.3f>]
        <content>
        ---

    If appending a full result would exceed the remaining token budget,
    its content is truncated to fit.  If even the header plus a minimal
    truncated content would not fit, the result is skipped.

    Args:
        results: Search results to format, ordered by descending relevance.
        token_budget: Maximum number of tokens for the returned string.

    Returns:
        A ``(context_string, tokens_used)`` tuple.
    """
    if not results:
        return "", 0

    parts: list[str] = []
    tokens_used = 0

    for result in results:
        source = result.source_path or "unknown"
        block_type = result.block_type or "unknown"

        # Build the header and separator so we know their cost.
        header = f"[Source: {source} | Type: {block_type} | Relevance: {result.similarity:.3f}]"
        overhead = _count_tokens(header + "\n" + "\n" + _SEPARATOR)
        remaining = token_budget - tokens_used

        if overhead >= remaining:
            # Not enough room for even the header; skip this result.
            continue

        content_budget = remaining - overhead
        content = result.content

        content_tokens = _count_tokens(content)
        if content_tokens > content_budget:
            content = _truncate_to_tokens(content, content_budget)
            # Recount after truncation to avoid off-by-one from decode rounding.
            content_tokens = _count_tokens(content)

        block = _RESULT_TEMPLATE.format(
            source_path=source,
            block_type=block_type,
            similarity=result.similarity,
            content=content,
            separator=_SEPARATOR,
        )

        block_tokens = _count_tokens(block)

        if tokens_used + block_tokens > token_budget:
            # Safety net: if the assembled block is still over budget after
            # truncation (possible due to encoding edge-cases), skip.
            continue

        parts.append(block)
        tokens_used += block_tokens

    context = "\n".join(parts)
    logger.debug(
        "format_context packed %d/%d results into ~%d tokens (budget=%d)",
        len(parts),
        len(results),
        tokens_used,
        token_budget,
    )
    return context, tokens_used
