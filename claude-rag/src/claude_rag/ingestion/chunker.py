"""Token-aware text chunker for the Claude Code RAG system.

Splits a sequence of ``ParsedBlock`` objects (produced by ``parser.py``)
into overlapping ``Chunk`` objects suitable for embedding and retrieval.
Token counting uses the **cl100k_base** encoding from ``tiktoken``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import tiktoken

from claude_rag.ingestion.parser import ParsedBlock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level tokenizer
# ---------------------------------------------------------------------------

_ENCODING = tiktoken.get_encoding("cl100k_base")

# Sentence-boundary regex — splits after `.`, `!`, or `?` followed by
# whitespace or end-of-string, but avoids splitting on common abbreviations.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A token-bounded text chunk ready for embedding.

    Attributes:
        content: The chunk text (may span several source blocks).
        index: Zero-based position of this chunk in the output sequence.
        source_blocks: Indices (into the input ``blocks`` list) of every
            ``ParsedBlock`` that contributed content to this chunk.
        metadata: Arbitrary extra information.  The chunker populates:

            * ``token_count`` (int) — number of cl100k_base tokens.
            * ``block_types`` (list[str]) — deduplicated block types present.
    """

    content: str
    index: int
    source_blocks: list[int] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _token_len(text: str) -> int:
    """Return the cl100k_base token count for *text*.

    Args:
        text: Arbitrary string.

    Returns:
        Number of tokens.
    """
    return len(_ENCODING.encode(text))


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences using a simple regex heuristic.

    Args:
        text: A plain-text paragraph or block.

    Returns:
        List of sentence strings (whitespace-trimmed, non-empty).
    """
    parts = _SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _build_overlap_prefix(prev_content: str, overlap: int) -> str:
    """Extract up to *overlap* tokens from the **end** of *prev_content*.

    The function decodes whole tokens so the overlap text is always valid
    UTF-8.

    Args:
        prev_content: Full text of the previous chunk.
        overlap: Target overlap size in tokens.

    Returns:
        A string whose token count is at most *overlap*.  May be empty if
        *overlap* is zero or *prev_content* is empty.
    """
    if overlap <= 0 or not prev_content:
        return ""

    tokens = _ENCODING.encode(prev_content)
    if len(tokens) <= overlap:
        return prev_content

    overlap_tokens = tokens[-overlap:]
    return _ENCODING.decode(overlap_tokens)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_blocks(
    blocks: list[ParsedBlock],
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[Chunk]:
    """Split parsed blocks into token-bounded, overlapping chunks.

    Chunking rules:

    1. **Code blocks are never split.**  A code block is emitted as a single
       chunk even if it exceeds *chunk_size*.
    2. Blocks are accumulated until adding the next block would exceed
       *chunk_size*; at that point the accumulated text is emitted as a
       chunk.
    3. If a single non-code block exceeds *chunk_size* on its own it is
       split at sentence boundaries so that each resulting piece fits within
       *chunk_size*.
    4. Each chunk (except the first) is prefixed with up to *overlap*
       tokens copied from the end of the previous chunk to provide
       retrieval context.

    Args:
        blocks: Ordered ``ParsedBlock`` list from the parser.
        chunk_size: Maximum number of cl100k_base tokens per chunk
            (excluding the overlap prefix).
        overlap: Number of tokens from the previous chunk to prepend to the
            next chunk.

    Returns:
        Ordered list of ``Chunk`` objects covering all input blocks.
    """
    if not blocks:
        return []

    chunks: list[Chunk] = []
    chunk_index = 0

    # Accumulator state
    acc_text: list[str] = []
    acc_tokens: int = 0
    acc_block_indices: list[int] = []
    acc_types: set[str] = set()

    # Overlap carried from the previously emitted chunk
    pending_overlap: str = ""

    def _emit(content_parts: list[str], block_indices: list[int], types: set[str]) -> None:
        """Create a ``Chunk`` from the accumulated parts and reset state."""
        nonlocal chunk_index, pending_overlap

        raw = "\n\n".join(content_parts)

        # Prepend overlap from the previous chunk
        if pending_overlap and chunks:
            full_text = pending_overlap + "\n\n" + raw
        else:
            full_text = raw

        tok_count = _token_len(full_text)
        chunk = Chunk(
            content=full_text,
            index=chunk_index,
            source_blocks=sorted(set(block_indices)),
            metadata={
                "token_count": tok_count,
                "block_types": sorted(types),
            },
        )
        chunks.append(chunk)
        chunk_index += 1

        # Prepare overlap for the *next* chunk
        pending_overlap = _build_overlap_prefix(full_text, overlap)

    def _flush_accumulator() -> None:
        """Emit whatever is in the accumulator."""
        nonlocal acc_text, acc_tokens, acc_block_indices, acc_types
        if acc_text:
            _emit(acc_text, acc_block_indices, acc_types)
            acc_text = []
            acc_tokens = 0
            acc_block_indices = []
            acc_types = set()

    for block_idx, block in enumerate(blocks):
        block_tokens = _token_len(block.content)

        # ---- Code blocks: never split, always emit standalone ----------
        if block.block_type == "code":
            _flush_accumulator()
            _emit([block.content], [block_idx], {block.block_type})
            continue

        # ---- Oversized non-code block: split at sentence boundaries ----
        if block_tokens > chunk_size:
            _flush_accumulator()
            sentences = _split_sentences(block.content)

            sent_acc: list[str] = []
            sent_tokens: int = 0

            for sentence in sentences:
                s_tok = _token_len(sentence)

                if sent_acc and sent_tokens + s_tok > chunk_size:
                    # Emit what we have so far
                    _emit(
                        [" ".join(sent_acc)],
                        [block_idx],
                        {block.block_type},
                    )
                    sent_acc = []
                    sent_tokens = 0

                sent_acc.append(sentence)
                sent_tokens += s_tok

            # Leftover sentences
            if sent_acc:
                _emit(
                    [" ".join(sent_acc)],
                    [block_idx],
                    {block.block_type},
                )
            continue

        # ---- Normal-sized block: try to accumulate ---------------------
        if acc_tokens + block_tokens > chunk_size and acc_text:
            _flush_accumulator()

        if not acc_text:
            acc_tokens = 0

        acc_text.append(block.content)
        acc_tokens += block_tokens
        acc_block_indices.append(block_idx)
        acc_types.add(block.block_type)

    # Emit any remaining accumulator content
    _flush_accumulator()

    logger.debug(
        "Chunked %d blocks into %d chunks (size=%d, overlap=%d)",
        len(blocks),
        len(chunks),
        chunk_size,
        overlap,
    )
    return chunks
