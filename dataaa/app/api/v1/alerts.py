"""Early-warning alert surface.

Three layers:

- ``GET  /alerts``              stateless 24h snapshot (spikes vs the previous
                                day) — always answers, even on a cold corpus.
- ``GET  /alerts/feed``         persisted alerts from the ``alerts`` table,
                                deduplicated on (kind, subject_key) by the
                                evaluator; newest activity first.
- ``POST /alerts/evaluate``     admin-only trigger for one evaluation pass.
- ``POST /alerts/{id}/acknowledge``  admin-only operator acknowledgement
                                (idempotent — the first ack timestamp sticks).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_role
from app.models.user import RoleEnum
from app.services.alerts import build_alerts, collect_alert_inputs, evaluate_alerts

router = APIRouter()

SEVERITIES = ("INFO", "WARNING", "CRITICAL")
MAX_FEED = 200


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.get("")
async def list_alerts() -> dict[str, Any]:
    from app.db.postgres import async_session_maker

    async with async_session_maker() as db:
        inputs = await collect_alert_inputs(db)
    payload = build_alerts(
        published_ats=inputs["published_ats"],
        disputed_ats=inputs["disputed_ats"],
        mutation_ats=inputs["mutation_ats"],
    )
    return {"generated_at": datetime.now(UTC).isoformat(), **payload}


@router.get("/feed")
async def alert_feed(
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(30, ge=1, le=MAX_FEED),
    kind: str | None = None,
    severity: str | None = None,
    include_acknowledged: bool = False,
) -> dict[str, Any]:
    """Persisted alerts (newest activity first) + unacknowledged tallies."""
    from app.models.evolution import Alert

    stmt = select(Alert)
    if kind:
        stmt = stmt.where(Alert.kind == kind.strip().upper())
    if severity:
        wanted = severity.strip().upper()
        if wanted not in SEVERITIES:
            raise HTTPException(
                status_code=400,
                detail=f"severity must be one of {', '.join(SEVERITIES)}",
            )
        stmt = stmt.where(Alert.severity == wanted)
    if not include_acknowledged:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))

    rows = (
        await db.execute(stmt.order_by(Alert.last_seen_at.desc()).limit(limit))
    ).scalars().all()

    by_severity: dict[str, int] = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(Alert.severity, func.count(Alert.id))
                .where(Alert.acknowledged_at.is_(None))
                .group_by(Alert.severity)
            )
        ).all()
    }
    by_kind: dict[str, int] = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(Alert.kind, func.count(Alert.id))
                .where(Alert.acknowledged_at.is_(None))
                .group_by(Alert.kind)
            )
        ).all()
    }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "items": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "severity": r.severity,
                "title": r.title,
                "body": r.body,
                "claim_id": str(r.claim_id) if r.claim_id else None,
                "payload": r.payload,
                "first_seen_at": _iso(r.first_seen_at),
                "last_seen_at": _iso(r.last_seen_at),
                "acknowledged_at": _iso(r.acknowledged_at),
            }
            for r in rows
        ],
        "counts": {
            "unacknowledged": sum(by_severity.values()),
            "by_severity": by_severity,
            "by_kind": by_kind,
        },
    }


@router.post("/evaluate", dependencies=[Depends(require_role(RoleEnum.admin))])
async def run_evaluation(
    db: AsyncSession = Depends(get_db_session),
    window_hours: int = Query(6, ge=1, le=48),
) -> dict[str, Any]:
    """Run one persistent evaluation pass (deduplicated upserts)."""
    summary = await evaluate_alerts(db, window_hours=window_hours)
    return {"status": "evaluated", **summary}


@router.post(
    "/{alert_id}/acknowledge",
    dependencies=[Depends(require_role(RoleEnum.admin))],
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Operator ack; idempotent so the first acknowledgement time wins."""
    from app.models.evolution import Alert

    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")

    acked_at = alert.acknowledged_at
    if acked_at is None:
        acked_at = datetime.now(UTC)
        alert.acknowledged_at = acked_at
        await db.commit()

    return {
        "status": "acknowledged",
        "alert_id": str(alert.id),
        "acknowledged_at": _iso(acked_at),
    }