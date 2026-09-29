"""Tests for the early-warning alert engine (pure logic + endpoint)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.alerts import build_alerts

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _recent(n: int) -> list[datetime]:
    return [NOW - timedelta(hours=2) for _ in range(n)]


def _prior(n: int) -> list[datetime]:
    return [NOW - timedelta(hours=30) for _ in range(n)]


def test_quiet_when_nothing_anomalous():
    out = build_alerts(published_ats=[], disputed_ats=[], mutation_ats=[], now=NOW)
    assert [a["type"] for a in out["alerts"]] == ["QUIET"]
    assert out["stats"]["articles_24h"] == 0


def test_ingestion_spike():
    out = build_alerts(
        published_ats=_recent(6) + _prior(1), disputed_ats=[], mutation_ats=[], now=NOW
    )
    spike = [a for a in out["alerts"] if a["type"] == "INGESTION_SPIKE"]
    assert spike and spike[0]["severity"] == "warn"


def test_no_spike_when_baseline_matches():
    out = build_alerts(
        published_ats=_recent(6) + _prior(6), disputed_ats=[], mutation_ats=[], now=NOW
    )
    assert not [a for a in out["alerts"] if a["type"] == "INGESTION_SPIKE"]


def test_disputed_surge():
    out = build_alerts(
        published_ats=[], disputed_ats=_recent(3), mutation_ats=[], now=NOW
    )
    surge = [a for a in out["alerts"] if a["type"] == "DISPUTED_SURGE"]
    assert surge and surge[0]["severity"] == "warn"


def test_mutation_surge_is_critical():
    out = build_alerts(
        published_ats=[], disputed_ats=[], mutation_ats=_recent(4), now=NOW
    )
    surge = [a for a in out["alerts"] if a["type"] == "MUTATION_SURGE"]
    assert surge and surge[0]["severity"] == "critical"


def test_naive_datetimes_treated_as_utc():
    out = build_alerts(
        published_ats=[datetime(2026, 9, 16, 10, 0, tzinfo=UTC)],
        disputed_ats=[],
        mutation_ats=[],
        now=NOW,
    )
    assert out["stats"]["articles_24h"] == 1


def test_explicit_utc_offset_matches_now():
    from datetime import timedelta, timezone

    plus5 = timezone(timedelta(hours=5, minutes=30))
    out = build_alerts(
        published_ats=[datetime(2026, 9, 16, 12, 30, tzinfo=plus5)],
        disputed_ats=[],
        mutation_ats=[],
        now=NOW,
    )
    # 12:30 +05:30 == 07:00 UTC — still inside the 24h window
    assert out["stats"]["articles_24h"] == 1


@pytest.mark.asyncio
async def test_alerts_endpoint(async_client, db_session, monkeypatch):
    """End-to-end on the SQLite test app with seeded rows."""
    import uuid

    from sqlalchemy import text

    from tests.conftest import TestingSessionLocal

    sid = str(uuid.uuid4())
    async with TestingSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO sources (id, name, type, url_or_identifier, is_active) "
                "VALUES (:id, 'test', 'rss', 'https://t.example/rss', 1)"
            ),
            {"id": sid},
        )
        art_ids = []
        for i, hours in enumerate([2, 3, 4, 5, 6, 30]):
            aid = str(uuid.uuid4())
            art_ids.append(aid)
            await db.execute(
                text(
                    "INSERT INTO articles (id, source_id, title, url, content_hash,"
                    " published_at) VALUES (:id, :sid, :title, :url, :ch, :pub)"
                ),
                {
                    "id": aid,
                    "sid": sid,
                    "title": f"t{i}",
                    "url": f"https://t.example/{i}",
                    "ch": f"hash-{i}",
                    "pub": (datetime.now(UTC) - timedelta(hours=hours)).isoformat(),
                },
            )
        # 3 recent DISPUTED claims on the first article
        for i in range(3):
            await db.execute(
                text(
                    "INSERT INTO claims (id, article_id, claim_text, verdict)"
                    " VALUES (:id, :aid, :txt, 'DISPUTED')"
                ),
                {"id": str(uuid.uuid4()), "aid": art_ids[0], "txt": f"claim {i}"},
            )
        await db.commit()

    monkeypatch.setattr("app.db.postgres.async_session_maker", TestingSessionLocal)
    resp = await async_client.get("/api/v1/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "alerts" in data and "stats" in data and "generated_at" in data
    assert data["stats"]["articles_24h"] == 5
    assert data["stats"]["disputed_24h"] == 3
    types = {a["type"] for a in data["alerts"]}
    assert "INGESTION_SPIKE" in types
    assert "DISPUTED_SURGE" in types