"""Evaluate claim extraction performance against benchmark datasets.

Evaluates GMEE's HuggingFaceLLMClient on LIAR and ClaimBuster test sets.
Computes Precision, Recall, F1, and confusion matrix against ground truth labels.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

# Add backend to sys.path so app modules can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.nlp.llm_client import HuggingFaceLLMClient  # noqa: E402


def get_ground_truth(dataset: str, row: pd.Series) -> int:
    """Map dataset row to binary claim_worthy label (1 or 0)."""
    if dataset == "liar":
        val = str(row.get("label", "")).strip().lower()
        if val in ("true", "mostly-true", "half-true"):
            return 1
        elif val in ("barely-true", "false", "pants-fire"):
            return 0
        else:
            return 0
    elif dataset == "claimbuster":
        score = float(row.get("cfs_score", 0.0))
        return 1 if score >= 0.5 else 0
    else:
        raise ValueError(f"Unknown dataset: {dataset}")


def get_text(dataset: str, row: pd.Series) -> str:
    """Extract claim text from dataset row."""
    if dataset == "liar":
        return str(row.get("statement", "")).strip()
    elif dataset == "claimbuster":
        return str(row.get("text", "")).strip()
    else:
        raise ValueError(f"Unknown dataset: {dataset}")


async def evaluate(
    dataset: str,
    data_path: str,
    sample_size: int,
) -> Tuple[Dict[str, Any], HuggingFaceLLMClient]:
    """Run evaluation loop over dataset samples."""
    df = pd.read_csv(data_path)
    total_available = len(df)

    if sample_size > 0 and sample_size < total_available:
        df = df.iloc[:sample_size].copy()
    else:
        sample_size = total_available

    client = HuggingFaceLLMClient()
    # Eagerly load model weights so loading time is separated from inference loop
    client._load()

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    print(f"Running evaluation on {sample_size} samples from {data_path}...")
    start_time = time.time()

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        text = get_text(dataset, row)
        truth = get_ground_truth(dataset, row)

        extracted = await client.extract_claims(text)
        pred = 1 if len(extracted) > 0 else 0

        if truth == 1 and pred == 1:
            tp += 1
        elif truth == 0 and pred == 1:
            fp += 1
        elif truth == 1 and pred == 0:
            fn += 1
        elif truth == 0 and pred == 0:
            tn += 1

        if idx % 50 == 0 or idx == sample_size:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            eta = (sample_size - idx) / rate if rate > 0 else 0
            print(
                f"[{idx:>4}/{sample_size}] "
                f"TP={tp} FP={fp} FN={fn} TN={tn} | "
                f"Elapsed: {elapsed:.1f}s | "
                f"ETA: {eta:.1f}s"
            )

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    notes = ""
    if sample_size < 200:
        notes = f"Evaluated on {sample_size} samples (< 200 threshold)."

    results = {
        "dataset": dataset,
        "sample_size": sample_size,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "model_used": client.MODEL_ID,
        "eval_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": notes,
    }

    return results, client


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate GMEE claim extraction on benchmark datasets.")
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=["liar", "claimbuster"],
        help="Dataset type ('liar' or 'claimbuster')",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Path to CSV dataset file",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path for JSON results file",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="Number of samples to evaluate (default: 500)",
    )

    args = parser.parse_args()

    results, client = asyncio.run(
        evaluate(
            dataset=args.dataset,
            data_path=args.data_path,
            sample_size=args.sample_size,
        )
    )

    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("CLAIM EXTRACTION EVALUATION RESULTS")
    print("=" * 60)
    print(f"Dataset:       {results['dataset']}")
    print(f"Model:         {results['model_used']}")
    print(f"Sample Size:   {results['sample_size']}")
    print(f"Precision:     {results['precision']:.4f}")
    print(f"Recall:        {results['recall']:.4f}")
    print(f"F1 Score:      {results['f1']:.4f}")
    print(f"Confusion:     TP={results['tp']} FP={results['fp']} FN={results['fn']} TN={results['tn']}")
    print(f"Saved to:      {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
