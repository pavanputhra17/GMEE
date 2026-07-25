import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.article import Article, ProcessingStatusEnum
from app.models.user import RoleEnum, User
from app.services.preprocessing_orchestrator import PreprocessingOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()
prep_orchestrator = PreprocessingOrchestrator()


@router.post("/trigger", response_model=dict)
async def trigger_preprocessing(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(RoleEnum.admin))
):
    """
    Manually trigger a preprocessing cycle (admin only).
    """
    try:
        summary = await prep_orchestrator.run_preprocessing_cycle(db)
        return {
            "status": "success",
            "message": "Preprocessing cycle completed",
            "summary": {
                "total_processed": summary.total_processed,
                "status_counts": summary.status_counts,
                "errors": summary.errors
            }
        }
    except Exception as e:
        logger.exception(f"Preprocessing trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preprocessing cycle failed: {e!s}"
        )


@router.get("/status", response_model=dict)
async def get_preprocessing_status(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get preprocessing statistics.
    """
    # Count articles by processing_status
    stmt = select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
    result = await db.execute(stmt)
    counts = dict(result.all())

    # Ensure all statuses are present in the response
    status_counts = {
        status_enum.value: counts.get(status_enum, 0)
        for status_enum in ProcessingStatusEnum
    }

    return {
        "status_counts": status_counts
    }
