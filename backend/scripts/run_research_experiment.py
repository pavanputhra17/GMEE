"""Reproducible, offline train/dev/test evaluation of frozen human-gold JSONL.

From the repository root:
  backend/.venv/Scripts/python.exe backend/scripts/run_research_experiment.py \
    --dataset dataset-v1.jsonl --output-dir experiment-v1 --seed 1729 --bootstrap 1000

Requires schema_version=gmee-research-v1, one dataset_version, explicit
pair_id/event_id/split, claim/article IDs, actual text_a/text_b, stored
cosine_score, gold_label and >=2 unanimous authenticated human_labels.
Optional features: lexical_jaccard/entity_jaccard; optional independently
agreed gold_mutation_types. No DB, model downloads, or weak-gold override.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.eval.artifacts import write_artifacts
from app.services.eval.dataset import DatasetError
from app.services.eval.research import ExperimentConfig, load_jsonl, run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, leakage-checked human-gold GMEE experiment")
    parser.add_argument("--dataset", type=Path, required=True, help="Versioned UTF-8 human-gold JSONL snapshot")
    parser.add_argument("--output-dir", type=Path, required=True, help="New/empty output directory; previous results are never overwritten")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--bootstrap", type=int, default=1000, help="Paired connected-event component resamples (20–10000)")
    args = parser.parse_args(argv)
    try:
        config = ExperimentConfig(seed=args.seed, bootstrap=args.bootstrap)
        config.validate()
        if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
            raise DatasetError("--output-dir must be new/empty; preserve existing results by selecting a new run directory")
        records, digest = load_jsonl(args.dataset)
        report, predictions, states = run_experiment(records, config=config, dataset_sha256=digest)
        manifest = write_artifacts(report, predictions, states, args.output_dir)
    except (DatasetError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"Completed frozen human-gold evaluation of {report['dataset_version']} ({digest})")
    print("Fitted on train; thresholds selected on dev; test evaluated once after selection.")
    print(f"Artifacts: {args.output_dir}; {len(manifest['artifacts'])} hashed files plus manifest.json")
    print("This run does not certify publication validity; review report warnings and dataset provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
