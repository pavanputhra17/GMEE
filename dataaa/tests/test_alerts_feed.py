"""Persisted alert feed, acknowledgement and evaluation trigger.

`test_alerts.py` covers the stateless 24h snapshot. These tests pin the
persistence layer that shipped with the `alerts` table but was unreachable from
the API: `/alerts/feed`, the idempotent acknowledge path, the admin gate on the
evaluation trigger, and the dedup semantics of `evaluate_alerts()`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select, text

from app.models.evolution import Alert
from app.services.alerts import evaluate_alerts


async def _seed_alert(
    db,
    *,
    kind: str = "MUTATION",
    severity: str = "WARNING",
    acknowledged: bool = False,
    age_minutes: int = 0,
) -> Alert:
    seen = datetime.now(UTC) - timedelta(minutes=age_minutes)
    alert = Alert(
        kind=kind,
        severity=severity,
        subject_key=f"edge:{uuid.uuid4()}",
        title=f"{kind} alert",
        body="seeded by tests",
        payload={"seed": True},
        acknowledged_at=datetime.now(UTC) if acknowledged else None,
        first_seen_at=seen,
        last_seen_at=seen,
    )
    db.add(alert)
    await db.commit()
    return alert


async def test_feed_empty_corpus(async_client):
    resp = await async_client.get("/api/v1/alerts/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["counts"] == {"unacknowledged": 0, "by_severity": {}, "by_kind": {}}


async def test_feed_orders_newest_first_and_hides_acknowledged(async_client, db_session):
    await _seed_alert(db_session, severity="INFO", age_minutes=30)
    await _seed_alert(db_session, severity="CRITICAL", age_minutes=5)
    await _seed_alert(db_session, severity="WARNING", acknowledged=True, age_minutes=1)

    data = (await async_client.get("/api/v1/alerts/feed")).json()
    assert [i["severity"] for i in data["items"]] == ["CRITICAL", "INFO"]
    assert all(i["acknowledged_at"] is None for i in data["items"])
    assert data["counts"]["unacknowledged"] == 2
    assert data["counts"]["by_severity"] == {"CRITICAL": 1, "INFO": 1}
    assert data["counts"]["by_kind"] == {"MUTATION": 2}

    history = (
        await async_client.get("/api/v1/alerts/feed?include_acknowledged=true")
    ).json()
    assert len(history["items"]) == 3
    assert history["items"][0]["severity"] == "WARNING"  # 1 minute old = newest

    filtered = (await async_client.get("/api/v1/alerts/feed?severity=critical")).json()
    assert [i["severity"] for i in filtered["items"]] == ["CRITICAL"]


async def test_feed_rejects_unknown_severity(async_client):
    resp = await async_client.get("/api/v1/alerts/feed?severity=panic")
    assert resp.status_code == 400
    assert "severity" in resp.json()["detail"]


async def test_acknowledge_marks_once_and_drops_from_feed(async_client, db_session):
    from app.api.deps import get_current_user
    from app.main import app
    from app.models.user import RoleEnum

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=RoleEnum.admin
    )

    alert = await _seed_alert(db_session)

    first = await async_client.post(f"/api/v1/alerts/{alert.id}/acknowledge")
    assert first.status_code == 200
    stamp = first.json()["acknowledged_at"]
    assert first.json()["status"] == "acknowledged"
    assert stamp

    # idempotent: the first acknowledgement timestamp wins
    second = await async_client.post(f"/api/v1/alerts/{alert.id}/acknowledge")
    assert second.status_code == 200
    assert second.json()["acknowledged_at"] == stamp

    feed = (await async_client.get("/api/v1/alerts/feed")).json()
    assert feed["items"] == []

    missing = await async_client.post(f"/api/v1/alerts/{uuid.uuid4()}/acknowledge")
    assert missing.status_code == 404


async def test_trigger_endpoints_require_admin(async_client):
    assert (await async_client.post("/api/v1/alerts/evaluate")).status_code in (401, 403)
    resp = await async_client.post(f"/api/v1/alerts/{uuid.uuid4()}/acknowledge")
    assert resp.status_code in (401, 403)


async def test_evaluate_persists_then_deduplicates(async_client, db_session):
    """A corroborated claim raises one alert; the next pass only refreshes it."""
    from app.models.claim import Claim

    source_id, article_id = str(uuid.uuid4()), str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO sources (id, name, type, url_or_identifier, is_active)"
            " VALUES (:id, 'test', 'rss', 'https://t.example/rss', 1)"
        ),
        {"id": source_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO articles (id, source_id, title, url, content_hash)"
            " VALUES (:id, :sid, 'title', 'https://t.example/1', 'hash-1')"
        ),
        {"id": article_id, "sid": source_id},
    )
    db_session.add(
        Claim(
            article_id=uuid.UUID(article_id),
            claim_text="The raid killed 12 civilians.",
            verdict="SUPPORTED",
            extracted_at=datetime.now(UTC),
            verdict_evidence={
                "corroboration": {"value": 0.8, "weight": 0.4},
                "contradiction": {"value": 0.05, "weight": 0.2},
            },
        )
    )
    await db_session.commit()

    first = await evaluate_alerts(db_session, window_hours=6)
    assert first["alerts_inserted"] == 1
    assert first["alerts_refreshed"] == 0

    kinds = (await db_session.execute(select(Alert.kind))).scalars().all()
    assert kinds == ["CORROBORATION"]

    second = await evaluate_alerts(db_session, window_hours=6)
    assert second["alerts_inserted"] == 0
    assert second["alerts_refreshed"] == 1

    feed = (await async_client.get("/api/v1/alerts/feed?kind=corroboration")).json()
    assert len(feed["items"]) == 1
    item = feed["items"][0]
    assert item["severity"] == "INFO"
    assert item["claim_id"] is not None
    assert item["payload"]["corroboration"] == 0.8
