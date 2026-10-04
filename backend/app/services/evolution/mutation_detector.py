"""Inferred, typed claim mutation edges with child-scoped reconciliation.

Similarity is a candidate signal, not proof of mutation or transmission. Parent
selection requires a meaningful lexical change, a different article, and a
strictly earlier publication timestamp. Candidate scoring is blockwise and
text analysis is capped per child; no entire-topic Gram matrix is allocated.
"""

import asyncio
import logging
import uuid
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.article import Article
from app.models.claim import Claim
from app.models.evolution import (
    ClaimClusterAssignment,
    ClaimRelationship,
    RelationshipTypeEnum,
)
from app.services.evolution.similarity import (
    SIMILARITY_BLOCK_SIZE,
    top_neighbors,
    unit_matrix,
)
from app.services.evolution.text_changes import analyze_text_change, utc_timestamp

logger = logging.getLogger(__name__)
MUTATION_ALGORITHM_VERSION = "gmee-mutation-parent-v2"
_ID_BATCH_SIZE = 500
_MAX_CANDIDATE_LIMIT = 500

# Retained for callers that used the original normalization helper.
_unit_matrix = unit_matrix


def candidate_limits(settings: object) -> tuple[int, int]:
    limit = max(
        1,
        min(
            _MAX_CANDIDATE_LIMIT, int(getattr(settings, "MUTATION_CANDIDATE_LIMIT", 50))
        ),
    )
    lag_days = max(0, int(getattr(settings, "MUTATION_MAX_LAG_DAYS", 30)))
    return limit, lag_days


