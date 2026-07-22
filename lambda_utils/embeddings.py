"""Text-embedding model wrapper (sentence-transformers)."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from lambda_utils.config import EMBEDDING_MODEL_NAME

_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Return the lazily-initialized SentenceTransformer singleton."""
    global _embedding_model
    if _embedding_model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model
