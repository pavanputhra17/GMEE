from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.pipeline import JobTypeEnum
from app.models.source import Source
from app.models.user import RoleEnum, User
from app.services.collection_orchestrator import orchestrator
from app.services.pipeline.jobs import JobAlreadyRunning, latest_job, run_job

router = APIRouter()


@router.post("/trigger")
async def trigger_collection(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(RoleEnum.admin))
) -> Any:
    """
    Manually trigger a data collection cycle (Admin only).

    Recorded as a durable ``pipeline_jobs`` row; a concurrent collection job
    (scheduled or manual) yields 409 instead of a second racing run. Still
    synchronous: behind a proxy with a short read timeout, poll
    ``GET /api/v1/operations/jobs`` for the outcome.
    """
    try:
        async with run_job(
            db, JobTypeEnum.collection, trigger="manual", user_id=current_user.id
        ) as job:
            summaries = await orchestrator.run_collection_cycle(db)
            job.summary = {"sources": [asdict(s) for s in summaries]}
    except JobAlreadyRunning:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection job is already running.",
        )

    return {
        "status": "success",
        "message": "Collection cycle completed",
        "job_id": str(job.id),
        "summaries": [
            {
                "source": s.source_name,
                "articles_fetched": s.articles_fetched,
                "articles_inserted": s.articles_inserted,
                "error": s.error
            } for s in summaries
        ]
    }


@router.get("/status")
async def get_collection_status(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get the status of all active sources and the latest collection run (Any authenticated user).
    The latest run comes from the durable job table, so it survives restarts and
    is consistent across replicas.
    """
    result = await db.execute(select(Source))
    sources = result.scalars().all()
    job = await latest_job(db, JobTypeEnum.collection)
    source_summaries = (job.summary or {}).get("sources", []) if job else []

    return {
        "latest_run": {
            "time": (job.finished_at or job.started_at) if job else None,
            "status": job.status if job else None,
            "job_id": str(job.id) if job else None,
            "summaries": [
                {
                    "source": s.get("source_name"),
                    "articles_fetched": s.get("articles_fetched", 0),
                    "articles_inserted": s.get("articles_inserted", 0),
                    "error": s.get("error"),
                } for s in source_summaries
            ],
        },
        "sources": [
            {
                "id": source.id,
                "name": source.name,
                "type": source.type.value,
                "is_active": source.is_active,
                "last_collected_at": source.last_collected_at
            } for source in sources
        ]
    }