async def _existing_edges(
    db: AsyncSession,
    child_ids: Sequence[uuid.UUID],
) -> dict[tuple[uuid.UUID, uuid.UUID, RelationshipTypeEnum], ClaimRelationship]:
    """Load by CHILD, not by both endpoints or the current topic.

    A child's previous parent may be outside its new cluster (or the supplied
    corpus), and must still be reconciled when that child becomes noise.
    """
    existing = {}
    for offset in range(0, len(child_ids), _ID_BATCH_SIZE):
        rows = (
            (
                await db.execute(
                    select(ClaimRelationship).where(
                        ClaimRelationship.from_claim_id.in_(
                            child_ids[offset : offset + _ID_BATCH_SIZE]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        existing.update(
            {(r.from_claim_id, r.to_claim_id, r.relationship_type): r for r in rows}
        )
    return existing


@dataclass(frozen=True)
class _ClaimInput:
    id: uuid.UUID
    article_id: uuid.UUID
    text: str
    published_at: datetime | None
    embedding: object


@dataclass(frozen=True)
class _Candidate:
    child_id: uuid.UUID
    target_id: uuid.UUID
    relationship_type: RelationshipTypeEnum
    score: float
    evidence: dict[str, Any]


def _detect_candidates(
    groups: dict[int, list[_ClaimInput]],
    evo_threshold: float,
    sim_threshold: float,
    candidate_limit: int,
    max_lag_days: int,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    max_lag = timedelta(days=max_lag_days)
    for topic_id in sorted(groups):
        valid: list[_ClaimInput] = []
        vectors: list[np.ndarray] = []
        dimension: int | None = None
        for claim in sorted(groups[topic_id], key=lambda c: str(c.id)):
            if claim.embedding is None:
                continue
            try:
                vector = np.asarray(claim.embedding, dtype=np.float32)
            except (TypeError, ValueError):
                logger.warning("Skipping invalid embedding for claim %s", claim.id)
                continue
            if (
                vector.ndim != 1
                or not len(vector)
                or not np.isfinite(vector).all()
                or not np.any(vector)
            ):
                logger.warning(
                    "Skipping empty/non-finite embedding for claim %s", claim.id
                )
                continue
            if dimension is not None and len(vector) != dimension:
                logger.warning(
                    "Skipping mismatched embedding dimension for claim %s", claim.id
                )
                continue
            dimension = len(vector)
            valid.append(claim)
            vectors.append(vector)
        if len(valid) < 2:
            continue

        order = sorted(
            range(len(valid)),
            key=lambda i: (
                valid[i].published_at is None,
                valid[i].published_at or datetime.max.replace(tzinfo=UTC),
                str(valid[i].id),
            ),
        )
        claims = [valid[i] for i in order]
        unit = unit_matrix([vectors[i] for i in order])
        known_times = [c.published_at for c in claims if c.published_at is not None]
        for i, child in enumerate(claims):
            start = (
                bisect_left(known_times, child.published_at - max_lag)
                if child.published_at is not None
                else 0
            )
            neighbors = top_neighbors(
                unit,
                i,
                start=start,
                stop=i,
                limit=candidate_limit,
                threshold=min(evo_threshold, sim_threshold),
            )
            analyzed: list[tuple[_ClaimInput, float, dict[str, Any], bool]] = []
            parent_id = None
            for j, score in neighbors:
                older = claims[j]
                analysis = analyze_text_change(
                    older.text,
                    child.text,
                    older_timestamp=older.published_at,
                    newer_timestamp=child.published_at,
                )
                strictly_older = analysis["temporal_order"] == "strictly_older"
                within_lag = (
                    analysis["lag_seconds"] is not None
                    and 0 < analysis["lag_seconds"] <= max_lag.total_seconds()
                )
                eligible = (
                    strictly_older
                    and within_lag
                    and child.article_id != older.article_id
                    and analysis["meaningful_change"]
                    and score >= evo_threshold
                )
                evidence: dict[str, Any] = {
                    **analysis,
                    "selection": {
                        "algorithm_version": MUTATION_ALGORITHM_VERSION,
                        "topic_id": topic_id,
                        "candidate_limit": candidate_limit,
                        "max_lag_days": max_lag_days,
                        "similarity_block_size": SIMILARITY_BLOCK_SIZE,
                        "evolution_similarity_threshold": evo_threshold,
                        "similar_to_threshold": sim_threshold,
                        "candidate_ranking": "cosine_desc_then_publication_time_then_claim_id",
                        "temporal_basis": "article.published_at_only",
                        "cosine_similarity": round(score, 6),
                        "limitations": [
                            "Only the highest-scoring bounded candidate set within the lag window is analyzed; an eligible parent outside it can be missed.",
                            "Exact blockwise scoring has bounded memory but can still require quadratic arithmetic within a topic.",
                            "Selected lineage is inferred, not observed copying or transmission.",
                        ],
                    },
                    "older_claim_id": str(older.id),
                    "newer_claim_id": str(child.id),
                    "older_article_id": str(older.article_id),
                    "newer_article_id": str(child.article_id),
                    "parent_eligibility": {
                        "strictly_older": strictly_older,
                        "different_article": child.article_id != older.article_id,
                        "within_max_lag": within_lag,
                        "meaningful_change": analysis["meaningful_change"],
                    },
                }
                analyzed.append((older, score, evidence, eligible))
                if parent_id is None and eligible:
                    parent_id = older.id

            for older, score, evidence, _ in analyzed:
                is_parent = older.id == parent_id
                if not is_parent and score < sim_threshold:
                    continue
                relationship_type = (
                    RelationshipTypeEnum.EVOLVED_FROM
                    if is_parent
                    else RelationshipTypeEnum.SIMILAR_TO
                )
                evidence.update(
                    {
                        "parent_claim_id": str(older.id) if is_parent else None,
                        "child_claim_id": str(child.id) if is_parent else None,
                        "inference": "inferred_candidate_lineage"
                        if is_parent
                        else "inferred_text_similarity",
                        "observed_propagation": False,
                    }
                )
                candidates.append(
                    _Candidate(child.id, older.id, relationship_type, score, evidence)
                )
    return candidates


class MutationDetector:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_mutation_detection(
        self,
        db: AsyncSession,
        assignments: Sequence[ClaimClusterAssignment],
        claims_by_id: dict[uuid.UUID, Claim],
        articles_by_id: dict[uuid.UUID, Article],
    ) -> list[ClaimRelationship]:
        """Reconcile all supplied children, including noise and missing embeddings.

        SIMILAR_TO evidence is upserted, not globally pruned. EVOLVED_FROM is
        a current inference: stale parents are removed by child regardless of
        their target's cluster membership. Claims outside this corpus are not
        touched. Row locks plus the partial unique index serialize parent
        replacement across concurrent detector runs.
        """
        child_ids = sorted(claims_by_id, key=str)
        for offset in range(0, len(child_ids), _ID_BATCH_SIZE):
            await db.execute(
                select(Claim.id)
                .where(Claim.id.in_(child_ids[offset : offset + _ID_BATCH_SIZE]))
                .order_by(Claim.id)
                .with_for_update()
            )
        existing = await _existing_edges(db, child_ids)
        topic_by_id: dict[uuid.UUID, int] = {}
        for assignment in assignments:
            cid = assignment.claim_id
            if cid in topic_by_id and topic_by_id[cid] != assignment.topic_id:
                topic_by_id[cid] = -1
            else:
                topic_by_id[cid] = assignment.topic_id
        groups: dict[int, list[_ClaimInput]] = defaultdict(list)
        for cid, topic_id in topic_by_id.items():
            claim = claims_by_id.get(cid)
            if topic_id == -1 or claim is None:
                continue
            article = articles_by_id.get(claim.article_id)
            groups[topic_id].append(
                _ClaimInput(
                    cid,
                    claim.article_id,
                    claim.claim_text or "",
                    utc_timestamp(article.published_at)
                    if article is not None
                    else None,
                    claim.embedding,
                )
            )

        candidate_limit, max_lag_days = candidate_limits(self.settings)
        candidates = await asyncio.to_thread(
            _detect_candidates,
            groups,
            self.settings.EVOLUTION_SIMILARITY_THRESHOLD,
            self.settings.SIMILAR_TO_THRESHOLD,
            candidate_limit,
            max_lag_days,
        )
        chosen_parents = {
            c.child_id: c.target_id
            for c in candidates
            if c.relationship_type == RelationshipTypeEnum.EVOLVED_FROM
        }
        stale = [
            row
            for row in existing.values()
            if row.relationship_type == RelationshipTypeEnum.EVOLVED_FROM
            and row.from_claim_id in claims_by_id
            and chosen_parents.get(row.from_claim_id) != row.to_claim_id
        ]
        for stale_row in stale:
            await db.delete(stale_row)
        if stale:
            # Release the child's unique parent slot before inserting its replacement.
            await db.flush()

        relationships: list[ClaimRelationship] = []
        new_edges: list[ClaimRelationship] = []
        for candidate in candidates:
            key = (candidate.child_id, candidate.target_id, candidate.relationship_type)
            row = existing.get(key)
            if row is None:
                row = ClaimRelationship(
                    from_claim_id=candidate.child_id,
                    to_claim_id=candidate.target_id,
                    relationship_type=candidate.relationship_type,
                    score=candidate.score,
                    mutation_evidence=candidate.evidence,
                )
                new_edges.append(row)
            else:
                row.score = candidate.score
                row.mutation_evidence = candidate.evidence
            relationships.append(row)
        if new_edges:
            db.add_all(new_edges)
        if relationships:
            await db.flush()
        logger.info(
            "Mutation detection complete: %d inferred relationships", len(relationships)
        )
        return relationships
