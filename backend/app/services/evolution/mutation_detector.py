import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence

from sentence_transformers.util import cos_sim
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


class MutationDetector:
    def __init__(self):
        self.settings = get_settings()

    async def run_mutation_detection(self, db: AsyncSession, assignments: Sequence[ClaimClusterAssignment], claims_by_id: dict[uuid.UUID, Claim], articles_by_id: dict[uuid.UUID, Article]) -> list[ClaimRelationship]:
        logger.info("Starting mutation detection...")
        
        # Group claims by topic (exclude noise topic -1)
        topic_groups = defaultdict(list)
        for assignment in assignments:
            if assignment.topic_id != -1:
                topic_groups[assignment.topic_id].append(assignment.claim_id)

        relationships = []
        evo_threshold = self.settings.EVOLUTION_SIMILARITY_THRESHOLD
        sim_threshold = self.settings.SIMILAR_TO_THRESHOLD

        for topic_id, claim_ids in topic_groups.items():
            if len(claim_ids) < 2:
                continue

            # Resolve claims and their temporal ordering
            # Order: published_at (if available), else extracted_at
            def get_time(cid: uuid.UUID):
                claim = claims_by_id[cid]
                article = articles_by_id[claim.article_id]
                return article.published_at or claim.extracted_at

            sorted_claim_ids = sorted(claim_ids, key=get_time)

            # Compare each claim against earlier claims in the same cluster
            for i, current_id in enumerate(sorted_claim_ids):
                current_claim = claims_by_id[current_id]
                current_emb = current_claim.embedding
                if current_emb is None:
                    continue

                best_evo_score = -1.0
                best_evo_target = None
                
                # Compare to all earlier claims
                for j in range(i):
                    earlier_id = sorted_claim_ids[j]
                    earlier_claim = claims_by_id[earlier_id]
                    earlier_emb = earlier_claim.embedding
                    if earlier_emb is None:
                        continue

                    # Calculate cosine similarity
                    # Sentence-transformers cos_sim expects 2D arrays, returns 2D tensor
                    sim_tensor = cos_sim([current_emb], [earlier_emb])
                    score = float(sim_tensor[0][0])

                    if score >= evo_threshold and score > best_evo_score:
                        best_evo_score = score
                        best_evo_target = earlier_id
                    elif score >= sim_threshold:
                        # Record SIMILAR_TO relationship
                        # SIMILAR_TO is symmetric in concept, but we store it as a directed edge.
                        relationships.append(ClaimRelationship(
                            from_claim_id=current_id,
                            to_claim_id=earlier_id,
                            relationship_type=RelationshipTypeEnum.SIMILAR_TO,
                            score=score
                        ))
                
                # Record EVOLVED_FROM for the best match above threshold
                if best_evo_target:
                    relationships.append(ClaimRelationship(
                        from_claim_id=current_id,
                        to_claim_id=best_evo_target,
                        relationship_type=RelationshipTypeEnum.EVOLVED_FROM,
                        score=best_evo_score
                    ))
                    
        if relationships:
            db.add_all(relationships)
            await db.flush()

        logger.info(f"Mutation detection complete. Found {len(relationships)} candidate relationships.")
        return relationships
