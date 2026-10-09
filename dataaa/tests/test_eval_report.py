"""Calibration + significance metrics and the gold-standard report.

A probabilistic scorer must be *measured*, not asserted: these tests pin the
hand-computed reference values for Brier score, ECE and reliability bins, the
determinism of the bootstrap CI, McNemar discordance counting, and the report's
honesty guard (it refuses to present n<100 numbers as results).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.eval.metrics import (
    bootstrap_ci,
    brier_score,
    expected_calibration_error,
    mcnemar_test,
    reliability_bins,
)
from app.services.eval.report import build_report, consensus


def _perfect_rows() -> list[dict[str, Any]]:
    """Perfectly separable toy corpus; two annotators agree on every pair."""
    spec = [
        ("p1", "b95", 0.95, "SAME_STORY"),
        ("p2", "b85", 0.90, "EVOLVED"),
        ("p3", "b40", 0.45, "DISTINCT"),
        ("p4", "b00", 0.10, "DISTINCT"),
    ]
    rows: list[dict[str, Any]] = []
    for pid, bucket, sim, label in spec:
        for annotator in ("a1", "a2"):
            rows.append({
                "pid": pid, "bucket": bucket, "sim": sim,
                "label": label, "annotator": annotator,
            })
    return rows


def test_brier_score_reference_value():
    # (1.0-1)² + (0-0)² + (0.8-1)² = 0 + 0 + 0.04 over 3 predictions
    assert brier_score([1.0, 0.0, 0.8], [True, False, True]) == pytest.approx(
        0.0133, abs=1e-4
    )


def test_brier_score_rejects_mismatched_lengths():
    assert brier_score([0.5], [True, False]) is None
    assert brier_score([], []) is None


def test_ece_is_zero_for_a_perfectly_calibrated_scorer():
    scores = [1.0] * 50 + [0.0] * 50
    labels = [True] * 50 + [False] * 50
    assert expected_calibration_error(scores, labels) == 0.0


def test_reliability_bins_reference_value():
    # 0.10 -> bin [0.0,0.1] (gap +0.10), 0.45 -> [0.4,0.5] (+0.45),
    # 0.90 -> [0.8,0.9] (-0.10), 0.95 -> [0.9,1.0] (-0.05)
    scores = [0.10, 0.45, 0.90, 0.95]
    labels = [False, False, True, True]
    bins = reliability_bins(scores, labels)
    assert sum(b["n"] for b in bins) == 4
    assert [b["lo"] for b in bins] == sorted(b["lo"] for b in bins)
    assert expected_calibration_error(scores, labels) == pytest.approx(0.175, abs=1e-4)


def test_reliability_bins_handle_edge_scores():
    bins = reliability_bins([0.0, 1.0], [False, True])
    assert sum(b["n"] for b in bins) == 2
    assert bins[0]["mean_score"] == 0.0
    assert bins[-1]["mean_score"] == 1.0


def test_bootstrap_ci_is_deterministic_and_brackets_values():
    rows = _perfect_rows()
    scores = [float(r["sim"]) for r in rows]
    labels = [r["label"] in ("SAME_STORY", "EVOLVED") for r in rows]
    first = bootstrap_ci(scores, labels, n_boot=200, seed=1729)
    second = bootstrap_ci(scores, labels, n_boot=200, seed=1729)
    assert first == second  # same seed -> identical numbers, always
    assert first is not None
    assert 0.0 <= first["low"] <= first["high"] <= 1.0
    assert 0.0 <= first["mean"] <= 1.0
    assert first["n_boot"] > 0


def test_bootstrap_ci_needs_a_minimum_sample():
    assert bootstrap_ci([0.9], [True], n_boot=50) is None


def test_mcnemar_counts_discordant_pairs_and_flags_difference():
    labels = [True, False] * 10
    perfect = [0.9 if y else 0.1 for y in labels]
    useless = [0.4] * 20  # never crosses the 0.5 threshold
    m = mcnemar_test(perfect, useless, labels, 0.5)
    assert m["b"] == 10.0
    assert m["c"] == 0.0
    assert m["p_value"] < 0.01
    flipped = mcnemar_test(useless, perfect, labels, 0.5)
    assert flipped["b"] == 0.0 and flipped["c"] == 10.0


def test_mcnemar_is_null_when_the_scorers_agree():
    labels = [True, False]
    m = mcnemar_test([0.9, 0.1], [0.8, 0.2], labels, 0.5)
    assert m["statistic"] == 0.0
    assert m["p_value"] == 1.0


def test_consensus_resolves_ties_deterministically():
    # DISTINCT is the negative class: a tie involving it resolves conservatively
    tie_with_negative = [
        {"pid": "q", "sim": 0.9, "bucket": "b95", "label": "DISTINCT"},
        {"pid": "q", "sim": 0.9, "bucket": "b95", "label": "SAME_STORY"},
    ]
    assert consensus(tie_with_negative)[0]["label"] == "DISTINCT"

    # a tie between two positive labels cannot move the binary decision; the
    # alphabetical pick only keeps the value deterministic across processes
    tie_between_positives = [
        {"pid": "r", "sim": 0.9, "bucket": "b95", "label": "SAME_STORY"},
        {"pid": "r", "sim": 0.9, "bucket": "b95", "label": "EVOLVED"},
    ]
    assert consensus(tie_between_positives)[0]["label"] == "EVOLVED"


def test_consensus_deduplicates_annotator_votes_per_pair():
    pairs = consensus(_perfect_rows())
    assert len(pairs) == 4
    assert {p["pid"] for p in pairs} == {"p1", "p2", "p3", "p4"}


def test_build_report_metrics_on_separable_corpus():
    report = build_report(_perfect_rows())
    assert report["n_pairs"] == 4
    assert report["n_positive"] == 2
    assert report["n_votes"] == 8  # two annotators x four pairs

    m = report["metrics"]
    assert m["auroc"] == 1.0
    assert m["best_f1"]["f1"] == 1.0
    assert m["f1_at_operating_point"]["f1"] == 1.0
    assert m["brier"] == pytest.approx(0.05625, abs=1e-4)
    assert m["ece"] == pytest.approx(0.175, abs=1e-4)

    assert report["sweep"] and report["reliability"]
    assert report["by_bucket"]["b95"] == {
        "n": 1, "SAME_STORY": 1, "EVOLVED": 0, "DISTINCT": 0
    }
    # honesty guard: 4 pairs is not a result
    assert "warning" in report and "n=4" in report["warning"]


def test_build_report_without_labels_explains_itself():
    report = build_report([])
    assert report["n_pairs"] == 0
    assert "message" in report
    assert "metrics" not in report


@pytest.mark.asyncio
async def test_report_endpoint_returns_metrics(async_client, db_session, monkeypatch):
    from app.models.eval import EvalPair, EvalPairLabel
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr("app.db.postgres.async_session_maker", TestingSessionLocal)

    pair = EvalPair(
        claim_a_id=uuid.uuid4(),
        claim_b_id=uuid.uuid4(),
        bucket="b95",
        sim_score=0.93,
    )
    db_session.add(pair)
    await db_session.flush()
    db_session.add_all([
        EvalPairLabel(pair_id=pair.id, annotator="t1", label="SAME_STORY"),
        EvalPairLabel(pair_id=pair.id, annotator="t2", label="SAME_STORY"),
    ])
    await db_session.commit()

    resp = await async_client.get("/api/v1/eval/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_pairs"] == 1
    assert body["n_positive"] == 1
    assert "metrics" in body
    # one pair cannot support a confidence interval — reported as null, not faked
    assert body["metrics"]["auroc_ci95"] is None
    assert "warning" in body


def test_report_route_is_mounted():
    from app.main import app

    assert "/api/v1/eval/report" in set(app.openapi()["paths"])

