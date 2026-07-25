import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.article import Article
from app.models.claim import Claim
from app.models.evolution import ClaimClusterRun
from app.models.source import Source
from app.services.evolution.cluster_service import ClusterService
from app.services.evolution.mutation_detector import MutationDetector
from app.services.evolution.neo4j_writer import Neo4jWriter

logger = logging.getLogger(__name__)


class EvolutionOrchestrator:
    def __init__(self):
        self.settings = get_settings()
        self.cluster_service = ClusterService()
        self.mutation_detector = MutationDetector()
        self.neo4j_writer = Neo4jWriter()

    async def run_evolution_cycle(self, db: AsyncSession, force: bool = False) -> dict:
        """
        Executes the evolution engine: clustering, mutation detection, graph sync.
        Respects guards for minimum corpus size and debounce (new claims).
        """
        # 1. Corpus size check
        total_claims = await db.scalar(select(func.count(Claim.id))) or 0
        min_corpus = self.settings.MIN_CORPUS_SIZE_FOR_CLUSTERING

        if total_claims < min_corpus:
            logger.info(f"Skipping evolution cycle: corpus size {total_claims} < {min_corpus}.")
            return {
                "status": "insufficient_data",
                "claims_available": total_claims,
                "minimum_required": min_corpus
            }

        # 2. Debounce guard
        if not force:
            last_run = await db.scalar(
                select(ClaimClusterRun).order_by(ClaimClusterRun.run_at.desc()).limit(1)
            )
            if last_run:
                new_claims = total_claims - last_run.claims_in_corpus
                min_new = self.settings.MIN_NEW_CLAIMS_TO_RECLUSTER
                if new_claims < min_new:
                    logger.info(f"Skipping evolution cycle: {new_claims} new claims < {min_new}.")
                    return {
                        "status": "debounced",
                        "new_claims": new_claims,
                        "minimum_new_required": min_new,
                        "last_run_at": last_run.run_at.isoformat()
                    }

        logger.info(f"Starting evolution cycle (force={force}). Corpus size: {total_claims}")

        # Fetch all claims with their entities
        stmt = select(Claim).options(selectinload(Claim.entities))
        res = await db.execute(stmt)
        claims: Sequence[Claim] = res.scalars().all()

        # Build quick lookups for articles and sources
        article_ids = {c.article_id for c in claims}
        art_res = await db.execute(select(Article).where(Article.id.in_(article_ids)))
        articles_by_id = {a.id: a for a in art_res.scalars().all()}

        source_ids = {a.source_id for a in articles_by_id.values()}
        src_res = await db.execute(select(Source).where(Source.id.in_(source_ids)))
        sources_by_id = {s.id: s for s in src_res.scalars().all()}

        claims_by_id = {c.id: c for c in claims}

        # 3. Clustering
        try:
            cluster_run = await self.cluster_service.run_clustering(db, claims)
        except ImportError as e:
            logger.error(f"Clustering dependencies missing: {e}")
            return {"status": "error", "error": "BERTopic dependencies missing"}

        # 4. Mutation Detection
        # Fetch the assignments just created in the current transaction
        assignments = cluster_run.assignments
        relationships = await self.mutation_detector.run_mutation_detection(
            db, assignments, claims_by_id, articles_by_id
        )

        # Commit Postgres transaction so we have durable IDs before Neo4j
        await db.commit()
        await db.refresh(cluster_run)

        # 5. Neo4j Sync
        neo4j_success = await self.neo4j_writer.sync_to_graph(
            claims, articles_by_id, sources_by_id, relationships
        )

        valid_clusters = len({a.topic_id for a in assignments if a.topic_id != -1})

        return {
            "status": "success",
            "corpus_size": total_claims,
            "clusters_found": valid_clusters,
            "relationships_detected": len(relationships),
            "neo4j_sync_success": neo4j_success
        }
