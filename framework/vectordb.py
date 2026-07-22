"""ChromaDB vector-database operations."""

from __future__ import annotations

import sys

import chromadb

from framework.config import get_chroma_client, COLLECTION_NAME


def get_collection(
    name: str | None = None,
    reset: bool = False,
) -> chromadb.Collection:
    """Get (or create) a ChromaDB collection.

    Args:
        name: Collection name (defaults to ``COLLECTION_NAME`` from config).
        reset: If ``True``, drop and recreate the collection first.

    Returns:
        The ready-to-use :class:`chromadb.Collection`.
    """
    collection_name = name or COLLECTION_NAME
    client = get_chroma_client()

    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass  # collection didn't exist — that's fine

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def require_collection(name: str | None = None) -> chromadb.Collection:
    """Get a collection that must already exist.

    Like :func:`get_collection` but prints an error and exits if the
    collection is absent (used by the detection pipeline).
    """
    collection_name = name or COLLECTION_NAME
    client = get_chroma_client()
    try:
        return client.get_collection(collection_name)
    except Exception:
        print(
            f"ERROR: ChromaDB collection '{collection_name}' not found "
            f"at the configured path.  Run build_kb.py first to build "
            f"the knowledge base."
        )
        sys.exit(1)
