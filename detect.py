#!/usr/bin/env python3
"""
Run online vulnerability detection.

For each code sample, generates a CPG, extracts taint-chain descriptions via
LLM, queries the ChromaDB knowledge base for similar vulnerability patterns,
and makes a final vulnerability determination via a second LLM call.

After processing, computes F1, MCC, Recall, and Precision against the ground-
truth labels.

Usage:
  python detect.py [--mini] [--start N] [--limit N]

Flags:
  --mini      Use inference.mini.parquet (debug subset) instead of the full dataset.
  --start N   Start processing at row index N (0-based, for resumption).
  --limit N   Stop after processing N samples.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from utils.config import DATA_DIR, COLLECTION_NAME, TOP_K
from utils.cpg import generate_cpg_json
from utils.embeddings import get_embedding_model
from utils.llm import call_llm_with_retry, extract_json
from utils.metrics import compute_metrics
from utils.progress import ProgressTracker
from utils.prompts import (
    PH_CPG,
    PH_KNOWLEDGE,
    inject_placeholders,
    load_prompt_messages,
)
from utils.vectordb import require_collection

load_dotenv()

# ---------------------------------------------------------------------------
# Per-pipeline constants
# ---------------------------------------------------------------------------

PROMPT_EXTRACT_DIR = Path("./prompts/extract-all-taint-chains")
PROMPT_DETECT_DIR = Path("./prompts/detect")
PROGRESS_FILE = Path("./detect_progress.json")
RESULTS_FILE = Path("./detect_results.jsonl")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Online vulnerability detection with RAG"
    )
    parser.add_argument(
        "--mini", action="store_true", help="Use inference.mini.parquet (debug subset)"
    )
    parser.add_argument(
        "--start", type=int, default=0, help="Start processing at row index (0-based)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Stop after N samples")
    args = parser.parse_args()

    # --- Load dataset ----------------------------------------------------------
    parquet_name = "inference.mini.parquet" if args.mini else "inference.parquet"
    parquet_path = DATA_DIR / parquet_name
    if not parquet_path.exists():
        print(f"ERROR: {parquet_path} not found. Run create_mini_dataset.py first?")
        sys.exit(1)

    df = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df)} samples from {parquet_path}")
    print(f"Label distribution:\n{df['label'].value_counts().to_string()}")

    # --- Infrastructure --------------------------------------------------------
    collection = require_collection(name=COLLECTION_NAME)
    print(f"ChromaDB collection '{COLLECTION_NAME}': {collection.count()} entries")

    embedding_model = get_embedding_model()

    # --- Prompt templates (load once) ------------------------------------------
    extract_messages = load_prompt_messages(PROMPT_EXTRACT_DIR)
    detect_messages = load_prompt_messages(PROMPT_DETECT_DIR)

    # --- Progress / resumption -------------------------------------------------
    progress = ProgressTracker(PROGRESS_FILE)
    processed = progress.load()
    if processed:
        print(f"Resuming — {len(processed)} samples already processed")

    # --- Restore previous results ----------------------------------------------
    y_true_all: list[bool] = []
    y_pred_all: list[bool] = []
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    y_true_all.append(rec["label"])
                    y_pred_all.append(rec["vulnerable"])
        print(f"Restored {len(y_true_all)} previous results")

    # --- Process samples -------------------------------------------------------
    start_idx = max(args.start, 0)
    end_idx = len(df) if args.limit is None else min(start_idx + args.limit, len(df))

    total_processed = 0
    total_errors = 0

    results_fp = open(RESULTS_FILE, "a", encoding="utf-8")

    try:
        for idx in range(start_idx, end_idx):
            if idx in processed:
                continue

            row = df.iloc[idx]
            row_id = int(row.get("id", idx))
            source_code = str(row["source"])
            true_label = bool(row["label"])

            print(f"\n--- Sample {idx} (id={row_id}, label={true_label}) ---")

            try:
                # ----------------------------------------------------------------
                # Step 1: Generate CPG
                # ----------------------------------------------------------------
                print("  Generating CPG...")
                cpg_json_str = generate_cpg_json(source_code)
                print(f"  CPG size: {len(cpg_json_str)} chars")

                # ----------------------------------------------------------------
                # Step 2: Extract taint-chain descriptions via LLM
                # ----------------------------------------------------------------
                msgs_extract = inject_placeholders(
                    extract_messages, **{PH_CPG: cpg_json_str}
                )

                print("  Extract LLM...")
                response_text = call_llm_with_retry(msgs_extract)
                extract_output = extract_json(response_text)
                descriptions: list[str] = extract_output.get("descriptions", [])
                print(f"  Descriptions extracted: {len(descriptions)}")

                # ----------------------------------------------------------------
                # Step 3: Encode descriptions → query ChromaDB
                # ----------------------------------------------------------------
                if not descriptions:
                    print(
                        "  WARNING: No descriptions extracted, skipping RAG retrieval"
                    )
                    all_knowledges: list[str] = []
                else:
                    query_embeddings = embedding_model.encode(descriptions)
                    print(
                        f"  Encoded {len(descriptions)} descriptions "
                        f"(shape: {query_embeddings.shape})"
                    )

                    all_knowledges = []
                    seen: set[str] = set()
                    for emb in query_embeddings:
                        results = collection.query(
                            query_embeddings=[emb.tolist()],
                            n_results=TOP_K,
                        )
                        docs = results.get("documents", [[]])[0]
                        for doc in docs:
                            if doc and doc not in seen:
                                seen.add(doc)
                                all_knowledges.append(doc)
                    print(
                        f"  Retrieved {len(all_knowledges)} unique knowledge entries "
                        f"(from {len(descriptions)} queries x top-{TOP_K})"
                    )

                # ----------------------------------------------------------------
                # Step 4: Detect vulnerability via LLM
                # ----------------------------------------------------------------
                knowledge_text = (
                    "\n\n---\n\n".join(all_knowledges)
                    if all_knowledges
                    else "（未检索到相关漏洞知识）"
                )

                msgs_detect = inject_placeholders(
                    detect_messages,
                    **{PH_CPG: cpg_json_str, PH_KNOWLEDGE: knowledge_text},
                )

                print("  Detect LLM...")
                response_text = call_llm_with_retry(msgs_detect)
                detect_output = extract_json(response_text)
                pred_vulnerable = bool(detect_output.get("vulnerable", False))
                inference = detect_output.get("inference", "")

                status = "CORRECT" if pred_vulnerable == true_label else "WRONG"
                print(
                    f"  Prediction: vulnerable={pred_vulnerable} "
                    f"(true={true_label}) -> {status}"
                )

                # ----------------------------------------------------------------
                # Step 5: Record result
                # ----------------------------------------------------------------
                result_record = {
                    "index": idx,
                    "id": row_id,
                    "source": source_code,
                    "label": true_label,
                    "vulnerable": pred_vulnerable,
                    "inference": inference,
                    "descriptions_extracted": descriptions,
                    "knowledges_retrieved": all_knowledges,
                }
                results_fp.write(json.dumps(result_record, ensure_ascii=False) + "\n")
                results_fp.flush()

                y_true_all.append(true_label)
                y_pred_all.append(pred_vulnerable)

                processed.add(idx)
                total_processed += 1

                if total_processed % 5 == 0:
                    progress.save(processed)

            except Exception as e:
                total_errors += 1
                print(f"  ERROR on sample {idx}: {e}")
                traceback.print_exc()

    finally:
        results_fp.close()

    # --- Final save ------------------------------------------------------------
    progress.save(processed)

    # --- Metrics ---------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"Processed {total_processed} new samples ({total_errors} errors)")

    if y_true_all:
        metrics = compute_metrics(y_true_all, y_pred_all)
        print(f"\nMetrics ({len(y_true_all)} total predictions):")
        print(f"  Accuracy:  {metrics['accuracy']}")
        print(f"  Precision: {metrics['precision']}")
        print(f"  Recall:    {metrics['recall']}")
        print(f"  F1:        {metrics['f1']}")
        print(f"  MCC:       {metrics['mcc']}")
        print(
            f"  Confusion Matrix: TP={metrics['tp']}, TN={metrics['tn']}, "
            f"FP={metrics['fp']}, FN={metrics['fn']}"
        )
    else:
        print("\nNo predictions recorded — cannot compute metrics.")


if __name__ == "__main__":
    main()
