"""Verdict-engine contract tests: the disclosed config must match the code.

GET /verdicts/summary is the project's XAI contract — it promises reviewers
that every weight, band and similarity window is disclosed. These tests pin
that promise down: no scorer output may be missing from the advertised band
list, and the reported similarity window must be the one the engine uses.
"""

from typing import Any

from app.services.verdict.engine import (
    DISPUTED_MAX_PROBABILITY,
    VERDICT_BANDS,
    VerdictEngine,
    band_for,
    engine_config,
    near_window,
)


def test_every_emitted_band_is_advertised():
    cfg = engine_config()
    advertised = {b["band"] for b in cfg["bands"]}
    assert advertised >= {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "UNRESOLVED",
        "WEAKLY_CORROBORATED",
        "UNSUPPORTED",
        "DISPUTED",
    }

    for i in range(101):
        for has_contra in (False, True):
            for has_corr in (False, True):
                band = band_for(i / 100, has_contra, has_corr)
                assert band in advertised


def test_thresholds_are_descending():
    thresholds = [t for t, _ in VERDICT_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)


def test_disputed_requires_an_explicit_contradiction():
    # absence of evidence is not evidence of absence
    assert band_for(0.10, has_contradiction=False) == "UNSUPPORTED"
    assert band_for(0.10, has_contradiction=True) == "DISPUTED"
    # at the cut-off the band is no longer DISPUTED
    assert band_for(DISPUTED_MAX_PROBABILITY, has_contradiction=True) == "UNRESOLVED"


def test_config_reports_the_window_it_uses():
    cfg = engine_config()
    window = cfg["near_similarity_window"]
    assert window == {"min": near_window()[0], "max": near_window()[1]}
    assert 0 < window["min"] < window["max"] < 1


def test_track_record_signal_is_laplace_smoothed():
    empty = VerdictEngine.track_record_signal(None)
    assert empty.value == 0.5

    strong = VerdictEngine.track_record_signal({"supported": 40, "disputed": 0})
    weak = VerdictEngine.track_record_signal({"supported": 0, "disputed": 40})
    assert strong.value > 0.9
    assert weak.value < 0.1


def test_track_record_bands_cover_every_engine_label():
    from app.services.verdict.engine import DISPUTED_BANDS, SUPPORTED_BANDS

    cfg = engine_config()
    advertised = {b["band"] for b in cfg["bands"]}
    assert set(SUPPORTED_BANDS) <= advertised
    assert set(DISPUTED_BANDS) <= advertised


# ------------------------------------------------ corroboration / contradiction

def _neighbours(sim: float, nli: str | None, count: int = 1) -> list[dict[str, Any]]:
    return [
        {"domain": f"outlet{i}.example", "sim": sim, "nli": nli}
        for i in range(count)
    ]


def test_contradiction_signal_is_neutral_when_nothing_contradicts():
    _, contra = VerdictEngine.corroboration_signal(_neighbours(0.70, None), "a.example")
    assert contra.value == 0.5  # re-centred: no downward pull without evidence
    assert contra.detail["contradiction_ratio"] == 0.0


def test_contradiction_ratio_reaches_a_full_penalty():
    _, contra = VerdictEngine.corroboration_signal(_neighbours(0.80, "no"), "a.example")
    assert contra.detail["contradiction_ratio"] == 1.0
    assert contra.value == 0.0


def test_strong_similarity_alone_counts_as_corroboration():
    corr, _ = VerdictEngine.corroboration_signal(_neighbours(0.93, None), "a.example")
    assert corr.detail["independent_outlets_supporting"] == ["outlet0.example"]


def test_weak_neighbour_without_nli_is_not_corroboration():
    corr, _ = VerdictEngine.corroboration_signal(_neighbours(0.66, None), "a.example")
    assert corr.value == 0.30
    assert corr.detail["nearby_unrelated"] == 1


def test_nli_yes_still_counts_below_the_strong_similarity_threshold():
    corr, _ = VerdictEngine.corroboration_signal(_neighbours(0.66, "yes"), "a.example")
    assert corr.detail["independent_outlets_supporting"] == ["outlet0.example"]


def test_same_outlet_never_corroborates():
    corr, contra = VerdictEngine.corroboration_signal(
        [{"domain": "a.example", "sim": 0.99, "nli": "yes"}], "a.example"
    )
    assert corr.value == 0.30
    assert contra.value == 0.5


def test_absence_of_contradiction_is_not_evidence_against_a_claim():
    """Regression: the raw ratio made "no contradiction" the largest single
    downward term in the pool (logit(0.01) * 0.20 ~= -0.92), which collapsed
    ~62% of the live corpus to UNSUPPORTED."""
    corr, contra = VerdictEngine.corroboration_signal([], "a.example")
    result = VerdictEngine.combine([
        corr,
        contra,
        VerdictEngine.track_record_signal(None),
        VerdictEngine.entity_signal([]),
        VerdictEngine.linguistic_signal("The ministry confirmed the figure."),
    ])
    assert result.probability > 0.35
    assert result.band == "UNRESOLVED"


def test_config_discloses_the_strong_similarity_rule():
    cfg = engine_config()
    assert 0.5 < cfg["strong_similarity_corroboration"] <= 1.0
