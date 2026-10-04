"""Authenticated, blinded annotation; admin-only scored research snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user, get_db_session, require_role
from app.models.article import Article
from app.models.claim import Claim
from app.models.eval import EvalPair, EvalPairLabel
from app.models.user import RoleEnum, User
from app.services.eval.dataset import (
    DatasetError,
    build_export,
    collect_export_records,
    collect_pair_metadata,
    lock_pair_writes,
    snapshot_session,
    validate_assignments,
    vote_record,
)
from app.services.eval.progress import build_progress, per_annotator
from app.services.eval.provenance import LABELS
from app.services.eval.report import ENGINE_OPERATING_POINT

router = APIRouter()
VALID_LABELS = LABELS
Label = Literal["SAME_STORY", "EVOLVED", "DISTINCT"]
Split = Literal["unassigned", "train", "dev", "test"]
AssignedSplit = Literal["train", "dev", "test"]
MutationType = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class BlindedClaim(BaseModel):
    text: str
    domain: str | None


class BlindedPair(BaseModel):
    pair_id: uuid.UUID
    a: BlindedClaim
    b: BlindedClaim


class NextPairResponse(BaseModel):
    done: bool
    pair: BlindedPair | None


def _blinded(row: Any) -> dict[str, Any]:
    return {"pair_id": str(row.id), "a": {"text": row.text_a, "domain": row.domain_a}, "b": {"text": row.text_b, "domain": row.domain_b}}


def _per_annotator(rows: Any) -> dict[str, Any]:
    return per_annotator(rows)


@router.get("/next", response_model=NextPairResponse)
async def next_pair(
    split: Split = "unassigned",
    strategy: Literal["coverage", "uncertainty"] = "coverage",
    annotator: str | None = Query(default=None, max_length=64, deprecated=True, description="Ignored; the authenticated user is the annotator"),
    limit_scan: int = Query(default=50, ge=1, le=200, deprecated=True, description="Ignored; selection is performed deterministically in SQL"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Uncertainty is score proximity for train only, not probability entropy."""
    if strategy == "uncertainty" and split != "train":
        raise HTTPException(status_code=422, detail="strategy=uncertainty requires split=train; unassigned/dev/test always use fixed coverage")
    ca, cb = aliased(Claim), aliased(Claim)
    aa, ab = aliased(Article), aliased(Article)
    identity = f"user:{current_user.id}"
    already_labeled = exists().where(
        EvalPairLabel.pair_id == EvalPair.id,
        EvalPairLabel.origin == "human",
        EvalPairLabel.annotator_user_id == current_user.id,
        EvalPairLabel.annotator == identity,
    )
    statement = (
        select(EvalPair.id.label("id"), ca.claim_text.label("text_a"), cb.claim_text.label("text_b"), aa.domain.label("domain_a"), ab.domain.label("domain_b"))
        .join(ca, ca.id == EvalPair.claim_a_id).join(cb, cb.id == EvalPair.claim_b_id)
        .join(aa, aa.id == ca.article_id).join(ab, ab.id == cb.article_id)
        .where(EvalPair.split == split, ~already_labeled)
    )
    if strategy == "uncertainty":
        statement = statement.order_by(func.abs(EvalPair.sim_score - ENGINE_OPERATING_POINT))
    statement = statement.order_by(EvalPair.sampled_at, EvalPair.id).limit(1)
    row = (await db.execute(statement)).first()
    return {"done": row is None, "pair": _blinded(row) if row is not None else None}


class EvalLabelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pair_id: uuid.UUID
    label: Label
    annotator: str | None = Field(default=None, min_length=1, max_length=64, deprecated=True, description="Ignored; never grants another annotator's identity")
    mutation_types: list[MutationType] | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("mutation_types")
    @classmethod
    def normalize_mutations(cls, value: list[str] | None) -> list[str] | None:
        return sorted(set(value)) if value is not None else None


