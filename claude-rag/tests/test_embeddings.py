"""Tests for the Claude RAG embeddings module (claude_rag.embeddings)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.embeddings.base import EmbeddingProvider


# ---------------------------------------------------------------------------
# Helper: conditionally import LocalEmbeddingProvider
# ---------------------------------------------------------------------------

_local_provider_available = True
_local_import_error: str | None = None

try:
    from claude_rag.embeddings.local import LocalEmbeddingProvider
except Exception as exc:  # noqa: BLE001
    _local_provider_available = False
    _local_import_error = str(exc)


# ---------------------------------------------------------------------------
# Tests — abstract base class
# ---------------------------------------------------------------------------


class TestBaseInterface:
    """Verify EmbeddingProvider cannot be instantiated (abstract)."""

    def test_base_interface(self) -> None:
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]

    def test_base_declares_embed(self) -> None:
        assert hasattr(EmbeddingProvider, "embed")

    def test_base_declares_embed_single(self) -> None:
        assert hasattr(EmbeddingProvider, "embed_single")

    def test_base_declares_dimension(self) -> None:
        assert hasattr(EmbeddingProvider, "dimension")


# ---------------------------------------------------------------------------
# Tests — LocalEmbeddingProvider (require model download; marked slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not _local_provider_available,
    reason=f"LocalEmbeddingProvider not importable: {_local_import_error}",
)
class TestLocalProviderDimension:
    """Verify that LocalEmbeddingProvider reports dimension == 384."""

    def test_local_provider_dimension(self) -> None:
        provider = LocalEmbeddingProvider()
        assert provider.dimension == 384


@pytest.mark.slow
@pytest.mark.skipif(
    not _local_provider_available,
    reason=f"LocalEmbeddingProvider not importable: {_local_import_error}",
)
class TestLocalProviderEmbedSingle:
    """Verify that embed_single returns a list of 384 floats."""

    def test_local_provider_embed_single(self) -> None:
        provider = LocalEmbeddingProvider()
        embedding = provider.embed_single("Hello, world!")

        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(v, float) for v in embedding)

    def test_local_provider_embed_single_nonempty(self) -> None:
        provider = LocalEmbeddingProvider()
        embedding = provider.embed_single("Test embedding content")

        # Embedding should not be all zeros
        assert any(v != 0.0 for v in embedding)


@pytest.mark.slow
@pytest.mark.skipif(
    not _local_provider_available,
    reason=f"LocalEmbeddingProvider not importable: {_local_import_error}",
)
class TestLocalProviderEmbedBatch:
    """Verify batch embedding returns correct number of 384-dim vectors."""

    def test_local_provider_embed_batch(self) -> None:
        provider = LocalEmbeddingProvider()
        texts = [
            "First document about Python.",
            "Second document about databases.",
            "Third document about machine learning.",
        ]
        embeddings = provider.embed(texts)

        assert isinstance(embeddings, list)
        assert len(embeddings) == len(texts)

        for i, emb in enumerate(embeddings):
            assert isinstance(emb, list), f"Embedding {i} is not a list"
            assert len(emb) == 384, (
                f"Embedding {i} has dimension {len(emb)}, expected 384"
            )
            assert all(isinstance(v, float) for v in emb), (
                f"Embedding {i} contains non-float values"
            )

    def test_local_provider_embed_batch_single_item(self) -> None:
        provider = LocalEmbeddingProvider()
        embeddings = provider.embed(["Single item batch"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384
