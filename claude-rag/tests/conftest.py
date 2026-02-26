"""Shared pytest fixtures for the Claude RAG test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the src directory is on the import path
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from claude_rag.config import Config


@pytest.fixture()
def config() -> Config:
    """Return a default Config instance."""
    return Config()


SAMPLE_CLAUDE_MD = """\
# Project Instructions

## Architecture
This is a FastAPI app with PostgreSQL + pgvector for semantic search.

## Code Style
- Use type hints on all functions
- Google-style docstrings
- Pytest for tests

## Key Decisions
We chose all-MiniLM-L6-v2 for embeddings because it has a good
trade-off between quality and speed for a local system.

```python
def get_embedding(text: str) -> list[float]:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text).tolist()
```

## Database
- Host: localhost:5432
- Database: llm_inference
- Tables: documents, ingested_records, legal_documents

## Recent Changes
- Added hybrid RRF search combining semantic + keyword
- Migrated legal embeddings from 384-dim to 768-dim ModernBERT
"""

SAMPLE_SESSION_LOG = """\
# Session: 2025-02-20T14:30:00

## User Request
Fix the failing tests in test_search.py

## Actions Taken
1. Read test_search.py — found assertion comparing float equality
2. Changed `assertEqual` to `assertAlmostEqual` with delta=0.001
3. Ran tests — all green

## Files Modified
- tests/test_search.py (line 42: fixed float comparison)
- src/search/hybrid.py (line 88: added rounding to RRF scores)

```python
# Before
assert result.similarity == 0.85
# After
self.assertAlmostEqual(result.similarity, 0.85, delta=0.001)
```
"""


@pytest.fixture()
def sample_claude_md(tmp_path: Path) -> Path:
    """Write a sample CLAUDE.md to a temp directory and return its path."""
    p = tmp_path / "CLAUDE.md"
    p.write_text(SAMPLE_CLAUDE_MD, encoding="utf-8")
    return p


@pytest.fixture()
def sample_session_log(tmp_path: Path) -> Path:
    """Write a sample session log to a temp directory and return its path."""
    p = tmp_path / "session_2025-02-20.md"
    p.write_text(SAMPLE_SESSION_LOG, encoding="utf-8")
    return p
