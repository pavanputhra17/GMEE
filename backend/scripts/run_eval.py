# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Exploratory live-corpus diagnostics, not held-out publication evaluation.

Only unanimous votes from >=2 authenticated humans enter the primary report.
Weak origins are reported separately, never upgraded to human gold. TF-IDF
fits this diagnostic sample and best-F1 uses this same sample, so both are
explicitly exploratory. Cosine/TF-IDF are scores, not probabilities; there
are no Brier/ECE claims for them and no sample-size validity assurances.

For reproducible results use export_research_dataset.py followed by
run_research_experiment.py (train-only fitting, dev selection, untouched test).
Usage: python scripts/run_eval.py [--output eval_exploratory_report.json]
"""

import argparse
import ast
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.services.eval.metrics import mcnemar_test
from app.services.eval.report import ENGINE_OPERATING_POINT, build_report, consensus, score_diagnostics

OUT = Path(__file__).resolve().parent.parent / "eval_exploratory_report.json"


def parse_embedding(raw) -> "np.ndarray":
    """pgvector comes back as a string under asyncpg — parse robustly."""
    if raw is None:
        return np.zeros((768,), dtype=np.float32)
    if isinstance(raw, str):
        return np.asarray(ast.literal_eval(raw), dtype=np.float32)
    return np.asarray(raw, dtype=np.float32)


async def load_labeled() -> list[dict]:
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT p.id AS pid, p.bucket, p.sim_score AS sim,
                           p.split, p.event_group,
                           ta.claim_text AS text_a, tb.claim_text AS text_b,
                           ta.embedding AS emb_a, tb.embedding AS emb_b,
                           l.annotator, l.annotator_user_id, l.origin, l.label, l.mutation_types
                    FROM eval_pairs p
                    JOIN claims ta ON ta.id = p.claim_a_id
                    JOIN claims tb ON tb.id = p.claim_b_id
                    JOIN eval_pair_labels l ON l.pair_id = p.id
                    ORDER BY p.id, l.origin, l.annotator
                    """
                )
            )
        ).all()
    return [dict(r._mapping) for r in rows]


# Primary consensus is shared with the API; weak votes never enter it.


def tfidf_scores(texts_a: list[str], texts_b: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
    all_texts = texts_a + texts_b
    mat = normalize(vec.fit_transform(all_texts))
    n = len(texts_a)
    return np.asarray(np.sum(mat[:n].multiply(mat[n:]), axis=1)).ravel()


def sbert_scores(rows: list[dict]) -> np.ndarray:
    out = []
    for r in rows:
        a = parse_embedding(r["emb_a"])
        b = parse_embedding(r["emb_b"])
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        out.append(float(a @ b) / denom if denom else 0.0)
    return np.asarray(out, dtype=np.float32)


def evaluate(rows: list[dict], n_boot: int = 400, seed: int = 1729) -> dict:
    report = build_report(rows, n_boot=n_boot, seed=seed)
    pairs = consensus(rows)
    if not pairs:
        return report
    labels = [r["label"] in ("SAME_STORY", "EVOLVED") for r in pairs]
    methods = {
        "engine_embedding": [float(r["sim"]) for r in pairs],
        "tfidf": list(map(float, tfidf_scores([r["text_a"] for r in pairs], [r["text_b"] for r in pairs]))),
    }
    if all(r.get("emb_a") is not None and r.get("emb_b") is not None for r in pairs):
        methods["sbert"] = list(map(float, sbert_scores(pairs)))
    else:
        report["embedding_recomputation_message"] = "sbert diagnostic omitted: actual stored embeddings unavailable for some human-gold pairs"
    for name, scores in methods.items():
        diagnostics = score_diagnostics([{**pair, "sim": score} for pair, score in zip(pairs, scores)], n_boot=n_boot, seed=seed)["metrics"]
        report[name] = {**diagnostics, "f1_at_engine_threshold": diagnostics["f1_at_operating_point"], "fitted_on": "same diagnostic sample (TF-IDF only); not train/dev/test"}
    report["paired_same_sample_diagnostics"] = {
        "engine_embedding_vs_tfidf": mcnemar_test(methods["engine_embedding"], methods["tfidf"], labels, ENGINE_OPERATING_POINT),
        "warning": "Exploratory discordance only; correlated event/claim groups and multiple comparisons are not accounted for",
    }
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description="Exploratory live-corpus diagnostics, never publication results")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new --output path to preserve previous diagnostics")
    rows = await load_labeled()
    report = evaluate(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, sort_keys=True, indent=2, allow_nan=False)
    print(f"Exploratory human consensus pairs={report['n_pairs']}; human votes={report['n_votes']}; all-origin votes={report['n_votes_all_origins']}")
    print(f"WARNING: {report['warning']}")
    print(f"Diagnostic report: {args.output}; for research use the frozen-dataset CLI")


if __name__ == "__main__":
    asyncio.run(main())