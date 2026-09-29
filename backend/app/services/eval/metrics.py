"""Gold-standard evaluation metrics — pure functions, fully unit-testable.

No DB, no models: these take plain lists so the evaluation methodology can be
verified independently of the data pipeline (see tests/test_eval_metrics.py).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    """Precision / recall / F1 with zero-division safety."""
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def auroc(scores: list[float], labels: list[bool]) -> float:
    """Rank-based AUROC (handles ties via average ranks).

    labels: True = positive class (same story). scores: higher = more likely
    positive. Returns 0.5 for empty or single-class input.
    """
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    n = len(pairs)
    pos = sum(1 for _, y in pairs if y)
    neg = n - pos
    if not pos or not neg:
        return 0.5

    # average ranks (1-based) for tie groups
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    rank_sum_pos = sum(r for r, (_, y) in zip(ranks, pairs) if y)
    return (rank_sum_pos - pos * (pos + 1) / 2) / (pos * neg)


def best_f1_threshold(scores: list[float], labels: list[bool]) -> dict[str, float | None]:
    """Sweep every distinct score as a decision threshold, return the best F1.

    A pair is predicted positive when score >= threshold. Ties in F1 resolve
    to the highest threshold (most conservative).
    """
    if not scores or all(y == labels[0] for y in labels):
        return {"threshold": None, **{k: (None if k != "f1" else 0.0) for k in ("precision", "recall", "f1")}}

    best: dict[str, float | None] = {"threshold": None, "precision": None, "recall": None, "f1": -1.0}
    for thr in sorted(set(scores)):
        tp = sum(1 for s, y in zip(scores, labels) if s >= thr and y)
        fp = sum(1 for s, y in zip(scores, labels) if s >= thr and not y)
        fn = sum(1 for s, y in zip(scores, labels) if s < thr and y)
        m = prf(tp, fp, fn)
        f1 = m["f1"] or 0.0
        if f1 >= (best["f1"] or -1.0):
            best = {"threshold": thr, **m}
    return best


def f1_at_threshold(scores: list[float], labels: list[bool], threshold: float) -> dict[str, float | None]:
    """P/R/F1 at a fixed operating threshold (e.g. the engine's 0.60 window)."""
    tp = sum(1 for s, y in zip(scores, labels) if s >= threshold and y)
    fp = sum(1 for s, y in zip(scores, labels) if s >= threshold and not y)
    fn = sum(1 for s, y in zip(scores, labels) if s < threshold and y)
    return prf(tp, fp, fn)


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for inter-annotator agreement over aligned label lists."""
    if len(a) != len(b) or not a:
        return None
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum(
        (a.count(c) / n) * (b.count(c) / n) for c in cats
    )
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Calibration & significance. A probabilistic scorer is only as good as its
# calibration: these metrics are what make the "calibrated probability" claim
# checkable rather than rhetorical.
# ---------------------------------------------------------------------------

MetricFn = Callable[[list[float], list[bool]], float | None]


def brier_score(scores: list[float], labels: list[bool]) -> float | None:
    """Mean squared error of probabilistic predictions (0 = perfect)."""
    if not scores or len(scores) != len(labels):
        return None
    total = sum(
        (min(max(float(s), 0.0), 1.0) - (1.0 if y else 0.0)) ** 2
        for s, y in zip(scores, labels)
    )
    return round(total / len(scores), 4)


def reliability_bins(
    scores: list[float], labels: list[bool], n_bins: int = 10
) -> list[dict[str, float]]:
    """Reliability-diagram data: per-bin mean score vs empirical positive rate.

    Empty bins are omitted. Scores are clamped to [0, 1]; score 0 falls in the
    first bin. `n` is returned as a float so the whole row stays numeric.
    """
    if not scores or len(scores) != len(labels) or n_bins < 1:
        return []
    clamped = [min(max(float(s), 0.0), 1.0) for s in scores]
    bins: list[dict[str, float]] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        members = [
            (s, y)
            for s, y in zip(clamped, labels)
            if (lo < s <= hi) or (i == 0 and s <= hi)
        ]
        if not members:
            continue
        mean_score = sum(s for s, _ in members) / len(members)
        empirical = sum(1 for _, y in members if y) / len(members)
        bins.append({
            "lo": round(lo, 3),
            "hi": round(hi, 3),
            "n": len(members),
            "mean_score": round(mean_score, 4),
            "empirical_rate": round(empirical, 4),
            "gap": round(mean_score - empirical, 4),
        })
    return bins


def expected_calibration_error(
    scores: list[float], labels: list[bool], n_bins: int = 10
) -> float | None:
    """Sample-weighted |confidence − accuracy| across bins (lower is better)."""
    bins = reliability_bins(scores, labels, n_bins)
    if not bins:
        return None
    n = sum(b["n"] for b in bins)
    if n <= 0:
        return None
    ece = sum(b["n"] * abs(b["gap"]) for b in bins) / n
    return round(ece, 4)


def sweep_thresholds(
    scores: list[float], labels: list[bool], thresholds: list[float]
) -> list[dict[str, float | None]]:
    """Precision/recall/F1 at each candidate operating point."""
    return [
        {"threshold": t, **f1_at_threshold(scores, labels, t)}
        for t in thresholds
    ]


def bootstrap_ci(
    scores: list[float],
    labels: list[bool],
    metric: MetricFn | None = None,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 1729,
) -> dict[str, float] | None:
    """Percentile bootstrap CI for a metric. Deterministic seed by default so
    published numbers are reproducible run to run."""
    fn: MetricFn = metric or auroc
    n = len(scores)
    if n < 4 or len(labels) != n or not 0 < alpha < 1:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(max(1, n_boot)):
        idx = [rng.randrange(n) for _ in range(n)]
        v = fn([scores[i] for i in idx], [labels[i] for i in idx])
        if v is not None:
            values.append(float(v))
    if len(values) < 10:
        return None
    values.sort()
    lo_i = min(len(values) - 1, int((alpha / 2) * len(values)))
    hi_i = max(0, min(len(values) - 1, int((1 - alpha / 2) * len(values)) - 1))
    return {
        "low": round(values[lo_i], 4),
        "high": round(values[hi_i], 4),
        "mean": round(sum(values) / len(values), 4),
        "n_boot": len(values),
    }


def mcnemar_test(
    scores_a: list[float],
    scores_b: list[float],
    labels: list[bool],
    threshold: float,
) -> dict[str, float]:
    """Paired significance test between two scorers at a shared operating point.

    χ² with continuity correction (df = 1). The p-value comes from the exact
    χ²₁ survival function (``erfc(√(stat/2))``), so no SciPy dependency is
    needed. `b` = A right & B wrong, `c` = B right & A wrong.
    """
    if not labels or not (len(scores_a) == len(scores_b) == len(labels)):
        return {"b": 0.0, "c": 0.0, "statistic": 0.0, "p_value": 1.0}
    b = c = 0
    for sa, sb, y in zip(scores_a, scores_b, labels):
        ok_a = (sa >= threshold) == y
        ok_b = (sb >= threshold) == y
        if ok_a and not ok_b:
            b += 1
        elif ok_b and not ok_a:
            c += 1
    if b + c == 0:
        return {"b": float(b), "c": float(c), "statistic": 0.0, "p_value": 1.0}
    statistic = (abs(b - c) - 1) ** 2 / (b + c)
    p_value = math.erfc(math.sqrt(statistic / 2)) if statistic > 0 else 1.0
    return {
        "b": float(b),
        "c": float(c),
        "statistic": round(statistic, 4),
        "p_value": round(p_value, 6),
    }