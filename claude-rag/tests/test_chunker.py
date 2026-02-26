"""Tests for the Claude RAG chunker module (claude_rag.ingestion.chunker)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.ingestion.parser import ParsedBlock, parse_claude_md
from claude_rag.ingestion.chunker import Chunk, chunk_blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_block(content: str, block_type: str = "text") -> ParsedBlock:
    """Create a minimal ParsedBlock for testing."""
    return ParsedBlock(content=content, block_type=block_type, metadata={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChunkBlocksBasic:
    """Parse a sample, chunk it, and verify chunks have content."""

    def test_chunk_blocks_basic(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))
        chunks = chunk_blocks(blocks, chunk_size=512, overlap=50)

        assert len(chunks) >= 1, "Should produce at least one chunk"

        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, Chunk)
            assert chunk.content, f"Chunk {i} has empty content"
            assert chunk.index == i, (
                f"Chunk index mismatch: expected {i}, got {chunk.index}"
            )
            assert chunk.metadata.get("token_count", 0) > 0, (
                f"Chunk {i} has no token_count metadata"
            )
            assert len(chunk.metadata.get("block_types", [])) > 0, (
                f"Chunk {i} has no block_types metadata"
            )

    def test_chunk_blocks_source_blocks_populated(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))
        chunks = chunk_blocks(blocks, chunk_size=512, overlap=50)

        for chunk in chunks:
            assert len(chunk.source_blocks) >= 1, (
                f"Chunk {chunk.index} has no source_blocks"
            )
            for idx in chunk.source_blocks:
                assert 0 <= idx < len(blocks), (
                    f"source_block index {idx} out of range"
                )

    def test_empty_blocks_produce_no_chunks(self) -> None:
        chunks = chunk_blocks([], chunk_size=512, overlap=50)
        assert chunks == []


class TestChunkBlocksCodeNeverSplit:
    """Verify that code blocks are never split across chunks."""

    def test_chunk_blocks_code_never_split(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        # Use a very small chunk_size so text blocks would be split,
        # but code blocks should remain intact.
        chunks = chunk_blocks(blocks, chunk_size=20, overlap=5)

        # Find the original code block content(s)
        original_code_contents = [
            b.content for b in blocks if b.block_type == "code"
        ]
        assert len(original_code_contents) >= 1, (
            "Sample should contain at least one code block"
        )

        # Each code block must appear in exactly one chunk, intact
        for code_content in original_code_contents:
            containing_chunks = [
                c for c in chunks if code_content in c.content
            ]
            assert len(containing_chunks) == 1, (
                f"Code block should appear in exactly 1 chunk, "
                f"found in {len(containing_chunks)}"
            )

    def test_large_code_block_stays_whole(self) -> None:
        """A code block bigger than chunk_size still emits as a single chunk."""
        big_code = "x = 1\n" * 200  # ~200 lines of code
        blocks = [_make_block(big_code, block_type="code")]

        chunks = chunk_blocks(blocks, chunk_size=10, overlap=2)

        assert len(chunks) == 1, (
            f"Large code block should produce 1 chunk, got {len(chunks)}"
        )
        assert big_code in chunks[0].content


class TestChunkBlocksOverlap:
    """Verify that chunks after the first have overlap from the previous chunk."""

    def test_chunk_blocks_overlap(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        # Use a small chunk size to force multiple chunks, with a non-zero overlap
        chunks = chunk_blocks(blocks, chunk_size=50, overlap=10)

        if len(chunks) < 2:
            # If the sample is too small to produce multiple non-code chunks,
            # build a synthetic scenario
            long_text = (
                "The quick brown fox jumps over the lazy dog. " * 50
            )
            blocks = [_make_block(long_text)]
            chunks = chunk_blocks(blocks, chunk_size=50, overlap=10)

        assert len(chunks) >= 2, "Need at least 2 chunks to test overlap"

        # For every chunk after the first, the beginning should contain
        # text that also appeared at the end of the previous chunk.
        for i in range(1, len(chunks)):
            prev_content = chunks[i - 1].content
            curr_content = chunks[i].content

            # The overlap prefix is taken from the END of the previous chunk.
            # So the first part of the current chunk's content should share
            # some substring with the end of the previous chunk.
            # We check that the current chunk starts with text found in prev.
            curr_start = curr_content[:200]  # first ~200 chars
            prev_end = prev_content[-200:]    # last ~200 chars

            # There must be a non-trivial shared substring
            overlap_found = any(
                word in prev_end
                for word in curr_start.split()[:5]
                if len(word) > 2
            )
            assert overlap_found, (
                f"Chunk {i} does not appear to overlap with chunk {i - 1}"
            )


class TestChunkBlocksSmallInput:
    """A single small block should produce a single chunk."""

    def test_chunk_blocks_small_input(self) -> None:
        blocks = [_make_block("Hello, world!")]
        chunks = chunk_blocks(blocks, chunk_size=512, overlap=50)

        assert len(chunks) == 1
        assert "Hello, world!" in chunks[0].content
        assert chunks[0].index == 0
        assert chunks[0].metadata["token_count"] > 0

    def test_single_heading_block(self) -> None:
        blocks = [_make_block("Introduction", block_type="heading")]
        chunks = chunk_blocks(blocks, chunk_size=512, overlap=50)

        assert len(chunks) == 1
        assert "Introduction" in chunks[0].content
