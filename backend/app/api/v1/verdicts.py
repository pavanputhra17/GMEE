"""Public verdict endpoints — every number is backed by stored evidence."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.db.postgres import async_session_maker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_verdicts(
    band: str = Query("", max_length=24),
    outlet: str = Query("", max_length=80),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    where = ["c.verdict IS NOT NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if band:
        where.append("c.verdict = :band")
        params["band"] = band
    if outlet:
        where.append("a.domain = :outlet")
        params["outlet"] = outlet
    where_sql = " AND ".join(where)

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    async with async_session_maker() as db:
        total = (
            await db.execute(
                text(
                    f"SELECT COUNT(*) FROM claims c JOIN articles a ON a.id=c.article_id "
                    f"WHERE {where_sql}"
                ),
                count_params,
            )
        ).scalar()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT c.id::text AS id, c.claim_text, c.verdict,
                           c.verdict_probability AS probability,
                           c.confidence AS extraction_confidence,
                           a.domain AS outlet, a.title AS article_title, a.url AS article_url,
                           c.extracted_at
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE {where_sql}
                    ORDER BY c.verdict_probability ASC NULLS LAST
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).all()

    items = []
    for r in rows:
        m = dict(r._mapping)
        m["extracted_at"] = m["extracted_at"].isoformat() if m["extracted_at"] else None
        items.append(m)

    return {"total": total or 0, "items": items}


@router.get("/stats")
async def verdict_stats():
    async with async_session_maker() as db:
        dist = (
            await db.execute(
                text(
                    "SELECT verdict, COUNT(*), AVG(verdict_probability) "
                    "FROM claims GROUP BY verdict"
                )
            )
        ).all()
        total_claims = (await db.execute(text("SELECT COUNT(*) FROM claims"))).scalar()
        outlets = (
            await db.execute(
                text(
                    """
                    SELECT a.domain AS outlet,
                           COUNT(*) AS claims_total,
                           COUNT(*) FILTER (WHERE c.verdict IN ('SUPPORTED','LEAN_SUPPORTED')) AS supported,
                           COUNT(*) FILTER (WHERE c.verdict IN ('DISPUTED','LEAN_DISPUTED')) AS disputed
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    GROUP BY a.domain HAVING COUNT(*) > 0
                    ORDER BY claims_total DESC
                    """
                )
            )
        ).all()

    def cred(sup: int, dis: int) -> float:
        # Laplace-smoothed credibility for display; n=0 -> neutral 0.5
        alpha = 4.0
        return round((sup + alpha * 0.5) / (sup + dis + alpha), 3) if sup + dis else 0.5

    return {
        "total_claims": total_claims or 0,
        "distribution": [
            {
                "band": r[0] or "UNSCORED",
                "count": r[1],
                "avg_probability": round(float(r[2]), 3) if r[2] is not None else None,
            }
            for r in dist
        ],
        "outlets": [
            {
                "name": r[0],
                "claims": r[1],
                "supported": r[2],
                "disputed": r[3],
                "credibility": cred(r[2], r[3]),
            }
            for r in outlets
        ],
    }


@router.get("/leaderboard")
async def outlet_leaderboard():
    """Outlets ranked by Laplace-smoothed credibility over their verdicted claims."""
    stats = await verdict_stats()
    ranked = sorted(stats["outlets"], key=lambda o: (-o["credibility"], -o["claims"]))
    return {"ranking": ranked}


@router.get("/{claim_id}")
async def verdict_detail(claim_id: str):
    """Full transparency: the claim, its verdict, and EVERY factor."""
    async with async_session_maker() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT c.id::text AS id, c.claim_text, c.verdict,
                           c.verdict_probability AS probability,
                           c.verdict_rationale, c.verdict_evidence,
                           c.confidence AS extraction_confidence,
                           a.domain AS outlet, a.title AS article_title,
                           a.url AS article_url, a.published_at,
                           COALESCE((SELECT json_agg(json_build_object('text', ce.entity_text, 'type', ce.entity_type))
                                     FROM claim_entities ce WHERE ce.claim_id = c.id), '[]'::json) AS entities
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.id = CAST(:cid AS uuid)
                    """
                ),
                {"cid": claim_id},
            )
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="claim not found")

    m = dict(row._mapping)
    try:
        m["verdict_evidence"] = json.loads(m["verdict_evidence"]) if isinstance(m["verdict_evidence"], str) else m["verdict_evidence"]
    except Exception:
        pass
    if m.get("published_at"):
        m["published_at"] = m["published_at"].isoformat()
    return m
