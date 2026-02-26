"""Memory-file parser for the Claude Code RAG system.

Parses CLAUDE.md files and session-log transcripts into structured
``ParsedBlock`` sequences suitable for downstream chunking and embedding.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_CODE_FENCE_OPEN_RE = re.compile(r"^```(\w*)\s*$")
_CODE_FENCE_CLOSE_RE = re.compile(r"^```\s*$")

# Session-log markers (Claude Code JSON / conversation transcripts)
_TOOL_OUTPUT_START_RE = re.compile(
    r"^(Tool output|<tool_output|<function_result)", re.IGNORECASE
)
_TOOL_OUTPUT_END_RE = re.compile(
    r"^(</tool_output>|</function_result>)", re.IGNORECASE
)
_REASONING_START_RE = re.compile(r"^(<thinking>|<reasoning>|\[reasoning\])", re.IGNORECASE)
_REASONING_END_RE = re.compile(r"^(</thinking>|</reasoning>|\[/reasoning\])", re.IGNORECASE)

# Heuristic: lines that look like an instruction (imperative sentence or
# bullet starting with a verb).  Kept intentionally broad so that the
# downstream LLM can refine.
_INSTRUCTION_HINT_RE = re.compile(
    r"^[-*]\s+(Always|Never|Do not|Make sure|Use|Prefer|Avoid|Run|Ensure|Remember)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ParsedBlock:
    """A contiguous, semantically meaningful block extracted from a memory file.

    Attributes:
        content: The raw text content of the block.
        block_type: Semantic label — one of ``"heading"``, ``"code"``,
            ``"instruction"``, ``"reasoning"``, ``"tool_output"``, or
            ``"text"``.
        metadata: Extra information about the block.  Common keys:

            * ``heading_level`` (int) — for heading blocks.
            * ``language`` (str) — for code blocks.
            * ``line_start`` (int) — 1-based start line in the source file.
            * ``line_end`` (int) — 1-based end line (inclusive).
    """

    content: str
    block_type: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_paragraph(text: str) -> str:
    """Return ``"instruction"`` or ``"text"`` for a plain-text paragraph.

    Args:
        text: The paragraph content (may be multiple lines).

    Returns:
        ``"instruction"`` if the paragraph contains imperative / directive
        language; ``"text"`` otherwise.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if _INSTRUCTION_HINT_RE.match(stripped):
            return "instruction"
    return "text"


