import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_neo4j_driver, get_redis_client

router = APIRouter()

@router.get("")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/ready", response_model=None)
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
    neo4j_driver: AsyncDriver = Depends(get_neo4j_driver),
    redis_client: Redis = Depends(get_redis_client)
) -> dict[str, Any] | JSONResponse:
    status: dict[str, Any] = {}
    is_ready = True

    # Check Postgres
    try:
        async with asyncio.timeout(2.0):
            await db.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"down: {e!s}"
        is_ready = False

    # Check Neo4j
    try:
        async with asyncio.timeout(2.0):
            async with neo4j_driver.session() as session:
                await session.run("RETURN 1")
        status["neo4j"] = "ok"
    except Exception as e:
        status["neo4j"] = f"down: {e!s}"
        is_ready = False

    # Check Redis
    try:
        async with asyncio.timeout(2.0):
            await redis_client.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"down: {e!s}"
        is_ready = False

    status["status"] = "ready" if is_ready else "not_ready"

    if not is_ready:
        return JSONResponse(status_code=503, content=status)

    return status
