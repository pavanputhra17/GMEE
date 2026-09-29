"""Claim mutation detection (EVOLVED_FROM / SIMILAR_TO inside each topic).

Similarity is computed as one batched matrix product per topic group instead of
a `cos_sim` call per candidate pair: the Python double loop was this pipeline's
slowest step, and the arithmetic is identical.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

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

logger = logging.getLogger(__name__)


async def _existing_edges(
    db: AsyncSession,
    claim_ids: Sequence[uuid.UUID],
) -> dict[tuple[uuid.UUID, uuid.UUID, RelationshipTypeEnum], ClaimRelationship]:
    """Persisted edges between these claims, keyed by (from, to, type).

    Re-running detection must upsert, not duplicate: `claim_relationships`
    carries a unique constraint on that tuple, so a blind re-insert would be
    rejected by the database (and, before the constraint existed, piled up one
    copy of every edge per evolution cycle).
    """
    if len(claim_ids) < 2:
        return {}
    rows = (
        await db.execute(
            select(ClaimRelationship).where(
                ClaimRelationship.from_claim_id.in_(list(claim_ids)),
                ClaimRelationship.to_claim_id.in_(list(claim_ids)),
            )
        )
    ).scalars().all()
    return {(r.from_claim_id, r.to_claim_id, r.relationship_type): r for r in rows}


def _unit_matrix(embeddings: Sequence[object]) -> np.ndarray:
    """Row-normalised embedding matrix for one batched cosine pass."""
    matrix: np.ndarray = np.asarray(embeddings, dtype=np.float32)
    norms: np.ndarray = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalised: np.ndarray = matrix / np.maximum(norms, 1e-9)
    return normalised


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
        """Detect EVOLVED_FROM / SIMILAR_TO edges inside each topic.

        `claim_relationships` is treated as a materialized view of the most
        recent run: rows that already exist are upserted (score refreshed)
        rather than duplicated, and EVOLVED_FROM edges an evaluated claim no
        longer reproduces are pruned so lineage stays a single chain.
        SIMILAR_TO rows are deduplicated but never pruned — near-similarity is
        evidence, not a cluster-scoped decision.
        """
        logger.info("Starting mutation detection...")
        
        # Group claims by topic (exclude noise topic -1)
        topic_groups = defaultdict(list)
        for assignment in assignments:
            if assignment.topic_id != -1:
                topic_groups[assignment.topic_id].append(assignment.claim_id)

        relationships: list[ClaimRelationship] = []
        evo_threshold = self.settings.EVOLUTION_SIMILARITY_THRESHOLD
        sim_threshold = self.settings.SIMILAR_TO_THRESHOLD

        for claim_ids in topic_groups.values():
            if len(claim_ids) < 2:
                continue

            # Resolve claims and their temporal ordering
            # Order: published_at (if available), else extracted_at
            def get_time(cid: uuid.UUID) -> datetime:
                claim = claims_by_id[cid]
                article = articles_by_id[claim.article_id]
                return article.published_at or claim.extracted_at

            sorted_claim_ids = sorted(claim_ids, key=get_time)
            existing = await _existing_edges(db, sorted_claim_ids)

            # Claims without an embedding cannot participate in either role, so
            # the matrix is built over the embedded subset only — "earlier" stays
            # the temporal order within that subset.
            evaluated_ids = [
                cid
                for cid in sorted_claim_ids
                if claims_by_id[cid].embedding is not None
            ]
            evaluated: set[uuid.UUID] = set(evaluated_ids)

            # Candidate edges for this topic group: (from, to, type, score).
            candidates: list[
                tuple[uuid.UUID, uuid.UUID, RelationshipTypeEnum, float]
            ] = []
            if len(evaluated_ids) >= 2:
                unit = _unit_matrix(
                    [claims_by_id[cid].embedding for cid in evaluated_ids]
                )
                # One Gram matrix per topic group: every cosine similarity in a
                # single BLAS call, instead of a tensor allocation per pair.
                similarity = unit @ unit.T
                for i in range(1, len(evaluated_ids)):
                    current_id = evaluated_ids[i]
                    sims = similarity[i, :i]

                    # Vectorised equivalent of the per-pair loop:
                    #   EVOLVED_FROM = best (highest) score >= evo_threshold,
                    #     ties going to the first occurrence;
                    #   SIMILAR_TO   = every other earlier claim in
                    #     [sim_threshold, evo_threshold) — plus qualifying
                    #     non-improving ties, exactly as before.
                    qualifying = sims >= evo_threshold
                    running_max = np.maximum.accumulate(
                        np.where(qualifying, sims, -np.inf)
                    )
                    prev_max = np.concatenate(([-np.inf], running_max[:-1]))
                    improves = qualifying & (sims > prev_max)

                    for earlier_j in np.flatnonzero(~improves & (sims >= sim_threshold)):
                        candidates.append((
                            current_id,
                            evaluated_ids[int(earlier_j)],
                            RelationshipTypeEnum.SIMILAR_TO,
                            float(sims[int(earlier_j)]),
                        ))

                    best_idx = np.flatnonzero(improves)
                    if best_idx.size:
                        best_j = int(best_idx[-1])  # first occurrence of the maximum
                        candidates.append((
                            current_id,
                            evaluated_ids[best_j],
                            RelationshipTypeEnum.EVOLVED_FROM,
                            float(sims[best_j]),
                        ))

            # ---- reconcile candidates with what is already persisted -------
            # Upsert by (from, to, type): an edge is never inserted twice, and a
            # stored score is refreshed when this run disagrees with it.
            new_edges: list[ClaimRelationship] = []
            seen: set[tuple[uuid.UUID, uuid.UUID, RelationshipTypeEnum]] = set()
            for from_id, to_id, rtype, score in candidates:
                key = (from_id, to_id, rtype)
                if key in seen:
                    continue
                seen.add(key)
                row = existing.get(key)
                if row is not None:
                    if abs(row.score - score) > 1e-9:
                        row.score = score
                    relationships.append(row)
                else:
                    edge = ClaimRelationship(
                        from_claim_id=from_id,
                        to_claim_id=to_id,
                        relationship_type=rtype,
                        score=score,
                    )
                    new_edges.append(edge)
                    relationships.append(edge)

            # EVOLVED_FROM mirrors the latest run: each evaluated claim should
            # have at most one predecessor, so an edge this run did not
            # reproduce is stale (the claim moved clusters) and is pruned.
            chosen_evo: dict[uuid.UUID, uuid.UUID] = {
                f: t
                for f, t, rt, _ in candidates
                if rt == RelationshipTypeEnum.EVOLVED_FROM
            }
            stale = [
                row
                for row in existing.values()
                if row.relationship_type == RelationshipTypeEnum.EVOLVED_FROM
                and row.from_claim_id in evaluated
                and chosen_evo.get(row.from_claim_id) != row.to_claim_id
            ]
            for row in stale:
                await db.delete(row)
            if stale:
                # Release the unique keys before inserting replacements.
                await db.flush()

            if new_edges:
                db.add_all(new_edges)
                await db.flush()

        logger.info(
            "Mutation detection complete. %d relationships current.",
            len(relationships),
        )
        return relationships
