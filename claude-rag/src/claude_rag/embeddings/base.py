"""Abstract embedding provider interface.

All embedding backends (local transformer, remote API, etc.) implement
this protocol so the rest of the RAG pipeline stays backend-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Base class that every embedding backend must implement."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        ...

    @abstractmethod
    def embed_single(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: The string to embed.

        Returns:
            The embedding vector for the input text.
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension.

        Returns:
            The integer dimensionality of vectors produced by this provider.
        """
        ...
