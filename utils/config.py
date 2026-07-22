"""Central configuration and lazy-initialized singletons.

Reads API credentials from the ``.env`` file via ``python-dotenv`` and exposes
them as module-level constants.  Expensive clients (OpenAI, ChromaDB) are
created once on first access.
"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("MODEL")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path("./data/datasets/js-to-cpp")
DB_PATH = Path("./db")
PROMPT_DIR = Path("./prompts")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "taint_knowledge"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
TOP_K = 3  # RAG retrieval: top-K per query
LLM_MAX_WORKERS = int(os.getenv("LLM_MAX_WORKERS", "4"))

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_llm_client: OpenAI | None = None
_chroma_client: chromadb.PersistentClient | None = None


def get_llm_client() -> OpenAI:
    """Return the lazily-initialized OpenAI-compatible client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _llm_client


def get_chroma_client() -> chromadb.PersistentClient:
    """Return the lazily-initialized ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    return _chroma_client
