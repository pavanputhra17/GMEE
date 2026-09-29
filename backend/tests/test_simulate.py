"""Tests for the propagation sandbox model (pure logic)."""

from app.services.simulate import simulate_cascade

CHAIN = {"a": ["b"], "b": ["c"], "c": ["d"]}


def test_full_reach_at_p_one():
    r = simulate_cascade(CHAIN, "a", p=1.0, max_depth=3)
    assert [lv["reached"] for lv in r["levels"]] == [1, 1, 1]
    # p is clamped to 0.95 (the model never claims certainty), so expected
    # decays as p**level: 0.95, 0.95^2, 0.95^3 (rounded to 2dp)
    assert [lv["expected"] for lv in r["levels"]] == [0.95, 0.9, 0.86]
    assert r["total_expected_reach"] == 3.71
    assert r["deterministic_reach"] == 4


def test_depth_caps_reach():
    r = simulate_cascade(CHAIN, "a", p=1.0, max_depth=2)
    assert len(r["levels"]) == 2
    assert r["deterministic_reach"] == 3


def test_star_expected_values():
    adj = {"hub": ["a", "b", "c", "d"]}
    r = simulate_cascade(adj, "hub", p=0.5, max_depth=2)
    # level 1: 4 nodes * 0.5 = 2 expected; level 2: leaves have no children
    assert r["levels"][0] == {"level": 1, "reached": 4, "expected": 2.0}
    assert r["levels"][1]["reached"] == 0
    assert r["total_expected_reach"] == 3.0
    # mean fanout 4 -> r = 0.5 * 4
    assert r["r_effective"] == 2.0


def test_r_effective_below_one_for_sparse_chain():
    r = simulate_cascade(CHAIN, "a", p=0.5, max_depth=3)
    # mean fanout 1 -> r = 0.5 < 1
    assert r["r_effective"] == 0.5


def test_unknown_root_is_safe():
    r = simulate_cascade(CHAIN, "zzz", p=0.9, max_depth=3)
    assert r["levels"] == []
    assert r["deterministic_reach"] == 1


def test_p_clamped():
    r = simulate_cascade(CHAIN, "a", p=99, max_depth=1)
    assert r["p"] == 0.95