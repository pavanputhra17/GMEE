import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.article import Article, ProcessingStatusEnum
from app.models.pipeline import JobTypeEnum
from app.models.user import RoleEnum, User
from app.services.pipeline.jobs import JobAlreadyRunning, run_job
from app.services.preprocessing_orchestrator import PreprocessingOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()
prep_orchestrator = PreprocessingOrchestrator()


@router.post("/trigger", response_model=dict)
async def trigger_preprocessing(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(RoleEnum.admin))
) -> dict[str, Any]:
    """
    Manually trigger a preprocessing cycle (admin only), recorded as a durable job.
    """
    try:
        async with run_job(
            db, JobTypeEnum.preprocessing, trigger="manual", user_id=current_user.id
        ) as job:
            summary = await prep_orchestrator.run_preprocessing_cycle(db)
            job.summary = {
                "total_processed": summary.total_processed,
                "status_counts": summary.status_counts,
                "lost_ownership": summary.lost_ownership,
                "recovered": summary.recovered,
            }
        return {
            "status": "success",
            "message": "Preprocessing cycle completed",
            "job_id": str(job.id),
            "summary": {
                "total_processed": summary.total_processed,
                "status_counts": summary.status_counts,
                "errors": summary.errors
            }
        }
    except JobAlreadyRunning:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A preprocessing job is already running.",
        )
    except Exception:
        logger.exception("Preprocessing trigger failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Preprocessing cycle failed; see the job record and server logs.",
        )


@router.get("/status", response_model=dict)
async def get_preprocessing_status(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """
    Get preprocessing statistics.
    """
    # Count articles by processing_status
    stmt = select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
    result = await db.execute(stmt)
    counts: dict[ProcessingStatusEnum, int] = {row[0]: int(row[1]) for row in result.all()}

    # Ensure all statuses are present in the response
    status_counts = {
        status_enum.value: counts.get(status_enum, 0)
        for status_enum in ProcessingStatusEnum
    }

    return {
        "status_counts": status_counts
    }
