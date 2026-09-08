import logging
import uuid
from collections.abc import Sequence

from neo4j import AsyncSession

from app.db.neo4j_client import neo4j_client
from app.models.article import Article
from app.models.claim import Claim
from app.models.evolution import ClaimRelationship
from app.models.source import Source

logger = logging.getLogger(__name__)


class Neo4jWriter:
    async def sync_to_graph(
        self,
        claims: Sequence[Claim],
        articles_by_id: dict[uuid.UUID, Article],
        sources_by_id: dict[uuid.UUID, Source],
        relationships: Sequence[ClaimRelationship]
    ) -> bool:
        """
        Synchronizes claims, entities, sources, and their relationships to Neo4j.
        This is an idempotent operation using MERGE.
        If it fails, it logs the error but does not raise, to avoid breaking Postgres transactions.
        """
        try:
            driver = await neo4j_client.get_driver()
            async with driver.session() as session:
                await self._merge_claims_entities_sources(session, claims, articles_by_id, sources_by_id)
                await self._merge_relationships(session, relationships)
            logger.info("Neo4j graph sync completed successfully.")
            return True
        except Exception:
            logger.exception("Failed to sync to Neo4j")
            return False

    async def _merge_claims_entities_sources(
        self,
        session: AsyncSession,
        claims: Sequence[Claim],
        articles_by_id: dict[uuid.UUID, Article],
        sources_by_id: dict[uuid.UUID, Source],
    ) -> None:
        for claim in claims:
            article: Article = articles_by_id[claim.article_id]
            source: Source = sources_by_id[article.source_id]

            # Merge Source
            await session.run("""
                MERGE (s:Source {id: $id})
                SET s.name = $name, s.type = $type
            """, id=str(source.id), name=source.name, type=source.type.value)

            # Merge Claim
            await session.run("""
                MERGE (c:Claim {id: $id})
                SET c.text = $text, c.extracted_at = $extracted_at
            """, id=str(claim.id), text=claim.claim_text, extracted_at=claim.extracted_at.isoformat())

            # Merge PUBLISHED_BY
            await session.run("""
                MATCH (c:Claim {id: $claim_id})
                MATCH (s:Source {id: $source_id})
                MERGE (c)-[:PUBLISHED_BY]->(s)
            """, claim_id=str(claim.id), source_id=str(source.id))

            # Merge Entities and MENTIONS
            for entity in claim.entities:
                await session.run("""
                    MERGE (e:Entity {text: $text, type: $type})
                    WITH e
                    MATCH (c:Claim {id: $claim_id})
                    MERGE (c)-[:MENTIONS]->(e)
                """, text=entity.entity_text, type=entity.entity_type, claim_id=str(claim.id))

    async def _merge_relationships(self, session: AsyncSession, relationships: Sequence[ClaimRelationship]) -> None:
        for rel in relationships:
            await session.run(f"""
                MATCH (from_claim:Claim {{id: $from_id}})
                MATCH (to_claim:Claim {{id: $to_id}})
                MERGE (from_claim)-[r:{rel.relationship_type.value}]->(to_claim)
                SET r.score = $score
            """, from_id=str(rel.from_claim_id), to_id=str(rel.to_claim_id), score=rel.score)
