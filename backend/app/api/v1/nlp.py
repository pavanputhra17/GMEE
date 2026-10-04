from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.article import Article, NLPStatusEnum
from app.models.pipeline import JobTypeEnum
from app.models.user import RoleEnum, User
from app.services.nlp_orchestrator import NLPOrchestrator
from app.services.pipeline.jobs import JobAlreadyRunning, run_job

router = APIRouter()


@router.post("/trigger")
async def trigger_nlp(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(RoleEnum.admin)),
) -> dict[str, Any]:
    """Manually trigger a cycle of NLP extraction (durable, single-flight job)."""
    orchestrator = NLPOrchestrator()
    try:
        async with run_job(db, JobTypeEnum.nlp, trigger="manual", user_id=current_user.id) as job:
            summary = await orchestrator.run_nlp_cycle(db)
            job.summary = summary.model_dump(exclude={"errors"})
    except JobAlreadyRunning:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An NLP job is already running.")
    return {"message": "NLP cycle completed", "job_id": str(job.id), "summary": summary.model_dump()}


@router.get("/status", dependencies=[Depends(get_current_user)])
async def get_nlp_status(db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """Get the current NLP status counts of articles."""
    stmt = select(Article.nlp_status, func.count(Article.id)).group_by(Article.nlp_status)
    result = await db.execute(stmt)
    
    status_counts = {status.value: 0 for status in NLPStatusEnum}
    for row in result:
        status_counts[row[0].value] = row[1]
        
    return {"status_counts": status_counts}
