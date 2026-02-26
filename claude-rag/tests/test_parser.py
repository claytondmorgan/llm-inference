"""Tests for the Claude RAG parser module (claude_rag.ingestion.parser)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.ingestion.parser import ParsedBlock, parse_claude_md, parse_session_log


# ---------------------------------------------------------------------------
# CLAUDE.md parsing
# ---------------------------------------------------------------------------


class TestParseCaudeMdHeadings:
    """Verify that heading blocks are detected with correct heading_level."""

    def test_parse_claude_md_headings(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        heading_blocks = [b for b in blocks if b.block_type == "heading"]

        # The sample has: # Project Instructions, ## Architecture, ## Code Style,
        # ## Key Decisions, ## Database, ## Recent Changes
        assert len(heading_blocks) >= 4, (
            f"Expected at least 4 headings, got {len(heading_blocks)}"
        )

        # Check the top-level heading
        top_heading = heading_blocks[0]
        assert top_heading.content == "Project Instructions"
        assert top_heading.metadata["heading_level"] == 1

        # All ##-level headings should have heading_level == 2
        sub_headings = [h for h in heading_blocks if h.metadata["heading_level"] == 2]
        assert len(sub_headings) >= 3
        sub_titles = [h.content for h in sub_headings]
        assert "Architecture" in sub_titles
        assert "Code Style" in sub_titles
        assert "Key Decisions" in sub_titles

    def test_heading_line_metadata(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))
        heading_blocks = [b for b in blocks if b.block_type == "heading"]

        for h in heading_blocks:
            assert "line_start" in h.metadata
            assert "line_end" in h.metadata
            # Headings are single-line, so start == end
            assert h.metadata["line_start"] == h.metadata["line_end"]


class TestParseCaudeMdCodeBlocks:
    """Verify that code blocks are detected with language metadata."""

    def test_parse_claude_md_code_blocks(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        code_blocks = [b for b in blocks if b.block_type == "code"]

        # The sample has one ```python block
        assert len(code_blocks) >= 1, (
            f"Expected at least 1 code block, got {len(code_blocks)}"
        )

        python_block = code_blocks[0]
        assert python_block.metadata["language"] == "python"
        assert "def get_embedding" in python_block.content
        assert "SentenceTransformer" in python_block.content

    def test_code_block_does_not_include_fences(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))
        code_blocks = [b for b in blocks if b.block_type == "code"]

        for cb in code_blocks:
            # The opening/closing ``` should NOT appear in the content
            lines = cb.content.splitlines()
            for line in lines:
                assert line.strip() != "```", (
                    "Code block content should not include the fence markers"
                )


class TestParseCaudeMdInstructions:
    """Verify that instruction blocks (bullet lists with imperatives) are detected."""

    def test_parse_claude_md_instructions(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        instruction_blocks = [b for b in blocks if b.block_type == "instruction"]

        # The "Code Style" section has imperative bullets:
        #   - Use type hints on all functions
        #   - Pytest for tests
        # At least one block should be classified as instruction
        assert len(instruction_blocks) >= 1, (
            f"Expected at least 1 instruction block, got {len(instruction_blocks)}"
        )

        # At least one instruction block should contain "Use type hints"
        all_instruction_text = " ".join(b.content for b in instruction_blocks)
        assert "Use type hints" in all_instruction_text


class TestParseCaudeMdText:
    """Verify that text blocks are detected for regular paragraphs."""

    def test_parse_claude_md_text(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        text_blocks = [b for b in blocks if b.block_type == "text"]

        # The Architecture paragraph ("This is a FastAPI app...") and the
        # Key Decisions paragraph should be plain text
        assert len(text_blocks) >= 1, (
            f"Expected at least 1 text block, got {len(text_blocks)}"
        )

        all_text = " ".join(b.content for b in text_blocks)
        assert "FastAPI" in all_text or "MiniLM" in all_text

    def test_all_blocks_have_content(self, sample_claude_md: Path) -> None:
        blocks = parse_claude_md(str(sample_claude_md))

        for b in blocks:
            assert isinstance(b, ParsedBlock)
            assert b.content, f"Block of type {b.block_type!r} has empty content"
            assert b.block_type in {
                "heading", "code", "instruction", "text",
                "reasoning", "tool_output",
            }


# ---------------------------------------------------------------------------
# Session log parsing
# ---------------------------------------------------------------------------


class TestParseSessionLog:
    """Verify session log parsing produces expected block types."""

    def test_parse_session_log(self, sample_session_log: Path) -> None:
        blocks = parse_session_log(str(sample_session_log))

        block_types = {b.block_type for b in blocks}

        # Session log has headings, text, and at least one code block
        assert "heading" in block_types, "Session log should contain headings"
        assert "code" in block_types, "Session log should contain a code block"

    def test_session_log_headings(self, sample_session_log: Path) -> None:
        blocks = parse_session_log(str(sample_session_log))

        headings = [b for b in blocks if b.block_type == "heading"]
        heading_titles = [h.content for h in headings]

        # Should find the session header and subsections
        assert any("Session" in t for t in heading_titles)
        assert any("User Request" in t for t in heading_titles)
        assert any("Actions Taken" in t for t in heading_titles)
        assert any("Files Modified" in t for t in heading_titles)

    def test_session_log_code_block(self, sample_session_log: Path) -> None:
        blocks = parse_session_log(str(sample_session_log))

        code_blocks = [b for b in blocks if b.block_type == "code"]
        assert len(code_blocks) >= 1

        # The code block contains "Before" / "After" comments
        code_text = code_blocks[0].content
        assert "Before" in code_text or "After" in code_text
        assert code_blocks[0].metadata["language"] == "python"

    def test_session_log_preserves_order(self, sample_session_log: Path) -> None:
        blocks = parse_session_log(str(sample_session_log))

        # Line numbers should be monotonically non-decreasing
        prev_start = 0
        for b in blocks:
            current_start = b.metadata.get("line_start", 0)
            assert current_start >= prev_start, (
                f"Block ordering broken: line_start {current_start} < {prev_start}"
            )
            prev_start = current_start
