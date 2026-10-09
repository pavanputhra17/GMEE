"""Evaluate Verdict Engine performance and run signal ablation studies.

Evaluates VerdictEngine on FEVER dev set claims using log-odds signal fusion,
computes per-class and Macro-F1 against ground truth veracity bands,
and performs ablation over all five verification signals.
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

# Add backend to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.nlp.entity_extractor import EntityExtractor  # noqa: E402
from app.services.verdict.engine import (  # noqa: E402
    Signal,
    VerdictEngine,
    VerdictResult,
    nli_stance,
)

FEVER_TO_TARGET = {
    "SUPPORTS": "SUPPORTED",
    "REFUTES": "DISPUTED",
    "NOT ENOUGH INFO": "UNRESOLVED",
}

CLASSES = ["SUPPORTED", "DISPUTED", "UNRESOLVED"]


def map_band_to_target(band: str) -> str:
    """Map VerdictResult band to target 3-class evaluation label."""
    if band in ("SUPPORTED", "PARTIALLY_SUPPORTED", "WEAKLY_CORROBORATED"):
        return "SUPPORTED"
    elif band in ("DISPUTED", "PENDING_DISPUTE"):
        return "DISPUTED"
    else:
        return "UNRESOLVED"


def compute_metrics(
    truths: List[str],
    preds: List[str],
) -> Tuple[float, Dict[str, float], Dict[str, Dict[str, int]]]:
    """Compute per-class F1, macro F1, and 3x3 confusion matrix."""
    matrix = {t: {p: 0 for p in CLASSES} for t in CLASSES}
    for t, p in zip(truths, preds):
        if t in matrix and p in matrix[t]:
            matrix[t][p] += 1

    per_class_f1: Dict[str, float] = {}
    for c in CLASSES:
        tp = matrix[c][c]
        fp = sum(matrix[other][c] for other in CLASSES if other != c)
        fn = sum(matrix[c][other] for other in CLASSES if other != c)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        per_class_f1[c] = round(f1, 4)

    macro_f1 = round(sum(per_class_f1.values()) / len(CLASSES), 4)
    return macro_f1, per_class_f1, matrix


async def extract_claim_signals(
    claims: List[str],
) -> List[List[Signal]]:
    """Compute 5 constituent signals for each claim in batch."""
    from sentence_transformers import SentenceTransformer, util

    print("Loading embedding and NER models for verdict evaluation...")
    EntityExtractor.load_model()
    st_model = SentenceTransformer("all-mpnet-base-v2")

    print(f"Encoding {len(claims)} claims for cross-claim stance & corroboration...")
    embeddings = st_model.encode(claims, convert_to_tensor=True, normalize_embeddings=True)
    sim_matrix = util.cos_sim(embeddings, embeddings).cpu()

    signals_per_claim: List[List[Signal]] = []

    print(f"Extracting signals for {len(claims)} claims...")
    for idx, claim_text in enumerate(claims):
        # 1. Linguistic signal
        lang_sig = VerdictEngine.linguistic_signal(claim_text)

        # 2. Entity grounding signal
        try:
            raw_ents = EntityExtractor.extract_entities(claim_text)
            ents = [{"entity_type": e.entity_type} for e in raw_ents]
        except Exception:
            ents = []
        ent_sig = VerdictEngine.entity_signal(ents)

        # 3. Source track record signal (unassigned/neutral prior for isolated FEVER claims)
        track_sig = VerdictEngine.track_record_signal(None)

        # 4 & 5. Corroboration and contradiction signals
        pool: List[Dict[str, Any]] = []
        # Find nearest neighbor in batch if sim >= 0.70
        best_j = None
        best_sim = 0.0
        for j in range(len(claims)):
            if idx == j:
                continue
            s = float(sim_matrix[idx][j])
            if s > best_sim and s >= 0.70:
                best_sim = s
                best_j = j

        if best_j is not None:
            stance = await nli_stance(claim_text, claims[best_j])
            pool.append({
                "domain": f"fever_doc_{best_j}",
                "sim": round(best_sim, 3),
                "nli": stance,
            })

        corr_sig, contra_sig = VerdictEngine.corroboration_signal(pool, own_domain=f"fever_doc_{idx}")

        claim_signals = [corr_sig, contra_sig, track_sig, ent_sig, lang_sig]
        signals_per_claim.append(claim_signals)

        if (idx + 1) % 50 == 0 or (idx + 1) == len(claims):
            print(f"Processed [{idx + 1:>3}/{len(claims)}] claims")

    return signals_per_claim


def run_ablation(
    truths: List[str],
    all_signals: List[List[Signal]],
) -> Dict[str, Any]:
    """Evaluate full model and zero-weight ablation variants."""
    ablation_configs = {
        "full_model": None,
        "without_corroboration": "corroboration",
        "without_contradiction": "contradiction",
        "without_track_record": "source_track_record",
        "without_entity_grounding": "entity_grounding",
        "without_language": "language",
    }

    ablation_results: Dict[str, Dict[str, float]] = {}
    full_macro = 0.0
    full_per_class: Dict[str, float] = {}
    full_matrix: Dict[str, Dict[str, int]] = {}

    for config_name, disabled_signal in ablation_configs.items():
        preds: List[str] = []
        for signals in all_signals:
            if disabled_signal is None:
                eval_signals = signals
            else:
                eval_signals = [
                    Signal(s.name, s.value, 0.0 if s.name == disabled_signal else s.weight, s.detail)
                    for s in signals
                ]

            result: VerdictResult = VerdictEngine.combine(eval_signals)
            pred_class = map_band_to_target(result.band)
            preds.append(pred_class)

        macro_f1, per_class, matrix = compute_metrics(truths, preds)
        ablation_results[config_name] = {"macro_f1": macro_f1}

        if config_name == "full_model":
            full_macro = macro_f1
            full_per_class = per_class
            full_matrix = matrix

    return {
        "macro_f1": full_macro,
        "per_class_f1": full_per_class,
        "confusion_matrix": full_matrix,
        "ablation": ablation_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Verdict Engine on FEVER benchmark with ablation.")
    parser.add_argument(
        "--data",
        type=str,
        default="evaluation/data/baselines/fever_dev.jsonl",
        help="Path to FEVER dev JSONL dataset (default: evaluation/data/baselines/fever_dev.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation/results/verdict_engine.json",
        help="Path to output JSON results file (default: evaluation/results/verdict_engine.json)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=300,
        help="Number of samples to evaluate (default: 300)",
    )

    args = parser.parse_args()

    # Load dataset
    claims: List[str] = []
    truths: List[str] = []

    with open(args.data, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            if args.sample_size > 0 and len(claims) >= args.sample_size:
                break
            record = json.loads(line)
            raw_label = record.get("label", "").strip()
            if raw_label in FEVER_TO_TARGET:
                claims.append(record.get("claim", "").strip())
                truths.append(FEVER_TO_TARGET[raw_label])

    actual_sample_size = len(claims)
    print(f"Loaded {actual_sample_size} valid samples from {args.data}")

    # Compute signals
    all_signals = asyncio.run(extract_claim_signals(claims))

    # Run ablation and evaluate
    eval_data = run_ablation(truths, all_signals)

    output_dict = {
        "macro_f1": eval_data["macro_f1"],
        "sample_size": actual_sample_size,
        "per_class_f1": eval_data["per_class_f1"],
        "confusion_matrix": eval_data["confusion_matrix"],
        "ablation": eval_data["ablation"],
        "limitation": "FEVER uses Wikipedia evidence; GMEE uses live web corpus. Results are approximate.",
        "eval_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_dict, f, indent=2)

    print("\n" + "=" * 65)
    print("VERDICT ENGINE EVALUATION & ABLATION RESULTS")
    print("=" * 65)
    print(f"Sample Size:     {actual_sample_size}")
    print(f"Macro-F1:        {eval_data['macro_f1']:.4f}")
    print(f"Per-Class F1:    {eval_data['per_class_f1']}")
    print(f"Confusion Matrix:{eval_data['confusion_matrix']}")
    print("\nAblation Results:")
    for variant, metrics in eval_data["ablation"].items():
        print(f"  - {variant:<28}: Macro-F1 = {metrics['macro_f1']:.4f}")
    print(f"\nSaved to:        {args.output}")
    print("=" * 65)


if __name__ == "__main__":
    main()
