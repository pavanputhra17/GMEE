from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_role
from app.core import scheduler
from app.models.source import Source
from app.models.user import RoleEnum, User
from app.services.collection_orchestrator import orchestrator

router = APIRouter()


@router.post("/trigger")
async def trigger_collection(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(RoleEnum.admin))
) -> Any:
    """
    Manually trigger a data collection cycle (Admin only).
    Note: For production at scale, this should be offloaded to a background task 
    to prevent request timeouts, but is synchronous here for MVP simplicity.
    """
    summaries = await orchestrator.run_collection_cycle(db)
    # Update the global latest summary state so /status sees it
    scheduler.latest_collection_summary = summaries
    scheduler.last_run_time = __import__("datetime").datetime.now()
    
    return {
        "status": "success",
        "message": "Collection cycle completed",
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
    """
    result = await db.execute(select(Source))
    sources = result.scalars().all()
    
    return {
        "latest_run": {
            "time": scheduler.last_run_time,
            "summaries": [
                {
                    "source": s.source_name,
                    "articles_fetched": s.articles_fetched,
                    "articles_inserted": s.articles_inserted,
                    "error": s.error
                } for s in scheduler.latest_collection_summary
            ] if scheduler.latest_collection_summary else []
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