def _parse_lines(lines: list[str]) -> list[ParsedBlock]:
    """Walk *lines* and emit ``ParsedBlock`` objects.

    The parser is a single-pass state machine that recognises headings,
    fenced code blocks, tool-output regions, reasoning regions, and plain
    paragraphs.

    Args:
        lines: Source file split into individual lines (without trailing
            newlines).

    Returns:
        Ordered list of ``ParsedBlock`` instances.
    """
    blocks: list[ParsedBlock] = []

    # Accumulator for the current plain-text paragraph
    para_lines: list[str] = []
    para_start: int = 0

    # State flags
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    code_start: int = 0

    in_tool_output = False
    tool_lines: list[str] = []
    tool_start: int = 0

    in_reasoning = False
    reasoning_lines: list[str] = []
    reasoning_start: int = 0

    def _flush_paragraph() -> None:
        """Emit the accumulated plain-text paragraph (if any)."""
        if not para_lines:
            return
        text = "\n".join(para_lines)
        btype = _classify_paragraph(text)
        blocks.append(
            ParsedBlock(
                content=text,
                block_type=btype,
                metadata={
                    "line_start": para_start,
                    "line_end": para_start + len(para_lines) - 1,
                },
            )
        )
        para_lines.clear()

    for idx, raw_line in enumerate(lines):
        lineno = idx + 1  # 1-based
        line = raw_line

        # ---- inside a fenced code block --------------------------------
        if in_code:
            if _CODE_FENCE_CLOSE_RE.match(line) and line.strip() == "```":
                blocks.append(
                    ParsedBlock(
                        content="\n".join(code_lines),
                        block_type="code",
                        metadata={
                            "language": code_lang,
                            "line_start": code_start,
                            "line_end": lineno,
                        },
                    )
                )
                in_code = False
                code_lines = []
                code_lang = ""
            else:
                code_lines.append(line)
            continue

        # ---- inside a tool-output region --------------------------------
        if in_tool_output:
            if _TOOL_OUTPUT_END_RE.match(line.strip()):
                blocks.append(
                    ParsedBlock(
                        content="\n".join(tool_lines),
                        block_type="tool_output",
                        metadata={
                            "line_start": tool_start,
                            "line_end": lineno,
                        },
                    )
                )
                in_tool_output = False
                tool_lines = []
            else:
                tool_lines.append(line)
            continue

        # ---- inside a reasoning region ----------------------------------
        if in_reasoning:
            if _REASONING_END_RE.match(line.strip()):
                blocks.append(
                    ParsedBlock(
                        content="\n".join(reasoning_lines),
                        block_type="reasoning",
                        metadata={
                            "line_start": reasoning_start,
                            "line_end": lineno,
                        },
                    )
                )
                in_reasoning = False
                reasoning_lines = []
            else:
                reasoning_lines.append(line)
            continue

        # ---- code fence opening -----------------------------------------
        m_code = _CODE_FENCE_OPEN_RE.match(line)
        if m_code:
            _flush_paragraph()
            in_code = True
            code_lang = m_code.group(1) or ""
            code_start = lineno
            continue

        # ---- tool output opening ----------------------------------------
        if _TOOL_OUTPUT_START_RE.match(line.strip()):
            _flush_paragraph()
            in_tool_output = True
            tool_start = lineno
            tool_lines = []
            continue

        # ---- reasoning opening ------------------------------------------
        if _REASONING_START_RE.match(line.strip()):
            _flush_paragraph()
            in_reasoning = True
            reasoning_start = lineno
            reasoning_lines = []
            continue

        # ---- heading ----------------------------------------------------
        m_heading = _HEADING_RE.match(line)
        if m_heading:
            _flush_paragraph()
            level = len(m_heading.group(1))
            title = m_heading.group(2).strip()
            blocks.append(
                ParsedBlock(
                    content=title,
                    block_type="heading",
                    metadata={
                        "heading_level": level,
                        "line_start": lineno,
                        "line_end": lineno,
                    },
                )
            )
            continue

        # ---- blank line → flush paragraph -------------------------------
        if line.strip() == "":
            _flush_paragraph()
            continue

        # ---- accumulate paragraph line ----------------------------------
        if not para_lines:
            para_start = lineno
        para_lines.append(line)

    # Flush any trailing state ------------------------------------------
    _flush_paragraph()

    if in_code and code_lines:
        blocks.append(
            ParsedBlock(
                content="\n".join(code_lines),
                block_type="code",
                metadata={
                    "language": code_lang,
                    "line_start": code_start,
                    "line_end": len(lines),
                },
            )
        )

    if in_tool_output and tool_lines:
        blocks.append(
            ParsedBlock(
                content="\n".join(tool_lines),
                block_type="tool_output",
                metadata={
                    "line_start": tool_start,
                    "line_end": len(lines),
                },
            )
        )

    if in_reasoning and reasoning_lines:
        blocks.append(
            ParsedBlock(
                content="\n".join(reasoning_lines),
                block_type="reasoning",
                metadata={
                    "line_start": reasoning_start,
                    "line_end": len(lines),
                },
            )
        )

    return blocks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_claude_md(file_path: str) -> list[ParsedBlock]:
    """Parse a ``CLAUDE.md`` memory file into structured blocks.

    Recognises markdown headings, fenced code blocks (with language hints),
    instruction-like bullet lists, and plain text paragraphs.

    Args:
        file_path: Absolute or relative path to the ``.md`` file.

    Returns:
        Ordered list of ``ParsedBlock`` instances covering the entire file.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    logger.debug("Parsing CLAUDE.md %s (%d lines)", file_path, len(lines))
    return _parse_lines(lines)


def parse_session_log(file_path: str) -> list[ParsedBlock]:
    """Parse a Claude Code session transcript into structured blocks.

    In addition to standard markdown structures this function detects
    tool-output regions (``<tool_output>`` / ``<function_result>``) and
    reasoning regions (``<thinking>`` / ``<reasoning>``).

    Args:
        file_path: Absolute or relative path to the session-log file.

    Returns:
        Ordered list of ``ParsedBlock`` instances covering the entire file.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    logger.debug("Parsing session log %s (%d lines)", file_path, len(lines))
    return _parse_lines(lines)
