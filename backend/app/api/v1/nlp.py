from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.article import Article, NLPStatusEnum
from app.models.user import RoleEnum
from app.services.nlp_orchestrator import NLPOrchestrator

router = APIRouter()


@router.post("/trigger", dependencies=[Depends(require_role(RoleEnum.admin))])
async def trigger_nlp(db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """Manually trigger a cycle of NLP extraction."""
    orchestrator = NLPOrchestrator()
    summary = await orchestrator.run_nlp_cycle(db)
    return {"message": "NLP cycle completed", "summary": summary.model_dump()}


@router.get("/status", dependencies=[Depends(get_current_user)])
async def get_nlp_status(db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """Get the current NLP status counts of articles."""
    stmt = select(Article.nlp_status, func.count(Article.id)).group_by(Article.nlp_status)
    result = await db.execute(stmt)
    
    status_counts = {status.value: 0 for status in NLPStatusEnum}
    for row in result:
        status_counts[row[0].value] = row[1]
        
    return {"status_counts": status_counts}