@router.post("/label", status_code=201)
async def label_pair(
    body: EvalLabelBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """One current human vote per user; prior revisions/other origins survive."""
    pair = (await db.execute(select(EvalPair.id).where(EvalPair.id == body.pair_id).with_for_update())).first()
    if pair is None:
        raise HTTPException(status_code=404, detail="pair not found")
    identity = f"user:{current_user.id}"
    vote = (await db.execute(select(EvalPairLabel).where(
        EvalPairLabel.pair_id == body.pair_id,
        EvalPairLabel.annotator == identity,
        EvalPairLabel.origin == "human",
    ).with_for_update())).scalar_one_or_none()
    now = datetime.now(UTC)
    if vote is None:
        vote = EvalPairLabel(
            pair_id=body.pair_id, annotator=identity, annotator_user_id=current_user.id,
            origin="human", label=body.label, mutation_types=body.mutation_types,
            notes=body.notes, created_at=now, updated_at=now,
            provenance={"method": "authenticated_eval_api_v1", "identity_source": "get_current_user"},
        )
        db.add(vote)
    else:
        if vote.annotator_user_id != current_user.id:
            raise HTTPException(status_code=409, detail="Stored human identity is inconsistent; retain the historical row and resolve its provenance before editing")
        mutations = body.mutation_types if "mutation_types" in body.model_fields_set else vote.mutation_types
        notes = body.notes if "notes" in body.model_fields_set else vote.notes
        if (vote.label, vote.mutation_types, vote.notes) != (body.label, mutations, notes):
            previous = vote_record(vote)
            previous.pop("history")
            vote.history = [*(vote.history or []), previous]
            vote.label, vote.mutation_types, vote.notes = body.label, mutations, notes
            vote.updated_at = now
    await db.flush()
    response = {"status": "recorded", "pair_id": str(body.pair_id), "label": vote.label, "annotator": identity, "origin": "human", "mutation_types": vote.mutation_types, "notes": vote.notes}
    await db.commit()
    return response


@router.get("/progress")
async def progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    pairs = [dict(r._mapping) for r in (await db.execute(select(EvalPair.id.label("pair_id"), EvalPair.bucket, EvalPair.split).order_by(EvalPair.id))).all()]
    votes = [vote_record(v) for v in (await db.execute(select(EvalPairLabel).order_by(EvalPairLabel.pair_id, EvalPairLabel.origin, EvalPairLabel.annotator))).scalars()]
    return build_progress(pairs, votes)


@router.get("/report")
async def eval_report(
    current_user: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Live-corpus diagnostics only; not a frozen held-out publication result."""
    from app.services.eval.report import build_report, collect_labeled_pairs

    return build_report(await collect_labeled_pairs(db))


class SplitAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pair_id: uuid.UUID
    event_group: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    split: AssignedSplit

    @field_validator("event_group")
    @classmethod
    def assigned_event(cls, value: str) -> str:
        if value.casefold() == "unassigned":
            raise ValueError("event_group must be a curated event identifier, not unassigned")
        return value


class SplitAssignmentsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignments: list[SplitAssignment] = Field(min_length=1, max_length=1000)


@router.post("/splits")
async def assign_splits(
    body: SplitAssignmentsBody,
    current_user: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Freeze whole connected components; identical retries are idempotent."""
    await lock_pair_writes(db)
    records = await collect_pair_metadata(db)
    changes = [a.model_dump(mode="json") for a in body.assignments]
    by_id = {r["pair_id"]: r for r in records}
    if any(c["pair_id"] not in by_id for c in changes):
        raise HTTPException(status_code=404, detail="One or more pair_ids were not found; nothing assigned")
    new_count = sum(by_id[c["pair_id"]]["split"] == "unassigned" for c in changes)
    try:
        validate_assignments(records, changes)
    except DatasetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    selected = (await db.execute(select(EvalPair).where(EvalPair.id.in_([a.pair_id for a in body.assignments])).with_for_update())).scalars().all()
    changes_by_id = {c["pair_id"]: c for c in changes}
    for pair in selected:
        change = changes_by_id[str(pair.id)]
        pair.split, pair.event_group = change["split"], change["event_group"]
    await db.commit()
    return {"assigned": new_count, "unchanged": len(changes) - new_count, "frozen": True}


@router.get("/export")
async def export_dataset(
    dataset_version: str = Query(min_length=1, max_length=128),
    publication: bool = False,
    current_user: User = Depends(require_role(RoleEnum.admin)),
) -> dict[str, Any]:
    """Actual records (never the blinded API); publication mode is human-only."""
    try:
        async with snapshot_session() as db:
            records = await collect_export_records(db, dataset_version)
        return build_export(records, dataset_version, publication=publication)
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
