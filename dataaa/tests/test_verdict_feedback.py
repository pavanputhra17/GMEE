"""Tests for human verdict feedback + the XAI summary endpoint.

Uses the SQLite test app; the Postgres ON CONFLICT upsert is exercised
against the real database in development (SQLite lacks the dialect insert).
"""

import pytest


@pytest.mark.asyncio
async def test_engine_config_is_complete():
    from app.services.verdict.engine import engine_config

    cfg = engine_config()
    assert set(cfg["weights"]) == {
        "corroboration", "contradiction", "source_track_record",
        "entity_grounding", "language",
    }
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert cfg["bands"][0]["band"] == "SUPPORTED"
    assert cfg["near_similarity_window"]["max"] >= cfg["near_similarity_window"]["min"]


@pytest.mark.asyncio
async def test_feedback_rejects_non_json(async_client):
    resp = await async_client.post("/api/v1/verdicts/feedback", content=b"not json")
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_summary_endpoint_shape(async_client, db_session, monkeypatch):
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(
        "app.api.v1.verdicts.async_session_maker", TestingSessionLocal
    )
    resp = await async_client.get("/api/v1/verdicts/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "engine_config" in data
    assert "distribution" in data
    assert "human_feedback" in data
    hf = data["human_feedback"]
    for key in ("total_votes", "agree", "disagree", "agreement_rate",
                "confirmed_disagreements"):
        assert key in hf