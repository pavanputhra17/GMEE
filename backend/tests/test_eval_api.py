"""The annotator-blinding contract for the gold-standard evaluation API.

`GET /eval/next` must never leak the stored similarity score, bucket or any
engine verdict: an annotator who sees them labels the machine's opinion, not
the claims. These tests pin that invariant (plus the DB-free validation paths
and route registration) so the blind cannot be removed by accident.

The DB-backed paths are deliberately not exercised here: the labeling SQL is
Postgres-specific (`id::text`, UUID casts) while the suite runs on SQLite.
See tests/test_alerts.py for a full SQLite-safe endpoint test pattern.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.eval import VALID_LABELS, EvalLabelBody, _blinded, _per_annotator

PAIR_ID = "11111111-1111-1111-1111-111111111111"


def _fake_row(**extra: object) -> SimpleNamespace:
    """A row shaped like the one _PAIR_SQL returns (plus optional cues)."""
    row = SimpleNamespace(
        id=PAIR_ID,
        text_a="claim A",
        domain_a="a.example",
        text_b="claim B",
        domain_b="b.example",
    )
    for key, value in extra.items():
        setattr(row, key, value)
    return row


def test_blinded_returns_only_texts_and_domains():
    payload = _blinded(_fake_row(bucket="b85", sim_score=0.93, verdict="DISPUTED"))
    assert set(payload) == {"pair_id", "a", "b"}
    assert payload["pair_id"] == PAIR_ID
    assert payload["a"] == {"text": "claim A", "domain": "a.example"}
    assert payload["b"] == {"text": "claim B", "domain": "b.example"}


def test_blinded_payload_carries_no_engine_cues():
    payload = _blinded(
        _fake_row(bucket="b85", sim_score=0.93, verdict="DISPUTED", stance="CONTRADICT")
    )
    flat = repr(payload).lower()
    for cue in ("0.93", "b85", "score", "bucket", "verdict", "stance"):
        assert cue not in flat


def test_every_declared_label_is_accepted():
    for label in VALID_LABELS:
        body = EvalLabelBody(pair_id=PAIR_ID, annotator="tester", label=label)
        assert body.label == label


def test_per_annotator_keeps_every_label_per_annotator():
    """Regression: flattening to one {label, count} lost all but the last vote."""
    out = _per_annotator(
        [
            ("tester1", "DISTINCT", 3),
            ("tester1", "SAME_STORY", 2),
            ("tester2", "EVOLVED", 1),
        ]
    )
    assert out["tester1"] == {"labels": {"DISTINCT": 3, "SAME_STORY": 2}, "total": 5}
    assert out["tester2"] == {"labels": {"EVOLVED": 1}, "total": 1}


def test_per_annotator_is_empty_without_labels():
    assert _per_annotator([]) == {}


def test_unknown_label_is_rejected():
    with pytest.raises(ValidationError):
        EvalLabelBody(pair_id=PAIR_ID, annotator="tester", label="MAYBE")


def test_annotator_must_be_non_empty():
    with pytest.raises(ValidationError):
        EvalLabelBody(pair_id=PAIR_ID, annotator="", label="DISTINCT")


@pytest.mark.asyncio
async def test_next_rejects_empty_annotator(async_client):
    # validated before the DB is touched, so this runs on SQLite
    resp = await async_client.get("/api/v1/eval/next?annotator=")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_label_rejects_non_uuid_pair_id(async_client):
    resp = await async_client.post(
        "/api/v1/eval/label",
        json={"pair_id": "x" * 32, "annotator": "tester", "label": "DISTINCT"},
    )
    assert resp.status_code == 400


def test_eval_routes_are_mounted():
    """The public API surface is asserted through the OpenAPI schema.

    `app.routes` is deliberately not used: FastAPI >= 0.14x / Starlette 1.x
    keeps included routers as nested mounts instead of flattening them, so
    route objects no longer carry a `.path` for every endpoint.
    """
    from app.main import app

    paths = set(app.openapi()["paths"])
    for path in ("/api/v1/eval/next", "/api/v1/eval/label", "/api/v1/eval/progress"):
        assert path in paths
