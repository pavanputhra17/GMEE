import logging
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from neo4j import AsyncSession

from app.db.neo4j_client import neo4j_client
from app.models.article import Article
from app.models.claim import Claim
from app.models.evolution import ClaimRelationship, RelationshipTypeEnum
from app.models.source import Source

logger = logging.getLogger(__name__)

# Rows per UNWIND round-trip. 500 keeps each parameter payload well under
# Neo4j's bolt limits while cutting a 10k-claim sync from ~40k round-trips
# down to a couple of dozen statements.
_BATCH_SIZE = 500

# The only relationship types allowed into the (unavoidably f-string'd)
# MERGE statement below. Values come from the StrEnum, so they are safe, but
# an explicit allow-list keeps that provably true under future edits.
_REL_TYPE_NAMES = frozenset(rt.value for rt in RelationshipTypeEnum)


def _chunks(rows: list[Any]) -> Iterator[list[Any]]:
    for i in range(0, len(rows), _BATCH_SIZE):
        yield rows[i : i + _BATCH_SIZE]


class Neo4jWriter:
    """Idempotent Postgres -> Neo4j sync.

    Every write is a batched ``UNWIND`` — a handful of statements per cycle
    instead of 4+ round-trips per claim. After the merge, ``EVOLVED_FROM``
    edges rooted at claims *evaluated in this run* that the authoritative
    Postgres table no longer holds are deleted, so Neo4j mirrors the
    deduplicated relationship table instead of accumulating stale lineage
    from earlier, pre-dedup runs.
    """

    async def sync_to_graph(
        self,
        claims: Sequence[Claim],
        articles_by_id: dict[uuid.UUID, Article],
        sources_by_id: dict[uuid.UUID, Source],
        relationships: Sequence[ClaimRelationship],
        evaluated_claim_ids: set[uuid.UUID] | None = None,
    ) -> bool:
        """
        Synchronizes claims, entities, sources, and their relationships to Neo4j.
        This is an idempotent operation using MERGE.
        If it fails, it logs the error but does not raise, to avoid breaking Postgres transactions.

        ``evaluated_claim_ids`` are the claims whose lineage the mutation
        detector just re-examined; stale-edge pruning is scoped to them, so
        edges of claims *not* evaluated this run are never touched. Pruning
        is skipped entirely when the set is omitted.
        """
        try:
            driver = await neo4j_client.get_driver()
            async with driver.session() as session:
                await self._merge_claims_entities_sources(session, claims, articles_by_id, sources_by_id)
                await self._merge_relationships(session, relationships)
                if evaluated_claim_ids:
                    await self._prune_stale_evolved(
                        session,
                        {str(cid) for cid in evaluated_claim_ids},
                        relationships,
                    )
            logger.info(
                "Neo4j graph sync completed: %d claims, %d edges",
                len(claims),
                len(relationships),
            )
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
        # 1. Sources — one UNWIND statement per batch
        source_rows = [
            {"id": str(s.id), "name": s.name, "type": s.type.value}
            for s in sources_by_id.values()
        ]
        for chunk in _chunks(source_rows):
            await session.run("""
                UNWIND $rows AS row
                MERGE (s:Source {id: row.id})
                SET s.name = row.name, s.type = row.type
            """, rows=chunk)

        # 2. Claims
        claim_rows = [
            {"id": str(c.id), "text": c.claim_text, "extracted_at": c.extracted_at.isoformat()}
            for c in claims
        ]
        for chunk in _chunks(claim_rows):
            await session.run("""
                UNWIND $rows AS row
                MERGE (c:Claim {id: row.id})
                SET c.text = row.text, c.extracted_at = row.extracted_at
            """, rows=chunk)

        # 3. Claim -> Source edges
        published_rows = [
            {
                "claim_id": str(c.id),
                "source_id": str(articles_by_id[c.article_id].source_id),
            }
            for c in claims
            if c.article_id in articles_by_id
        ]
        for chunk in _chunks(published_rows):
            await session.run("""
                UNWIND $rows AS row
                MATCH (c:Claim {id: row.claim_id})
                MATCH (s:Source {id: row.source_id})
                MERGE (c)-[:PUBLISHED_BY]->(s)
            """, rows=chunk)

        # 4. Entities and Claim -> Entity edges
        entity_rows = [
            {"claim_id": str(c.id), "text": e.entity_text, "type": e.entity_type}
            for c in claims
            for e in c.entities
        ]
        for chunk in _chunks(entity_rows):
            await session.run("""
                UNWIND $rows AS row
                MATCH (c:Claim {id: row.claim_id})
                MERGE (e:Entity {text: row.text, type: row.type})
                MERGE (c)-[:MENTIONS]->(e)
            """, rows=chunk)

    async def _merge_relationships(self, session: AsyncSession, relationships: Sequence[ClaimRelationship]) -> None:
        by_type: dict[str, list[dict[str, Any]]] = {}
        for rel in relationships:
            rel_type = rel.relationship_type.value
            if rel_type not in _REL_TYPE_NAMES:
                logger.warning(
                    "Skipping unknown relationship type %r in graph sync", rel_type
                )
                continue
            by_type.setdefault(rel_type, []).append({
                "from_id": str(rel.from_claim_id),
                "to_id": str(rel.to_claim_id),
                "score": rel.score,
            })
        for rel_type, rows in by_type.items():
            for chunk in _chunks(rows):
                # rel_type is allow-listed above, never user input.
                await session.run(f"""
                    UNWIND $rows AS row
                    MATCH (from_claim:Claim {{id: row.from_id}})
                    MATCH (to_claim:Claim {{id: row.to_id}})
                    MERGE (from_claim)-[r:{rel_type}]->(to_claim)
                    SET r.score = row.score
                """, rows=chunk)

    async def _prune_stale_evolved(
        self,
        session: AsyncSession,
        evaluated_claim_ids: set[str],
        relationships: Sequence[ClaimRelationship],
    ) -> None:
        """Delete EVOLVED_FROM edges the authoritative run no longer reproduces.

        Postgres prunes stale edges only for claims the mutation detector
        re-examined (``evaluated_claim_ids``); this mirrors that scoping so
        Neo4j cannot drift from the deduplicated relationship table. ``keep``
        is the current edge set for those same claims, filtered per batch so
        the parameter payload stays small.
        """
        keep_all = [
            (str(r.from_claim_id), str(r.to_claim_id))
            for r in relationships
            if r.relationship_type == RelationshipTypeEnum.EVOLVED_FROM
        ]
        for id_chunk in _chunks(sorted(evaluated_claim_ids)):
            chunk_set = set(id_chunk)
            keep = [pair for pair in keep_all if pair[0] in chunk_set]
            await session.run("""
                UNWIND $claim_ids AS cid
                MATCH (c:Claim {id: cid})-[r:EVOLVED_FROM]->(t:Claim)
                WHERE NOT [c.id, t.id] IN $keep
                DELETE r
            """, claim_ids=id_chunk, keep=[list(pair) for pair in keep])

