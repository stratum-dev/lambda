#!/usr/bin/env python3
"""
Run online vulnerability detection.

For each code sample from the HuggingFace dataset codemetic/lambda (inference
split), generates a CPG, extracts taint-chain descriptions via LLM, queries the
ChromaDB knowledge base for similar vulnerability patterns, and makes a final
vulnerability determination via a second LLM call.

After processing, computes F1, MCC, Recall, and Precision against the ground-
truth labels.

Usage:
  python detect.py [--subset NAME] [--language LANG] [--start N] [--limit N] [--workers N]

Flags:
  --subset NAME   Dataset subset/config to load (default: js-to-cpp).
                  Available: cpp-only, java-to-cpp, js-to-cpp, debug.
  --language LANG  Programming language for CPG generation (default: javascript).
                  Supported: javascript, cpp, java, python.
  --start N       Start processing at row index N (0-based, for resumption).
  --limit N       Stop after processing N samples.
  --workers N     Max parallel LLM requests (default: LLM_MAX_WORKERS env or 4).
"""

import argparse
import json
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
    TOP_K,
)
from lambda_utils.cpg import generate_cpg_json
from lambda_utils.embeddings import get_embedding_model
from lambda_utils.llm import call_llm_with_retry, extract_json
from lambda_utils.metrics import compute_metrics
from lambda_utils.progress import ProgressTracker
from lambda_utils.prompts import (
    load_prompt_messages,
    render_messages,
)
from lambda_utils.vectordb import require_collection

load_dotenv()

# ---------------------------------------------------------------------------
# Per-pipeline constants
# ---------------------------------------------------------------------------

PROMPT_EXTRACT_DIR = Path("./prompts/extract-all-taint-chains")
PROMPT_DETECT_DIR = Path("./prompts/detect")
PROGRESS_FILE = Path("./detect_progress.t.json")
RESULTS_FILE = Path("./detect_results.t.jsonl")


# ---------------------------------------------------------------------------
# Per-sample worker
# ---------------------------------------------------------------------------


def _process_one(
    idx: int,
    row,
    subset: str,
    language: str,
    extract_messages: list[dict],
    detect_messages: list[dict],
    embedding_model,
    collection,
    lock: threading.Lock,
    results_fp,
) -> dict:
    """Process a single sample — CPG → extract-LLM → RAG → detect-LLM.

    Returns a result record dict on success.  Raises on failure.
    """
    row_id = int(row.get("id", idx))
    source_code = str(row["source"])
    true_label = bool(row["label"])

    # --- Step 1: Generate CPG -------------------------------------------------
    cpg_json_str = generate_cpg_json(source_code, language=language)

    # --- Step 2: Extract taint-chain descriptions via LLM ----------------------
    msgs_extract = render_messages(extract_messages, cpg=cpg_json_str)
    response_text = call_llm_with_retry(msgs_extract)
    extract_output = extract_json(response_text)
    descriptions: list[str] = extract_output.get("descriptions", [])

    # --- Step 3: Encode → query ChromaDB (filtered by subset) -----------------
    if not descriptions:
        all_knowledge: list[str] = []
    else:
        query_embeddings = embedding_model.encode(descriptions)

        all_knowledge = []
        seen: set[str] = set()
        for emb in query_embeddings:
            with lock:
                results = collection.query(
                    query_embeddings=[emb.tolist()],
                    n_results=TOP_K,
                    where={"subset": subset},
                )
            docs = results.get("documents", [[]])[0]
            for doc in docs:
                if doc and doc not in seen:
                    seen.add(doc)
                    all_knowledge.append(doc)

    # --- Step 4: Detect vulnerability via LLM --------------------------------
    knowledge_text = (
        "\n\n---\n\n".join(all_knowledge)
        if all_knowledge
        else "（未检索到相关漏洞知识）"
    )

    msgs_detect = render_messages(
        detect_messages,
        cpg=cpg_json_str,
        knowledge=knowledge_text,
    )
    response_text = call_llm_with_retry(msgs_detect)
    detect_output = extract_json(response_text)
    pred_vulnerable = bool(detect_output.get("vulnerable", False))
    inference = detect_output.get("inference", "")

    # --- Step 5: Build result record -----------------------------------------
    record = {
        "index": idx,
        "id": row_id,
        "source": source_code,
        "label": true_label,
        "vulnerable": pred_vulnerable,
        "inference": inference,
        "descriptions_extracted": descriptions,
        "knowledge_retrieved": all_knowledge,
    }

    # --- Step 6: Write result (serialised) -----------------------------------
    with lock:
        results_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        results_fp.flush()

    return record


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Online vulnerability detection with RAG"
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
        f"Loading '{args.subset}' subset from {HF_DATASET_REPO} (inference split) ..."
    )
    try:
        dataset = load_dataset(HF_DATASET_REPO, args.subset, split="inference")
    except Exception as e:
        print(f"ERROR: Failed to load dataset: {e}")
        sys.exit(1)

    df = dataset.to_pandas()
    print(f"Loaded {len(df)} samples, columns={list(df.columns)}")
    print(f"Label distribution:\n{df['label'].value_counts().to_string()}")
    print(f"Max workers: {args.workers}")

    # --- Infrastructure --------------------------------------------------------
    collection = require_collection(name=COLLECTION_NAME)
    print(f"ChromaDB collection '{COLLECTION_NAME}': {collection.count()} entries")

    embedding_model = get_embedding_model()

    # --- Prompt templates (load once — read-only, share across threads) --------
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
    results_fp = open(RESULTS_FILE, "a", encoding="utf-8")

    try:
        # --- Parallel execution -------------------------------------------------
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_idx = {}
            for idx in pending:
                future = executor.submit(
                    _process_one,
                    idx,
                    df.iloc[idx],
                    args.subset,
                    args.language,
                    extract_messages,
                    detect_messages,
                    embedding_model,
                    collection,
                    lock,
                    results_fp,
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                row = df.iloc[idx]
                true_label = bool(row["label"])

                try:
                    record = future.result()
                    status = (
                        "CORRECT" if record["vulnerable"] == true_label else "WRONG"
                    )

                    with lock:
                        processed.add(idx)
                        y_true_all.append(record["label"])
                        y_pred_all.append(record["vulnerable"])
                        counters["done"] += 1
                        if counters["done"] % 5 == 0:
                            progress.save(processed)

                    print(
                        f"[{counters['done']}/{len(pending)}] "
                        f"Sample {idx} (id={record['id']}, label={true_label}) "
                        f"-> vulnerable={record['vulnerable']} {status} "
                        f"({len(record['descriptions_extracted'])} descriptions, "
                        f"{len(record['knowledge_retrieved'])} knowledge)"
                    )
                except Exception:
                    with lock:
                        counters["errors"] += 1
                    print(f"[{counters['done']}/{len(pending)}] " f"Sample {idx} ERROR")
                    traceback.print_exc()

    finally:
        results_fp.close()

    # --- Final save ------------------------------------------------------------
    progress.save(processed)

    # --- Metrics ---------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"Processed {counters['done']} new samples ({counters['errors']} errors)")

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
