"""Public, read-only aggregate metrics for the operations dashboard.

One round-trip for everything the GMEE telemetry UI needs:
service readiness, corpus counts, NLP status distribution, latest
clustering run, and graph topology counts from Neo4j.

No user data, no PII — safe to expose without auth; harden with the
global rate limiter (see app/core/rate_limit.py).
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_neo4j_driver, get_redis_client
from app.models.article import Article, NLPStatusEnum
from app.models.claim import Claim, ClaimEntity

router = APIRouter()
logger = logging.getLogger(__name__)

_TIMEOUT_S = 3.0


async def _postgres_metrics(db: AsyncSession) -> dict[str, Any]:
    async with asyncio.timeout(_TIMEOUT_S):
        articles_total = await db.scalar(select(func.count(Article.id))) or 0

        nlp_rows = await db.execute(
            select(Article.nlp_status, func.count(Article.id)).group_by(Article.nlp_status)
        )
        status_counts = {s.value: 0 for s in NLPStatusEnum}
        for row in nlp_rows:
            status_counts[row[0].value] = row[1]

        claims_total = await db.scalar(select(func.count(Claim.id))) or 0
        embedded_claims = (
            await db.scalar(select(func.count(Claim.id)).where(Claim.embedding.is_not(None))) or 0
        )
        entities_total = await db.scalar(select(func.count(ClaimEntity.id))) or 0

        # Latest clustering run summary (may not exist yet)
        last_run = await db.execute(
            text(
                "SELECT run_at, claims_in_corpus FROM claim_cluster_runs "
                "ORDER BY run_at DESC LIMIT 1"
            )
        )
        run_row = last_run.first()

        return {
            "articles_total": int(articles_total),
            "nlp_status_counts": status_counts,
            "claims_total": int(claims_total),
            "embedded_claims": int(embedded_claims),
            "entities_total": int(entities_total),
            "last_evolution_run": (
                {
                    "run_at": run_row.run_at.isoformat(),
                    "claims_in_corpus": run_row.claims_in_corpus,
                }
                if run_row
                else None
            ),
        }


async def _neo4j_metrics(driver: AsyncDriver) -> dict[str, Any]:
    async with asyncio.timeout(_TIMEOUT_S):
        async with driver.session() as session:
            nodes_result = await session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n "
                "ORDER BY n DESC LIMIT 10"
            )
            counts = await nodes_result.data()

            rel_result = await session.run(
                "MATCH ()-[r]->() RETURN count(r) AS n"
            )
            rel_record = await rel_result.single()

            return {
                "available": True,
                "nodes": {rec["label"]: rec["n"] for rec in counts},
                "relationships": rel_record["n"] if rel_record else 0,
            }


async def _redis_metrics(redis_client: Redis) -> dict[str, Any]:
    async with asyncio.timeout(_TIMEOUT_S):
        info = await redis_client.info("memory")
        return {
            "available": True,
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_mb": round(info.get("used_memory", 0) / (1024 * 1024), 1),
        }


@router.get("")
async def dashboard_snapshot(
    db: AsyncSession = Depends(get_db_session),
    neo4j_driver: AsyncDriver = Depends(get_neo4j_driver),
    redis_client: Redis = Depends(get_redis_client),
) -> dict[str, Any]:
    """Aggregate telemetry snapshot. Each store reports independently;
    a down store degrades its own section instead of failing the request."""
    snapshot: dict[str, Any] = {
        "generated_at": None,
        "services": {"postgres": "ok", "neo4j": "ok", "redis": "ok"},
    }

    try:
        snapshot.update(await _postgres_metrics(db))
    except Exception as exc:
        logger.warning("dashboard: postgres section degraded: %s", exc)
        snapshot["services"]["postgres"] = f"down: {exc}"
        snapshot["corpus"] = None

    try:
        snapshot["graph"] = await _neo4j_metrics(neo4j_driver)
    except Exception as exc:
        logger.warning("dashboard: neo4j section degraded: %s", exc)
        snapshot["services"]["neo4j"] = f"down: {exc}"
        snapshot["graph"] = None

    try:
        snapshot["cache"] = await _redis_metrics(redis_client)
    except Exception as exc:
        logger.warning("dashboard: redis section degraded: %s", exc)
        snapshot["services"]["redis"] = f"down: {exc}"
        snapshot["cache"] = None

    from datetime import UTC, datetime

    snapshot["generated_at"] = datetime.now(UTC).isoformat()
    return snapshot
