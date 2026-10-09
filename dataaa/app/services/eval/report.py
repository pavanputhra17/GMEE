"""Gold-standard evaluation report: consensus labels -> publication metrics.

Split mirrors `services/eval/metrics.py`: `build_report` takes plain rows so the
methodology is testable without a database, and `collect_labeled_pairs` is the
thin SQL layer shared by `GET /eval/report` and `scripts/run_eval.py`.

What this fixes: the project shipped a probabilistic scorer whose quality was
asserted rather than measured (eval_report.json held n=8 pairs). This module
produces AUROC with a bootstrap CI, best-F1, F1 at the engine operating point,
Brier score, expected calibration error, reliability bins, a threshold sweep and
pairwise McNemar significance — and it says out loud when the sample is too
small to conclude anything.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.eval.metrics import (
    auroc,
    best_f1_threshold,
    bootstrap_ci,
    brier_score,
    expected_calibration_error,
    f1_at_threshold,
    reliability_bins,
    sweep_thresholds,
)

POSITIVE_LABELS = ("SAME_STORY", "EVOLVED")
ENGINE_OPERATING_POINT = 0.60
THRESHOLD_SWEEP = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)

# Below this many consensus pairs the confidence interval is wider than the
# effect anyone would want to claim; the report says so instead of pretending.
MIN_MEANINGFUL_PAIRS = 100


def consensus(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per pair: majority label across annotators.

    Ties resolve conservatively: DISTINCT wins when it is part of the tie (it is
    the negative class), otherwise every tied label is positive and the binary
    decision is identical — the alphabetical pick only keeps it deterministic.
    The previous `max(set(votes), key=votes.count)` tie-break depended on set
    iteration order, which Python randomises per process — numbers in a paper
    cannot be allowed to move for that reason.
    """
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_pair.setdefault(str(r["pid"]), []).append(r)

    out: list[dict[str, Any]] = []
    for rs in by_pair.values():
        votes = [str(r["label"]) for r in rs]
        counts = Counter(votes)
        top = max(counts.values())
        winners = sorted(lab for lab, n in counts.items() if n == top)
        if len(winners) > 1 and "DISTINCT" in winners:
            label = "DISTINCT"
        else:
            label = winners[0]
        base = dict(rs[0])
        base["label"] = label
        base["votes"] = votes
        out.append(base)
    return out


def build_report(
    rows: list[dict[str, Any]], n_boot: int = 500, seed: int = 1729
) -> dict[str, Any]:
    """Metrics for the stored engine similarity score over consensus labels.

    `rows` need `pid`, `bucket`, `sim` and `label` keys (one per annotator vote).
    """
    pairs = consensus(rows)
    report: dict[str, Any] = {
        "n_pairs": len(pairs),
        "n_positive": 0,
        "n_votes": len(rows),
        "operating_point": ENGINE_OPERATING_POINT,
        "method": "engine similarity (all-mpnet-base-v2 cosine, stored per pair)",
    }
    if not pairs:
        report["message"] = "no labeled pairs yet — label pairs in the Eval Lab tab"
        report["warning"] = (
            "Nothing is measurable until annotators label pairs; the labeling "
            "endpoints are blinded by design (tests/test_eval_api.py)."
        )
        return report

    labels = [str(p["label"]) in POSITIVE_LABELS for p in pairs]
    scores = [float(p["sim"]) for p in pairs]
    report["n_positive"] = sum(labels)
    report["metrics"] = {
        "auroc": round(auroc(scores, labels), 4),
        "auroc_ci95": bootstrap_ci(scores, labels, auroc, n_boot=n_boot, seed=seed),
        "auroc_ci95_f1": bootstrap_ci(
            scores,
            labels,
            lambda s, y: f1_at_threshold(s, y, ENGINE_OPERATING_POINT)["f1"],
            n_boot=n_boot,
            seed=seed,
        ),
        "best_f1": best_f1_threshold(scores, labels),
        "f1_at_operating_point": f1_at_threshold(scores, labels, ENGINE_OPERATING_POINT),
        "brier": brier_score(scores, labels),
        "ece": expected_calibration_error(scores, labels),
    }
    report["reliability"] = reliability_bins(scores, labels)
    report["sweep"] = sweep_thresholds(scores, labels, list(THRESHOLD_SWEEP))

    buckets: dict[str, dict[str, int]] = {}
    for p in pairs:
        entry = buckets.setdefault(
            str(p["bucket"]), {"n": 0, "SAME_STORY": 0, "EVOLVED": 0, "DISTINCT": 0}
        )
        entry["n"] += 1
        entry[str(p["label"])] += 1
    report["by_bucket"] = buckets

    if len(pairs) < MIN_MEANINGFUL_PAIRS:
        report["warning"] = (
            f"n={len(pairs)} consensus pairs — AUROC/ECE/F1 are indicative only "
            f"until ~{MIN_MEANINGFUL_PAIRS}+ pairs are labeled (bootstrap CIs show "
            "the width). Do not quote these numbers as results."
        )
    return report


async def collect_labeled_pairs(db: Any) -> list[dict[str, Any]]:
    """Every (pair, annotator, label) row plus the pair's stored similarity.

    Deliberately dialect-safe: no `::text` casts, so the SQLite test suite can
    exercise the endpoint path. UUIDs are stringified in Python instead.
    """
    from sqlalchemy import text

    rows = (
        await db.execute(
            text(
                """
                SELECT p.id AS pid, p.bucket AS bucket,
                       p.sim_score AS sim, l.label AS label
                FROM eval_pairs p
                JOIN eval_pair_labels l ON l.pair_id = p.id
                """
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]
