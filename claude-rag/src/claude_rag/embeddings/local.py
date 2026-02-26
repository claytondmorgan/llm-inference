"""Local embedding provider backed by the existing EmbeddingGenerator.

Delegates to the torch + transformers implementation in
``lambda-s3-trigger/ingestion-worker/app/embeddings.py`` via a
``sys.path`` adjustment so ``from app.embeddings import EmbeddingGenerator``
resolves correctly.

The import and model loading are **lazy** — deferred until the first call
to :meth:`embed` or :meth:`embed_single` — so that merely importing this
module does not trigger the ~90 MB weight download / PyTorch init.  This
keeps IDE debugging responsive and startup fast.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from claude_rag.config import Config
from claude_rag.embeddings.base import EmbeddingProvider

if TYPE_CHECKING:
    from app.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Make the ingestion-worker package importable.
# The layout is:
#   <project-root>/lambda-s3-trigger/ingestion-worker/app/embeddings.py
# Adding ``<project-root>/lambda-s3-trigger/ingestion-worker`` to sys.path
# lets us do ``from app.embeddings import EmbeddingGenerator``.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_INGESTION_WORKER_DIR = str(_PROJECT_ROOT / "lambda-s3-trigger" / "ingestion-worker")

if _INGESTION_WORKER_DIR not in sys.path:
    sys.path.insert(0, _INGESTION_WORKER_DIR)


class LocalEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that runs a transformer model locally.

    Wraps the existing ``EmbeddingGenerator`` which uses ``torch`` and
    ``transformers`` (AutoTokenizer / AutoModel) directly -- **not** the
    ``sentence_transformers`` library.

    The heavy model load is deferred until the first embedding call, so
    constructing this object is fast and debugger-friendly.

    Args:
        model_name: HuggingFace model identifier.  Falls back to
            ``Config.EMBEDDING_MODEL`` when *None*.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or Config.EMBEDDING_MODEL
        self._generator: EmbeddingGenerator | None = None
        self._dimension: int = Config.EMBEDDING_DIM
        logger.info("LocalEmbeddingProvider configured with model %s (lazy load)", self._model_name)

    def _ensure_loaded(self) -> EmbeddingGenerator:
        """Lazily import and instantiate the EmbeddingGenerator."""
        if self._generator is None:
            logger.info("Loading embedding model %s ...", self._model_name)
            from app.embeddings import EmbeddingGenerator as _EG  # noqa: E402

            self._generator = _EG(model_name=self._model_name)
            logger.info("Embedding model loaded.")
        return self._generator

    # ------------------------------------------------------------------
    # EmbeddingProvider interface
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Delegates to ``EmbeddingGenerator.generate_batch``.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embedding vectors, one per input text.  Entries
            corresponding to empty input strings may be *None*.
        """
        return self._ensure_loaded().generate_batch(texts)

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text.

        Delegates to ``EmbeddingGenerator.generate_single``.

        Args:
            text: The string to embed.

        Returns:
            The embedding vector for the input text.
        """
        return self._ensure_loaded().generate_single(text)

    @property
    def dimension(self) -> int:
        """Return the embedding dimension.

        Returns:
            The configured embedding dimensionality (384 by default).
        """
        return self._dimension
