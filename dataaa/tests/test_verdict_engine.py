"""Verdict-engine contract tests: the disclosed config must match the code.

GET /verdicts/summary is the project's XAI contract — it promises reviewers
that every weight, band and similarity window is disclosed. These tests pin
that promise down: no scorer output may be missing from the advertised band
list, and the reported similarity window must be the one the engine uses.
"""

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
