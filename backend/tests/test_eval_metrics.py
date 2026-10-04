"""Hand-computed raw-score ranking and calibrated-probability metric contracts."""

import math

import pytest

from app.services.eval.metrics import (
    auroc,
    average_precision,
    best_f1_threshold,
    brier_score,
    expected_calibration_error,
    f1_at_threshold,
    precision_recall_curve,
    reliability_bins,
)


def test_average_precision_tied_scores_reference():
    scores, labels = [0.9, 0.8, 0.8, 0.1], [True, False, True, False]
    assert average_precision(scores, labels) == pytest.approx(5 / 6)
    curve = precision_recall_curve(scores, labels)
    assert [p["threshold"] for p in curve] == [0.9, 0.8, 0.1]
    assert curve[1]["precision"] == pytest.approx(2 / 3)
    assert curve[1]["recall"] == 1.0


def test_ranking_and_threshold_metrics_accept_negative_cosine_scores():
    scores, labels = [-0.8, -0.2, 0.2, 0.8], [False, False, True, True]
    assert auroc(scores, labels) == average_precision(scores, labels) == 1.0
    assert best_f1_threshold(scores, labels)["threshold"] == 0.2
    assert f1_at_threshold(scores, labels, 0.0)["f1"] == 1.0


@pytest.mark.parametrize("scores", [[-0.1, 0.9], [0.1, 1.1], [math.nan, 0.1], [0.1, math.inf]])
def test_probability_metrics_do_not_clamp_invalid_scores_into_probabilities(scores):
    labels = [False, True]
    assert brier_score(scores, labels) is None
    assert expected_calibration_error(scores, labels) is None
    assert reliability_bins(scores, labels) == []


def test_average_precision_empty_and_mismatch_not_fabricated():
    assert average_precision([], []) is None
    assert average_precision([0.1], [True, False]) is None
    assert average_precision([0.1], [False]) is None
