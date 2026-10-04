"""Evidence-gated scoring contracts; similarity/style must never invent support."""

from typing import Any

import pytest

from app.services.verdict.engine import (
    DISPUTED_MAX_PROBABILITY,
    METHOD_VERSION,
    SCORE_KIND,
    VERDICT_BANDS,
    VerdictEngine,
    band_for,
    engine_config,
    near_window,
)


def test_every_emitted_band_is_advertised():
    advertised = {b["band"] for b in engine_config()["bands"]}
    assert advertised == {
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
                assert band_for(i / 100, has_contra, has_corr) in advertised


def test_thresholds_are_descending():
    thresholds = [threshold for threshold, _ in VERDICT_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)


def test_disputed_requires_an_explicit_contradiction():
    assert band_for(0.10, has_contradiction=False) == "UNSUPPORTED"
    assert band_for(0.10, has_contradiction=True) == "DISPUTED"
    assert band_for(DISPUTED_MAX_PROBABILITY, has_contradiction=True) == "UNRESOLVED"


@pytest.mark.parametrize("score", [0.55, 0.72, 0.99])
def test_high_score_without_entailment_never_supports(score):
    assert band_for(score, has_corroboration=False) == "UNRESOLVED"


@pytest.mark.parametrize("score", [0.55, 0.72, 0.99])
def test_mixed_evidence_never_becomes_supported_from_style(score):
    assert (
        band_for(score, has_contradiction=True, has_corroboration=True) == "UNRESOLVED"
    )


def test_positive_bands_require_entailment():
    assert band_for(0.8, has_corroboration=True) == "SUPPORTED"
    assert band_for(0.6, has_corroboration=True) == "PARTIALLY_SUPPORTED"
    assert band_for(0.2, has_corroboration=True) == "WEAKLY_CORROBORATED"


def test_config_reports_actual_retrieval_and_stance_method():
    cfg = engine_config()
    assert cfg["near_similarity_window"] == {
        "min": near_window()[0],
        "max": near_window()[1],
    }
    assert cfg["score_kind"] == SCORE_KIND
    assert cfg["method_version"] == METHOD_VERSION
    assert cfg["similarity_role"].startswith("retrieval_only")
    assert "explicit entailment only" in cfg["corroboration_rule"]
    assert "strong_similarity_corroboration" not in cfg
    assert cfg["nli"]["model"] == "cross-encoder/nli-deberta-v3-base"
    assert cfg["nli"]["confidence_min"] == 0.7
    assert cfg["stance_cache"]["ttl_seconds"] > 0
    assert cfg["stance_cache"]["max_entries"] > 0
    assert "never self-verdicts" in cfg["source_prior_policy"]


def test_track_record_is_neutral_without_independent_provenance():
    for stats in (
        None,
        {},
        {"supported": 40, "disputed": 0},
        {
            "supported": 40,
            "disputed": 0,
            "independently_validated": True,
        },
    ):
        signal = VerdictEngine.track_record_signal(stats)
        assert signal.value == 0.5
        assert signal.detail["prior_source"] == "neutral_no_independent_data"


def test_independent_track_record_is_smoothed_and_disclosed():
    metadata = {
        "independently_validated": True,
        "provenance": "Independent reviewed dataset",
    }
    strong = VerdictEngine.track_record_signal(
        {"supported": 40, "disputed": 0, **metadata}
    )
    weak = VerdictEngine.track_record_signal(
        {"supported": 0, "disputed": 40, **metadata}
    )
    assert strong.value > 0.9
    assert weak.value < 0.1
    assert strong.detail["provenance"] == metadata["provenance"]
    assert strong.detail["prior_source"] == "supplied_independent_data"


def _neighbours(sim: float, nli: str | None, count: int = 1) -> list[dict[str, Any]]:
    return [
        {"domain": f"outlet{i}.example", "sim": sim, "nli": nli} for i in range(count)
    ]


@pytest.mark.parametrize("similarity", [0.66, 0.93, 1.0])
@pytest.mark.parametrize("stance", [None, "neutral", "unknown"])
def test_similarity_alone_is_never_corroboration(similarity, stance):
    corr, contra = VerdictEngine.corroboration_signal(
        _neighbours(similarity, stance), "a.example"
    )
    assert corr.value == 0.30
    assert corr.detail["independent_outlets_supporting"] == []
    assert corr.detail["nearby_unrelated"] == 1
    assert contra.value == 0.5
    assert contra.detail["contradiction_ratio"] == 0.0


@pytest.mark.parametrize("stance", ["yes", "entailment"])
def test_true_entailment_counts_even_without_high_cosine(stance):
    corr, _ = VerdictEngine.corroboration_signal(
        [
            {"domain": "outlet.example", "sim": 0.66, "stance": stance},
        ],
        "a.example",
    )
    assert corr.detail["independent_outlets_supporting"] == ["outlet.example"]
    assert corr.value > 0.5


@pytest.mark.parametrize("stance", ["no", "contradiction"])
def test_explicit_contradiction_reaches_full_penalty(stance):
    corr, contra = VerdictEngine.corroboration_signal(
        [
            {"domain": "outlet.example", "sim": 0.99, "stance": stance},
        ],
        "a.example",
    )
    assert not corr.detail["independent_outlets_supporting"]
    assert contra.detail["contradiction_ratio"] == 1.0
    assert contra.value == 0.0


def test_canonical_neutral_is_not_overridden_by_legacy_or_cosine():
    corr, contra = VerdictEngine.corroboration_signal(
        [
            {"domain": "b.example", "sim": 1.0, "stance": "neutral", "nli": "yes"},
        ],
        "a.example",
    )
    assert corr.value == 0.30
    assert contra.value == 0.5


def test_same_normalized_outlet_never_corroborates():
    corr, contra = VerdictEngine.corroboration_signal(
        [
            {"domain": "WWW.A.EXAMPLE", "sim": 0.99, "nli": "yes"},
        ],
        "a.example",
    )
    assert corr.value == 0.30
    assert contra.value == 0.5


def test_syndicated_repetition_counts_once():
    corr, _ = VerdictEngine.corroboration_signal(
        [
            {
                "domain": f"outlet{i}.example",
                "stance": "entailment",
                "syndication_group": "wire-copy",
            }
            for i in range(4)
        ],
        "a.example",
    )
    assert len(corr.detail["independent_outlets_supporting"]) == 1
    assert corr.detail["supporting_syndication_groups"] == ["wire-copy"]


def test_own_syndication_group_cannot_corroborate():
    corr, _ = VerdictEngine.corroboration_signal(
        [
            {
                "domain": "b.example",
                "stance": "entailment",
                "syndication_group": "own-copy",
            },
        ],
        "a.example",
        own_syndication_group="own-copy",
    )
    assert corr.detail["independent_outlets_supporting"] == []


def test_absence_of_contradiction_is_not_evidence_against_claim():
    corr, contra = VerdictEngine.corroboration_signal([], "a.example")
    result = VerdictEngine.combine(
        [
            corr,
            contra,
            VerdictEngine.track_record_signal(None),
            VerdictEngine.entity_signal([]),
            VerdictEngine.linguistic_signal("The ministry confirmed the figure."),
        ]
    )
    assert result.probability > 0.35
    assert result.band == "UNRESOLVED"
    assert result.evidence["score_kind"] == SCORE_KIND
    assert result.evidence["method_version"] == METHOD_VERSION
    assert "P(supported)" not in result.rationale
    assert "uncalibrated" in result.rationale.lower()


def test_entity_language_and_prior_scores_cannot_create_support():
    result = VerdictEngine.combine(
        [
            VerdictEngine.entity_signal([{"entity_type": "ORG"}] * 20),
            VerdictEngine.linguistic_signal(
                "The ministry confirmed 500 cases in London on Monday."
            ),
            VerdictEngine.track_record_signal(
                {
                    "supported": 1000,
                    "disputed": 0,
                    "independently_validated": True,
                    "provenance": "Externally reviewed",
                }
            ),
        ]
    )
    assert result.probability > 0.72
    assert result.band == "UNRESOLVED"
    assert "No cross-domain entailment" in result.rationale


def test_empty_signals_abstain_without_dividing_by_zero():
    result = VerdictEngine.combine([])
    assert result.probability == 0.5
    assert result.band == "UNRESOLVED"
