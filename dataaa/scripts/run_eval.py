# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Gold-standard evaluation runner.

Scores the human-labeled eval_pairs against two retrieval baselines:

  * sbert — cosine similarity of the production embeddings (all-mpnet-base-v2,
    the same vectors the clustering engine uses)
  * tfidf — character+word TF-IDF cosine (scikit-learn), the classic cheap
    baseline any published system must beat

and reports, per method: AUROC with a bootstrap CI, best-F1 (threshold swept),
F1 at the engine's operating point (0.60), Brier score and expected calibration
error. Pairwise McNemar tests say whether the differences are significant, and
the report shouts when the sample is too small to mean anything (it usually is,
until hundreds of pairs are labeled). Writes eval_report.json.

Consensus labels (majority vote, ties -> DISTINCT) come from
app/services/eval/report.py so the API and this script can never disagree.

Usage: python scripts/run_eval.py
"""

import ast
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.services.eval.metrics import (
    auroc,
    best_f1_threshold,
    bootstrap_ci,
    brier_score,
    expected_calibration_error,
    f1_at_threshold,
    mcnemar_test,
    reliability_bins,
)
from app.services.eval.report import (
    ENGINE_OPERATING_POINT,
    MIN_MEANINGFUL_PAIRS,
    POSITIVE_LABELS,
    consensus,
)

OUT = Path(__file__).resolve().parent.parent / "eval_report.json"


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
                    SELECT p.id::text AS pid, p.bucket, p.sim_score AS sim,
                           ta.claim_text AS text_a, tb.claim_text AS text_b,
                           ta.embedding AS emb_a, tb.embedding AS emb_b,
                           l.annotator, l.label
                    FROM eval_pairs p
                    JOIN claims ta ON ta.id = p.claim_a_id
                    JOIN claims tb ON tb.id = p.claim_b_id
                    JOIN eval_pair_labels l ON l.pair_id = p.id
                    """
                )
            )
        ).all()
    return [dict(r._mapping) for r in rows]


# `consensus` lives in app/services/eval/report.py: deterministic tie-break
# (Counter + explicit DISTINCT preference), shared with GET /eval/report.


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


def evaluate(rows: list[dict]) -> dict:
    pairs = consensus(rows)
    labels = [str(r["label"]) in POSITIVE_LABELS for r in pairs]
    methods = {
        "sbert": sbert_scores(pairs),
        "tfidf": tfidf_scores([r["text_a"] for r in pairs], [r["text_b"] for r in pairs]),
        "engine_embedding": np.asarray([float(r["sim"]) for r in pairs], dtype=np.float32),
    }
    scored = {name: list(map(float, s)) for name, s in methods.items()}

    report: dict = {"n_pairs": len(pairs), "n_votes": len(rows), "n_positive": sum(labels)}
    for name, s in scored.items():
        report[name] = {
            "auroc": round(auroc(s, labels), 4),
            "auroc_ci95": bootstrap_ci(s, labels, auroc, n_boot=400),
            "best_f1": {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in best_f1_threshold(s, labels).items()
            },
            "f1_at_engine_threshold": {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in f1_at_threshold(s, labels, ENGINE_OPERATING_POINT).items()
            },
            "brier": brier_score(s, labels),
            "ece": expected_calibration_error(s, labels),
        }

    # paired significance at the shared operating point
    report["significance"] = {
        "engine_embedding_vs_tfidf": mcnemar_test(
            scored["engine_embedding"], scored["tfidf"], labels, ENGINE_OPERATING_POINT
        ),
        "sbert_vs_tfidf": mcnemar_test(
            scored["sbert"], scored["tfidf"], labels, ENGINE_OPERATING_POINT
        ),
    }
    report["reliability_engine_embedding"] = reliability_bins(
        scored["engine_embedding"], labels
    )

    # per-bucket agreement between engine similarity and humans
    buckets: dict[str, dict[str, int]] = {}
    for r in pairs:
        b = buckets.setdefault(r["bucket"], {"n": 0, "SAME_STORY": 0, "EVOLVED": 0, "DISTINCT": 0})
        b["n"] += 1
        b[r["label"]] += 1
    report["by_bucket"] = buckets

    if len(pairs) < MIN_MEANINGFUL_PAIRS:
        report["warning"] = (
            f"n={len(pairs)} consensus pairs — indicative only until "
            f"~{MIN_MEANINGFUL_PAIRS}+ pairs are labeled; do not quote as a result"
        )
    return report


async def main() -> None:
    rows = await load_labeled()
    if not rows:
        print("no labeled pairs yet — label some via POST /api/v1/eval/label")
        return
    report = evaluate(rows)  # evaluate() applies the shared consensus itself
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"pairs evaluated (consensus): {report['n_pairs']}  "
          f"positive (same story): {report['n_positive']}  votes: {report['n_votes']}")
    print(f"{'method':<18}{'AUROC':>7}{'95% CI':>16}{'best-F1':>9}{'F1@0.60':>9}"
          f"{'Brier':>7}{'ECE':>7}")

    def _fmt(v: object) -> str:
        return f"{float(v):.3f}" if isinstance(v, (int, float)) else "  n/a"

    for name in ("sbert", "tfidf", "engine_embedding"):
        m = report[name]
        ci = m["auroc_ci95"] or {}
        ci_txt = (
            f"[{ci['low']:.2f},{ci['high']:.2f}]"
            if "low" in ci and "high" in ci
            else "n/a"
        )
        bf = m["best_f1"]
        f1e = m["f1_at_engine_threshold"]
        print(f"{name:<18}{m['auroc']:>7.3f}{ci_txt:>16}{(bf['f1'] or 0):>9.3f}"
              f"{(f1e['f1'] or 0):>9.3f}{_fmt(m['brier']):>7}{_fmt(m['ece']):>7}")

    sig = report["significance"]["engine_embedding_vs_tfidf"]
    print(f"\nMcNemar engine vs tfidf @0.60: b={sig['b']:.0f} c={sig['c']:.0f} "
          f"p={sig['p_value']:.4f}")
    if report.get("warning"):
        print(f"WARNING: {report['warning']}")
    print(f"\nreport written to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())