from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.models.evolution import ClaimClusterRun
from app.models.user import RoleEnum
from app.services.evolution.orchestrator import EvolutionOrchestrator

router = APIRouter(prefix="/evolution", tags=["evolution"])


@router.post("/trigger", dependencies=[Depends(require_role([RoleEnum.admin]))])
async def trigger_evolution(
    force: bool = Query(False, description="Bypass debounce guard (minimum-corpus guard is still respected)"),
    db: AsyncSession = Depends(get_db)
) -> Any:
    orchestrator = EvolutionOrchestrator()
    result = await orchestrator.run_evolution_cycle(db, force=force)
    return {"message": "Evolution cycle triggered", "result": result}


@router.get("/status", dependencies=[Depends(get_current_user)])
async def get_evolution_status(db: AsyncSession = Depends(get_db)) -> Any:
    stmt = select(ClaimClusterRun).order_by(ClaimClusterRun.run_at.desc()).limit(1)
    run = await db.scalar(stmt)
    
    if not run:
        return {"status": "no_runs_yet"}
        
    return {
        "status": "success",
        "last_run_id": run.id,
        "last_run_at": run.run_at,
        "claims_in_corpus_at_run": run.claims_in_corpus,
        "algorithm_params": run.algorithm_params
    }


@router.get("/clusters", dependencies=[Depends(get_current_user)])
async def get_clusters(db: AsyncSession = Depends(get_db)) -> Any:
    # Fetch the latest run with assignments
    stmt = (
        select(ClaimClusterRun)
        .options(selectinload(ClaimClusterRun.assignments))
        .order_by(ClaimClusterRun.run_at.desc())
        .limit(1)
    )
    run = await db.scalar(stmt)
    
    if not run:
        return {"clusters": []}
        
    # Group assignments by topic_id
    clusters = {}
    for a in run.assignments:
        if a.topic_id not in clusters:
            clusters[a.topic_id] = {
                "topic_id": a.topic_id,
                "label": a.topic_label,
                "keywords": a.topic_keywords,
                "claim_ids": []
            }
        clusters[a.topic_id]["claim_ids"].append(a.claim_id)
        
    return {"clusters": list(clusters.values())}
