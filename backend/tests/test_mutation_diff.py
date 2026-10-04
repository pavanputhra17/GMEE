"""Unit tests for the word-level mutation diff service."""

from app.services.verdict.mutation_diff import diff_versions, tokenize


def test_tokenize_handles_numbers_and_punct():
    toks = tokenize("At least 12 dead, $5 million lost!")
    assert "12" in toks
    assert "$" in toks or "million" in toks
    assert " " not in toks


def test_numeric_drift_detected():
    a = "The earthquake killed 12 people in Colombia."
    b = "The earthquake killed 40 people in Colombia."
    d = diff_versions(a, b)
    assert "NUMERIC_DRIFT" in d["mutation_types"]
    changed = [s for s in d["segments"] if s["type"] == "changed"]
    assert any("12" in s["old"] and "40" in s["new"] for s in changed)
    assert d["similarity"] > 0.5  # mostly identical wording


def test_hedging_shift_detected():
    a = "Officials reportedly found survivors in the rubble."
    b = "Officials found survivors in the rubble."
    d = diff_versions(a, b)
    assert "HEDGING_SHIFT" in d["mutation_types"]
    lost = [h for h in d["hedge_changes"] if h["direction"] == "lost"]
    assert any(h["word"] == "reportedly" for h in lost)


def test_entity_substitution_detected():
    a = "President Garcia met the ambassador on Monday."
    b = "President Torres met the ambassador on Monday."
    d = diff_versions(a, b)
    assert "ENTITY_SUBSTITUTION" in d["mutation_types"]
    assert {"removed": "Garcia", "added": ""} in d["entity_changes"]
    assert {"removed": "", "added": "Torres"} in d["entity_changes"]


def test_identical_text_is_near_duplicate():
    t = "The comet will be visible from Earth on Friday night."
    d = diff_versions(t, t)
    assert d["mutation_types"] == ["NEAR_DUPLICATE"]
    assert d["similarity"] == 1.0


def test_framing_shift_flagged_for_low_similarity():
    a = "Markets rallied sharply after the central bank held rates steady."
    b = "Cryptocurrency investors fled the country following the scandal."
    d = diff_versions(a, b)
    assert "FRAMING_SHIFT" in d["mutation_types"]


def test_segments_render_same_and_changed_runs():
    a = "Two soldiers died in the ambush near the border."
    b = "Two soldiers died in the attack near the eastern border."
    d = diff_versions(a, b)
    types = [s["type"] for s in d["segments"]]
    assert "same" in types and "changed" in types
    # changed segment carries a kind
    for s in d["segments"]:
        if s["type"] == "changed":
            assert s["kinds"]  # non-empty kind list


def test_old_output_keys_are_preserved_with_additive_typed_analysis():
    d = diff_versions(
        "According to Alice, all bridges reportedly did not close at 10 am.",
        "Bob said some bridges did close at 12 am.",
    )
    assert {
        "numeric_changes",
        "entity_changes",
        "hedge_changes",
        "similarity",
        "mutation_types",
        "segments",
    } <= d.keys()
    assert {
        "POLARITY_SHIFT",
        "HEDGING_SHIFT",
        "ATTRIBUTION_SHIFT",
        "SCOPE_SHIFT",
        "NUMERIC_DRIFT",
        "ENTITY_SUBSTITUTION",
    } <= set(d["mutation_types"])
    assert d["analysis"]["changed_spans"]
    assert d["polarity_changes"]
    assert d["attribution_changes"]
    assert d["scope_changes"]
    assert d["observed_propagation"] is False
    assert d["algorithm_version"] == d["analysis"]["algorithm_version"]
    for segment in d["segments"]:
        assert {"type", "old", "new", "kinds"} <= segment.keys()


def test_decimal_currency_is_a_single_numeric_token():
    assert "$1,200.50" in tokenize("It cost $1,200.50.")
    assert "3.5%" in tokenize("Rates rose by 3.5%.")
