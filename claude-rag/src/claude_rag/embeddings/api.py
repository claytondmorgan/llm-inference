"""Remote embedding provider for OpenAI-compatible /v1/embeddings APIs.

This is a structural stub -- it is fully typed and documented but intended
to be fleshed out once an API key and endpoint are available.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from claude_rag.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com"
_DEFAULT_MODEL = "text-embedding-3-small"
_DEFAULT_DIMENSION = 1536


class APIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that calls an OpenAI-compatible ``/v1/embeddings`` endpoint.

    Args:
        api_key: Bearer token for the API.  If *None*, calls to
            :meth:`embed` / :meth:`embed_single` will raise
            :class:`ValueError`.
        model_name: Model identifier sent in the request body.
        base_url: Root URL of the API (no trailing slash).
        dimension: Dimensionality of the vectors returned by the model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        dimension: int = _DEFAULT_DIMENSION,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._dimension = dimension

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_api_key(self) -> str:
        """Return the API key or raise if it was never set.

        Returns:
            The configured API key.

        Raises:
            ValueError: If no API key was provided at construction time.
        """
        if not self._api_key:
            raise ValueError(
                "APIEmbeddingProvider requires an api_key. "
                "Pass one to the constructor or set the OPENAI_API_KEY env var."
            )
        return self._api_key

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Send texts to the remote /v1/embeddings endpoint.

        Args:
            texts: The batch of strings to embed.

        Returns:
            A list of embedding vectors in the same order as *texts*.

        Raises:
            ValueError: If no API key is configured.
            httpx.HTTPStatusError: On non-2xx responses from the API.
        """
        api_key = self._ensure_api_key()
        url = f"{self._base_url}/v1/embeddings"

        payload: dict[str, Any] = {
            "input": texts,
            "model": self._model_name,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(
            "Requesting embeddings for %d text(s) from %s", len(texts), url
        )

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        data = response.json()

        # The OpenAI response nests vectors under {"data": [{"embedding": [...]}]}
        # and results may not be in input order, so sort by index.
        sorted_items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in sorted_items]

    # ------------------------------------------------------------------
    # EmbeddingProvider interface
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the remote API.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            ValueError: If no API key is configured.
        """
        return self._request_embeddings(texts)

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text via the remote API.

        Args:
            text: The string to embed.

        Returns:
            The embedding vector for the input text.

        Raises:
            ValueError: If no API key is configured.
        """
        return self._request_embeddings([text])[0]

    @property
    def dimension(self) -> int:
        """Return the embedding dimension.

        Returns:
            The dimensionality configured at construction time.
        """
        return self._dimension
