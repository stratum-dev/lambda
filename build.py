#!/usr/bin/env python3
"""Build the offline knowledge base.

Reads vulnerability code samples (source + context) from the HuggingFace dataset
codemetic/lambda (knowledge split), generates a CPG for each, sends it to an LLM
with taint-analysis prompts to obtain structured knowledge, encodes the retrieval
description into a vector, and stores the result in ChromaDB.

Usage:
  python build.py [--subset NAME] [--language LANG] [--reset-db] [--start N] [--limit N] [--workers N]

Flags:
  --subset NAME   Dataset subset/config to load (default: js-to-cpp).
                  Available: cpp-only, java-to-cpp, js-to-cpp, debug.
  --language LANG  Programming language for CPG generation (default: javascript).
                  Supported: javascript, cpp, java, python.
  --reset-db      Drop and re-create the ChromaDB collection before starting.
  --start N       Start processing at row index N (0-based, for resumption).
  --limit N       Stop after processing N samples.
  --workers N     Max parallel LLM requests (default: LLM_MAX_WORKERS env or 4).
"""

import argparse
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv

from lambda_utils.config import (
    HF_DATASET_REPO,
    HF_DATASET_SUBSET_DEFAULT,
    COLLECTION_NAME,
    LLM_MAX_WORKERS,
)
from lambda_utils.cpg import generate_cpg_json
from lambda_utils.embeddings import get_embedding_model
from lambda_utils.llm import call_llm_with_retry, extract_json
from lambda_utils.progress import ProgressTracker
from lambda_utils.prompts import (
    load_prompt_messages,
    render_messages,
)
from lambda_utils.vectordb import get_collection

load_dotenv()

# ---------------------------------------------------------------------------
# Per-pipeline constants
# ---------------------------------------------------------------------------

PROMPT_DIR_KB = Path("./prompts/taint-analysis")
PROGRESS_FILE = Path("./build_kb_progress.t.json")


# ---------------------------------------------------------------------------
# Per-sample worker
# ---------------------------------------------------------------------------


def _process_one(
    idx: int,
    row,
    subset: str,
    language: str,
    base_messages: list[dict],
    embedding_model,
    collection,
    lock: threading.Lock,
    processed: set[int],
    progress: ProgressTracker,
    counters: dict,
) -> tuple[int, str, str]:
    """Process a single sample — CPG → LLM → embed → ChromaDB.

    Returns ``(idx, knowledge, description)`` on success.
    Raises on failure (caught by the caller).
    """
    row_id = int(row.get("id", idx))
    source_code = str(row["source"])
    context = str(row["context"])

    # Step 1: Generate CPG
    cpg_json_str = generate_cpg_json(source_code, language=language)

    # Step 2: Build messages + call LLM
    messages = render_messages(
        base_messages,
        cpg=cpg_json_str,
        context=context,
    )
    response_text = call_llm_with_retry(messages)

    # Step 3: Parse response
    output = extract_json(response_text)
    knowledge = output["knowledge"]
    description = output["description"]

    # Step 4: Encode description
    embeddings = embedding_model.encode([description])

    # Step 5: Store in ChromaDB (serialised — SQLite is not thread-safe for writes)
    doc_id = f"kb_{idx}_{row_id}"
    with lock:
        collection.add(
            embeddings=embeddings.tolist(),
            documents=[knowledge],
            metadatas=[{"subset": subset, "source_id": str(row_id)}],
            ids=[doc_id],
        )

    # Step 6: Mark processed (serialised)
    with lock:
        processed.add(idx)
        counters["done"] += 1
        if counters["done"] % 5 == 0:
            progress.save(processed)

    return idx, knowledge, description


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build offline taint-analysis knowledge base"
    )
    parser.add_argument(
        "--subset",
        type=str,
        default=HF_DATASET_SUBSET_DEFAULT,
        help=f"Dataset subset/config to load (default: {HF_DATASET_SUBSET_DEFAULT})",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="javascript",
        help="Programming language for CPG generation (default: javascript)",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Drop and recreate the ChromaDB collection",
    )
    parser.add_argument(
        "--start", type=int, default=0, help="Start processing at row index (0-based)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Stop after N samples")
    parser.add_argument(
        "--workers",
        type=int,
        default=LLM_MAX_WORKERS,
        help=f"Max parallel LLM requests (default: {LLM_MAX_WORKERS})",
    )
    args = parser.parse_args()

    # --- Load dataset ----------------------------------------------------------
    print(
        f"Loading '{args.subset}' subset from {HF_DATASET_REPO} (knowledge split) ..."
    )
    try:
        dataset = load_dataset(HF_DATASET_REPO, args.subset, split="knowledge")
    except Exception as e:
        print(f"ERROR: Failed to load dataset: {e}")
        sys.exit(1)

    df = dataset.to_pandas()
    print(f"Loaded {len(df)} samples, columns={list(df.columns)}")
    print(f"Max workers: {args.workers}")

    # --- Infrastructure --------------------------------------------------------
    collection = get_collection(name=COLLECTION_NAME, reset=args.reset_db)
    print(
        f"ChromaDB collection '{COLLECTION_NAME}' ready "
        f"(current count: {collection.count()})"
    )

    embedding_model = get_embedding_model()

    progress = ProgressTracker(PROGRESS_FILE)
    processed = progress.load()
    if processed:
        print(f"Resuming — {len(processed)} samples already processed, will skip those")

    # --- Prompt template (load once — read-only, safe to share across threads) --
    base_messages = load_prompt_messages(PROMPT_DIR_KB)

    # --- Gather pending indices -------------------------------------------------
    start_idx = max(args.start, 0)
    end_idx = len(df) if args.limit is None else min(start_idx + args.limit, len(df))
    pending = [i for i in range(start_idx, end_idx) if i not in processed]

    if not pending:
        print("All samples already processed — nothing to do.")
        return

    print(f"Processing {len(pending)} samples with {args.workers} workers ...")

    # --- Shared state -----------------------------------------------------------
    lock = threading.Lock()
    counters: dict = {"done": 0, "errors": 0}

    # --- Parallel execution -----------------------------------------------------
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_idx = {}
        for idx in pending:
            future = executor.submit(
                _process_one,
                idx,
                df.iloc[idx],
                args.subset,
                args.language,
                base_messages,
                embedding_model,
                collection,
                lock,
                processed,
                progress,
                counters,
            )
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            row_id = int(df.iloc[idx].get("id", idx))
            try:
                _, knowledge, _ = future.result()
                print(
                    f"[{counters['done']}/{len(pending)}] "
                    f"Sample {idx} (id={row_id}) OK — "
                    f"knowledge: {knowledge[:80]}..."
                )
            except Exception:
                with lock:
                    counters["errors"] += 1
                print(
                    f"[{counters['done']}/{len(pending)}] Sample {idx} (id={row_id}) ERROR"
                )
                traceback.print_exc()

    # --- Final save ------------------------------------------------------------
    progress.save(processed)
    print(f"\n{'=' * 60}")
    print(
        f"Done! Processed {counters['done']} new samples "
        f"({counters['errors']} errors)"
    )
    print(f"Total in collection: {collection.count()}")


if __name__ == "__main__":
    main()
