"""Early-warning alert engine.

Turns raw corpus telemetry into human-readable alerts:
  - INGESTION_SPIKE   — article arrivals well above the previous day
  - DISPUTED_SURGE    — DISPUTED-verdict claims spiking in the last 24h
  - MUTATION_SURGE    — EVOLVED_FROM links spiking in the last 24h
  - QUIET             — nothing anomalous (explicit is better than empty)

Pure classification lives in build_alerts (unit-testable, no DB); the DB
queries live in collect_alert_inputs (sqlite-safe, no SQL intervals).
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=24)


def _bucket(ats: Sequence[datetime | None], now: datetime) -> tuple[int, int]:
    """(count in last 24h, count in the 24h before that)."""
    recent = prior = 0
    for t in ats:
        if t is None:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        delta = now - t
        if timedelta(0) <= delta <= WINDOW:
            recent += 1
        elif WINDOW < delta <= 2 * WINDOW:
            prior += 1
    return recent, prior


def build_alerts(
    *,
    published_ats: Sequence[datetime | None],
    disputed_ats: Sequence[datetime | None],
    mutation_ats: Sequence[datetime | None],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    alerts: list[dict[str, Any]] = []

    ing_recent, ing_prior = _bucket(published_ats, now)
    if ing_recent >= 5 and ing_recent >= 2 * max(ing_prior, 1):
        alerts.append({
            "type": "INGESTION_SPIKE",
            "severity": "warn",
            "title": "Collection is surging",
            "detail": f"{ing_recent} articles ingested in the last 24h "
                      f"(previous 24h: {ing_prior}). Clustering will re-run soon.",
        })

    dis_recent, dis_prior = _bucket(disputed_ats, now)
    if dis_recent >= 3 and dis_recent >= 2 * max(dis_prior, 1):
        alerts.append({
            "type": "DISPUTED_SURGE",
            "severity": "warn",
            "title": "Cross-outlet contradiction spike",
            "detail": f"{dis_recent} claims scored DISPUTED in the last 24h "
                      f"(previous 24h: {dis_prior}). Inspect the FactCheck tab.",
        })

    mut_recent, mut_prior = _bucket(mutation_ats, now)
    if mut_recent >= 3 and mut_recent >= 2 * max(mut_prior, 1):
        alerts.append({
            "type": "MUTATION_SURGE",
            "severity": "critical",
            "title": "Claim mutations accelerating",
            "detail": f"{mut_recent} new EVOLVED_FROM links detected in the last 24h "
                      f"(previous 24h: {mut_prior}). A story is actively drifting.",
        })

    if not alerts:
        alerts.append({
            "type": "QUIET",
            "severity": "info",
            "title": "All quiet",
            "detail": "No anomalous collection, verdict or mutation activity in the last 24h.",
        })

    return {
        "alerts": alerts,
        "stats": {
            "articles_24h": ing_recent,
            "articles_prior_24h": ing_prior,
            "disputed_24h": dis_recent,
            "disputed_prior_24h": dis_prior,
            "mutations_24h": mut_recent,
            "mutations_prior_24h": mut_prior,
        },
    }


async def collect_alert_inputs(db: Any) -> dict[str, list[datetime | None]]:
    """Gather the three timestamp streams. Uses ORM selects only — no SQL
    dialect features — so the test suite can run it on SQLite."""
    from app.models.article import Article
    from app.models.claim import Claim
    from app.models.evolution import ClaimRelationship, RelationshipTypeEnum

    pub = (await db.execute(select(Article.published_at))).scalars().all()

    dis = (
        await db.execute(select(Claim.extracted_at).where(Claim.verdict == "DISPUTED"))
    ).scalars().all()

    mut = (
        await db.execute(
            select(ClaimRelationship.created_at).where(
                ClaimRelationship.relationship_type == RelationshipTypeEnum.EVOLVED_FROM
            )
        )
    ).scalars().all()

    return {"published_ats": list(pub), "disputed_ats": list(dis), "mutation_ats": list(mut)}


# ---------------------------------------------------------------------------
# Persistent alert engine (deduplicated, acknowledgeable, scheduler-driven).
# Whereas build_alerts() computes a stateless 24h snapshot on every request,
# evaluate_alerts() detects per-claim/edge/cluster conditions and PERSISTS them
# in the `alerts` table, deduplicated on (kind, subject_key).
# ---------------------------------------------------------------------------

CORROBORATION_THRESHOLD = 0.6
CONTRADICTION_THRESHOLD = 0.3
SPIKE_MIN_CLAIMS = 8
MAX_ALERTS_PER_RUN = 40


def _evidence_signal(evidence: Any, key: str) -> float | None:
    if not isinstance(evidence, dict):
        return None
    sig = evidence.get(key)
    if isinstance(sig, dict) and isinstance(sig.get("value"), (int, float)):
        return float(sig["value"])
    return None


def _evidence_detail(evidence: Any, key: str, field: str) -> float | None:
    """Nested numeric detail of one signal (e.g. its raw contradiction ratio)."""
    if not isinstance(evidence, dict):
        return None
    sig = evidence.get(key)
    if isinstance(sig, dict) and isinstance(sig.get(field), (int, float)):
        return float(sig[field])
    return None


async def evaluate_alerts(db: Any, window_hours: int = 6) -> dict[str, Any]:
    """One persistent evaluation pass; deduplicates and commits."""
    from datetime import timedelta

    from app.models.claim import Claim
    from app.models.evolution import (
        Alert,
        ClaimClusterAssignment,
        ClaimRelationship,
        RelationshipTypeEnum,
    )
    from app.services.verdict.mutation_diff import diff_versions

    since = datetime.now(UTC) - timedelta(hours=window_hours)
    now = datetime.now(UTC)
    raised: list[dict[str, Any]] = []

    # ---- verdict-backed signals (corroboration / contradiction) -----------
    res = await db.execute(
        select(Claim)
        .where(Claim.extracted_at >= since, Claim.verdict_evidence.is_not(None))
        .order_by(Claim.extracted_at.desc())
        .limit(500)
    )
    for c in res.scalars().all():
        corr = _evidence_signal(c.verdict_evidence, "corroboration")
        # The contradiction SIGNAL is neutral-centred (0.5 = no contradiction),
        # so the alert threshold applies to the raw ratio it carries in its
        # detail. Rows scored before that change stored the ratio directly in
        # `value` — fall back to it so historical evidence still alerts.
        contra = _evidence_detail(
            c.verdict_evidence, "contradiction", "contradiction_ratio"
        )
        if contra is None:
            contra = _evidence_signal(c.verdict_evidence, "contradiction")
        if contra is not None and contra >= CONTRADICTION_THRESHOLD:
            raised.append({
                "kind": "CONTRADICTION", "severity": "CRITICAL",
                "subject_key": f"claim:{c.id}",
                "title": f"Cross-outlet contradiction detected (signal {contra:.2f})",
                "body": (c.claim_text or "")[:280], "claim_id": c.id,
                "payload": {"contradiction": contra, "claim_text": (c.claim_text or "")[:280]},
            })
        elif corr is not None and corr >= CORROBORATION_THRESHOLD:
            raised.append({
                "kind": "CORROBORATION", "severity": "INFO",
                "subject_key": f"claim:{c.id}",
                "title": f"Independently corroborated ({corr:.0%} corroboration signal)",
                "body": (c.claim_text or "")[:280], "claim_id": c.id,
                "payload": {"corroboration": corr, "claim_text": (c.claim_text or "")[:280]},
            })

    # ---- fresh EVOLVED_FROM edges with typed mutation content -------------
    edge_res = await db.execute(
        select(ClaimRelationship).where(
            ClaimRelationship.relationship_type == RelationshipTypeEnum.EVOLVED_FROM,
            ClaimRelationship.created_at >= since,
        ).limit(100)
    )
    edges = edge_res.scalars().all()
    if edges:
        claim_ids = {e.from_claim_id for e in edges} | {e.to_claim_id for e in edges}
        c_res = await db.execute(select(Claim).where(Claim.id.in_(claim_ids)))
        by_id = {c.id: c for c in c_res.scalars().all()}
        for e in edges:
            a, b = by_id.get(e.from_claim_id), by_id.get(e.to_claim_id)
            if not a or not b:
                continue
            d = diff_versions(a.claim_text or "", b.claim_text or "")
            types = d["mutation_types"]
            if not types or types == ["NEAR_DUPLICATE"]:
                continue
            interesting = [t for t in types if t != "WORDING_DRIFT"] or types
            raised.append({
                "kind": "MUTATION",
                "severity": "WARNING" if "NUMERIC_DRIFT" in interesting else "INFO",
                "subject_key": f"edge:{e.from_claim_id}:{e.to_claim_id}",
                "title": f"Claim mutated across outlets: {', '.join(interesting)}",
                "body": ("\u201c" + (a.claim_text or "")[:120] + "\u201d \u2192 \u201c"
                         + (b.claim_text or "")[:120] + "\u201d"),
                "claim_id": b.id,
                "payload": {"mutation_types": types, "similarity": d["similarity"],
                            "from_claim": str(a.id), "to_claim": str(b.id)},
            })

    # ---- story-cluster spikes ---------------------------------------------
    spike_res = await db.execute(
        select(
            ClaimClusterAssignment.cluster_run_id,
            ClaimClusterAssignment.topic_label,
            func.count(ClaimClusterAssignment.id).label("n"),
        )
        .join(Claim, Claim.id == ClaimClusterAssignment.claim_id)
        .where(Claim.extracted_at >= since)
        .group_by(ClaimClusterAssignment.cluster_run_id, ClaimClusterAssignment.topic_label)
        .having(func.count(ClaimClusterAssignment.id) >= SPIKE_MIN_CLAIMS)
        .limit(10)
    )
    for run_id, label, n in spike_res.all():
        raised.append({
            "kind": "SPIKE", "severity": "WARNING",
            "subject_key": f"cluster:{run_id}:{label}",
            "title": f"Story burst: {n} new claims in cluster \u201c{label or run_id}\u201d",
            "body": f"{n} claims joined this story cluster within the last {window_hours}h window.",
            "claim_id": None,
            "payload": {"cluster_run_id": str(run_id), "topic_label": label, "new_claims": n},
        })

    # ---- deduplicate + persist --------------------------------------------
    inserted = refreshed = 0
    for item in raised[:MAX_ALERTS_PER_RUN]:
        existing = (
            await db.execute(
                select(Alert).where(Alert.kind == item["kind"], Alert.subject_key == item["subject_key"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.last_seen_at = now
            refreshed += 1
        else:
            db.add(Alert(**item, first_seen_at=now, last_seen_at=now))
            inserted += 1
    await db.commit()

    summary = {"window_hours": window_hours, "conditions_detected": len(raised),
               "alerts_inserted": inserted, "alerts_refreshed": refreshed}
    logger.info("persistent alert evaluation: %s", summary)
    return summary