"""Configuration for the Claude Code RAG system.

Supports local mode (env vars / .env file) and AWS mode (Secrets Manager).
Modeled after lambda-s3-trigger/ingestion-worker/app/config.py.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root if it exists
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Config:
    """Central configuration with env var overrides and sensible defaults."""

    # --- Database ---
    DB_MODE: str = os.getenv("DB_MODE", "local")  # "local" or "aws"
    PGHOST: str = os.getenv("PGHOST", "localhost")
    PGPORT: int = int(os.getenv("PGPORT", "5432"))
    PGUSER: str = os.getenv("PGUSER", "postgres")
    PGPASSWORD: str = os.getenv("PGPASSWORD", "")
    PGDATABASE: str = os.getenv("PGDATABASE", "claude_rag")

    # AWS fallback (only used when DB_MODE == "aws")
    DB_SECRET_NAME: str = os.getenv("DB_SECRET_NAME", "llm-db-credentials")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # --- Embeddings ---
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # --- Chunking ---
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))  # tokens
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))  # tokens

    # --- Memory directories to watch ---
    CLAUDE_MEMORY_DIRS: list[str] = [
        d.strip()
        for d in os.getenv(
            "CLAUDE_MEMORY_DIRS",
            str(Path.home() / ".claude"),
        ).split(",")
    ]

    # --- Search ---
    SEARCH_TOP_K: int = int(os.getenv("SEARCH_TOP_K", "10"))
    RELEVANCE_THRESHOLD: float = float(os.getenv("RELEVANCE_THRESHOLD", "0.25"))  # min cosine similarity for semantic-only matches
    CONTEXT_TOKEN_BUDGET: int = int(os.getenv("CONTEXT_TOKEN_BUDGET", "4096"))
    RRF_K: int = int(os.getenv("RRF_K", "60"))  # RRF constant

    # --- State ---
    STATE_DIR: Path = Path(
        os.getenv("CLAUDE_RAG_STATE_DIR", str(Path.home() / ".claude-rag"))
    )

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")  # "json" or "text"

    def __repr__(self) -> str:
        return (
            f"Config(DB_MODE={self.DB_MODE!r}, PGHOST={self.PGHOST!r}, "
            f"PGDATABASE={self.PGDATABASE!r}, EMBEDDING_MODEL={self.EMBEDDING_MODEL!r}, "
            f"EMBEDDING_DIM={self.EMBEDDING_DIM}, CHUNK_SIZE={self.CHUNK_SIZE}, "
            f"SEARCH_TOP_K={self.SEARCH_TOP_K})"
        )

    @property
    def dsn(self) -> str:
        """Return a PostgreSQL DSN string for local mode."""
        return (
            f"host={self.PGHOST} port={self.PGPORT} dbname={self.PGDATABASE} "
            f"user={self.PGUSER} password={self.PGPASSWORD}"
        )
