#!/usr/bin/env python3
"""Build the offline knowledge base.

Reads vulnerability code samples (source + context), generates a CPG for each,
sends it to an LLM with taint-analysis prompts to obtain structured knowledge,
encodes the retrieval description into a vector, and stores the result in ChromaDB.

Usage:
  python build_kb.py [--mini] [--reset-db] [--start N] [--limit N]

Flags:
  --mini      Use knowledge.mini.parquet (debug subset) instead of the full dataset.
  --reset-db  Drop and re-create the ChromaDB collection before starting.
  --start N   Start processing at row index N (0-based, for resumption).
  --limit N   Stop after processing N samples.
"""

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from framework.config import DATA_DIR, COLLECTION_NAME
from framework.cpg import generate_cpg_json
from framework.embeddings import get_embedding_model
from framework.llm import call_llm_with_retry, extract_json
from framework.progress import ProgressTracker
from framework.prompts import (
    PH_CPG,
    PH_CONTEXT,
    inject_placeholders,
    load_prompt_messages,
)
from framework.vectordb import get_collection

load_dotenv()

# ---------------------------------------------------------------------------
# Per-pipeline constants
# ---------------------------------------------------------------------------

PROMPT_DIR_KB = Path("./prompts/taint-analysis")
PROGRESS_FILE = Path("./build_kb_progress.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build offline taint-analysis knowledge base"
    )
    parser.add_argument(
        "--mini", action="store_true", help="Use knowledge.mini.parquet (debug subset)"
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
    args = parser.parse_args()

    # --- Load dataset ----------------------------------------------------------
    parquet_name = "knowledge.mini.parquet" if args.mini else "knowledge.parquet"
    parquet_path = DATA_DIR / parquet_name
    if not parquet_path.exists():
        print(f"ERROR: {parquet_path} not found. Run create_mini_dataset.py first?")
        sys.exit(1)

    df = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df)} samples from {parquet_path}")

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

    # --- Prompt template (load once) -------------------------------------------
    base_messages = load_prompt_messages(PROMPT_DIR_KB)

    # --- Process samples -------------------------------------------------------
    start_idx = max(args.start, 0)
    end_idx = len(df) if args.limit is None else min(start_idx + args.limit, len(df))

    total_processed = 0
    total_errors = 0

    for idx in range(start_idx, end_idx):
        if idx in processed:
            continue

        row = df.iloc[idx]
        row_id = int(row.get("id", idx))
        source_code = str(row["source"])
        context = str(row["context"])

        print(f"\n--- Sample {idx} (id={row_id}) ---")

        try:
            # Step 1: Generate CPG
            print("  Generating CPG...")
            cpg_json_str = generate_cpg_json(source_code)
            print(f"  CPG size: {len(cpg_json_str)} chars")

            # Step 2: Build messages with injected CPG + context
            messages = inject_placeholders(
                base_messages,
                **{PH_CPG: cpg_json_str, PH_CONTEXT: context},
            )

            # Step 3: Call LLM (with retries built in)
            print("  LLM call...")
            response_text = call_llm_with_retry(messages)

            # Step 4: Parse response
            output = extract_json(response_text)
            knowledge = output["knowledge"]
            description = output["description"]
            print(f"  knowledge: {knowledge[:100]}...")
            print(f"  description: {description[:100]}...")

            # Step 5: Encode description
            embeddings = embedding_model.encode([description])

            # Step 6: Store in ChromaDB
            doc_id = f"kb_{idx}_{row_id}"
            collection.add(
                embeddings=embeddings.tolist(),
                documents=[knowledge],
                metadatas=[{"task": "js-to-cpp", "source_id": str(row_id)}],
                ids=[doc_id],
            )
            print(f"  Stored in ChromaDB as '{doc_id}'")

            processed.add(idx)
            total_processed += 1

            if total_processed % 5 == 0:
                progress.save(processed)

        except Exception as e:
            total_errors += 1
            print(f"  ERROR on sample {idx}: {e}")
            traceback.print_exc()

    # --- Final save ------------------------------------------------------------
    progress.save(processed)
    print(f"\n{'=' * 60}")
    print(f"Done! Processed {total_processed} new samples ({total_errors} errors)")
    print(f"Total in collection: {collection.count()}")


if __name__ == "__main__":
    main()
