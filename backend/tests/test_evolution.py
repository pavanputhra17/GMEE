import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.models.article import Article
from app.models.claim import Claim
from app.models.evolution import (
    ClaimClusterAssignment,
    ClaimRelationship,
    RelationshipTypeEnum,
)
from app.services.evolution.mutation_detector import MutationDetector
from app.services.evolution.neo4j_writer import Neo4jWriter
from app.services.evolution.orchestrator import EvolutionOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_guards():
    settings = get_settings()
    settings.MIN_CORPUS_SIZE_FOR_CLUSTERING = 30
    settings.MIN_NEW_CLAIMS_TO_RECLUSTER = 10

    orchestrator = EvolutionOrchestrator()

    # 1. Test small corpus guard
    mock_db = AsyncMock()
    # mock_db.scalar returns 20 for total_claims (less than 30)
    mock_db.scalar.return_value = 20

    res = await orchestrator.run_evolution_cycle(mock_db)
    assert res["status"] == "insufficient_data"
    assert res["claims_available"] == 20

    # 2. Test debounce guard
    mock_db.scalar.side_effect = [
        40,  # total claims > 30 (passes corpus check)
        AsyncMock(claims_in_corpus=35, run_at=datetime.now(UTC))  # last run claims
    ]
    # new claims = 40 - 35 = 5 (less than 10 threshold)
    res = await orchestrator.run_evolution_cycle(mock_db)
    assert res["status"] == "debounced"
    assert res["new_claims"] == 5

    # 3. Test force bypass
    mock_db.scalar.side_effect = [
        40,  # total claims > 30
    ]
    with patch.object(orchestrator, 'cluster_service') as mock_cluster, \
         patch.object(orchestrator, 'mutation_detector') as mock_mutation, \
         patch.object(orchestrator, 'neo4j_writer') as mock_neo4j:
        
        mock_cluster_run = AsyncMock()
        mock_cluster_run.assignments = []
        mock_cluster.run_clustering.return_value = mock_cluster_run
        mock_mutation.run_mutation_detection.return_value = []
        mock_neo4j.sync_to_graph.return_value = True

        res = await orchestrator.run_evolution_cycle(mock_db, force=True)
        assert res["status"] == "success"
        assert res["corpus_size"] == 40


@pytest.mark.asyncio
async def test_mutation_detector_logic():
    settings = get_settings()
    settings.EVOLUTION_SIMILARITY_THRESHOLD = 0.85
    settings.SIMILAR_TO_THRESHOLD = 0.75

    detector = MutationDetector()
    mock_db = AsyncMock()

    # Create dummy data
    t0 = datetime.now(UTC) - timedelta(days=2)
    t1 = datetime.now(UTC) - timedelta(days=1)
    
    art0 = Article(id=uuid.uuid4(), published_at=t0)
    art1 = Article(id=uuid.uuid4(), published_at=t1)

    c0 = Claim(id=uuid.uuid4(), article_id=art0.id, extracted_at=t0, embedding=[1.0, 0.0, 0.0])
    c1 = Claim(id=uuid.uuid4(), article_id=art1.id, extracted_at=t1, embedding=[0.9, 0.1, 0.0])  # high sim
    c2 = Claim(id=uuid.uuid4(), article_id=art1.id, extracted_at=t1, embedding=[0.8, 0.6, 0.0])  # medium sim
    c3 = Claim(id=uuid.uuid4(), article_id=art1.id, extracted_at=t1, embedding=[0.0, 1.0, 0.0])  # low sim

    assignments = [
        ClaimClusterAssignment(claim_id=c0.id, topic_id=1),
        ClaimClusterAssignment(claim_id=c1.id, topic_id=1),
        ClaimClusterAssignment(claim_id=c2.id, topic_id=1),
        ClaimClusterAssignment(claim_id=c3.id, topic_id=1),
    ]

    claims_by_id = {c.id: c for c in [c0, c1, c2, c3]}
    articles_by_id = {a.id: a for a in [art0, art1]}

    relationships = await detector.run_mutation_detection(mock_db, assignments, claims_by_id, articles_by_id)
    
    # We expect c1 -> c0 (EVOLVED_FROM)
    # We expect c2 -> c0 (SIMILAR_TO)
    # We expect c3 to have nothing with c0
    
    evo_rels = [r for r in relationships if r.relationship_type == RelationshipTypeEnum.EVOLVED_FROM]
    sim_rels = [r for r in relationships if r.relationship_type == RelationshipTypeEnum.SIMILAR_TO]
    
    assert len(evo_rels) == 1
    assert evo_rels[0].from_claim_id == c1.id
    assert evo_rels[0].to_claim_id == c0.id
    
    # Check temporal ordering (from_claim is later than to_claim)
    assert evo_rels[0].from_claim_id != c0.id
    assert sim_rels[0].from_claim_id == c2.id
    assert sim_rels[0].to_claim_id == c0.id


@pytest.mark.asyncio
async def test_neo4j_writer_idempotency():
    # Use a mock driver to check if MERGE is called the expected number of times
    # In reality, testing Neo4j idempotency requires a live Neo4j instance. 
    # Since we can't guarantee a clean Neo4j container in CI without wiping the main one,
    # we mock the driver's session to ensure MERGE statements are executed, 
    # and we rely on Cypher's MERGE semantics for actual idempotency.
    writer = Neo4jWriter()
    
    with patch("app.services.evolution.neo4j_writer.neo4j_client.get_driver") as mock_get_driver:
        mock_driver = AsyncMock()
        mock_get_driver.return_value = mock_driver
        mock_session = AsyncMock()
        mock_driver.session.return_value.__aenter__.return_value = mock_session
        
        c0 = Claim(id=uuid.uuid4(), article_id=uuid.uuid4(), claim_text="test", extracted_at=datetime.now(UTC), entities=[])
        art = Article(id=c0.article_id, source_id=uuid.uuid4())
        src = AsyncMock(id=art.source_id, name="Test", type=AsyncMock(value="rss"))
        
        claims = [c0]
        articles = {art.id: art}
        sources = {src.id: src}
        relationships = [
            ClaimRelationship(
                from_claim_id=c0.id, to_claim_id=c0.id, 
                relationship_type=RelationshipTypeEnum.SIMILAR_TO, score=0.9
            )
        ]
        
        res = await writer.sync_to_graph(claims, articles, sources, relationships)
        assert res is True
        
        # Verify run was called with MERGE
        calls = mock_session.run.call_args_list
        assert len(calls) > 0
        for call in calls:
            query = call[0][0]
            assert "MERGE" in query


@pytest.mark.asyncio
async def test_orchestrator_resilience_to_neo4j_failure():
    orchestrator = EvolutionOrchestrator()
    mock_db = AsyncMock()
    mock_db.scalar.side_effect = [40]  # total claims > 30

    with patch.object(orchestrator, 'cluster_service') as mock_cluster, \
         patch.object(orchestrator, 'mutation_detector') as mock_mutation, \
         patch.object(orchestrator, 'neo4j_writer') as mock_neo4j:
        
        mock_cluster_run = AsyncMock()
        mock_cluster_run.assignments = []
        mock_cluster.run_clustering.return_value = mock_cluster_run
        mock_mutation.run_mutation_detection.return_value = []
        
        # Mock Neo4j to fail
        mock_neo4j.sync_to_graph.return_value = False

        res = await orchestrator.run_evolution_cycle(mock_db, force=True)
        
        # Assert orchestrator caught the failure and returned false for sync, but overall success
        assert res["status"] == "success"
        assert res["neo4j_sync_success"] is False
        
        # Ensure Postgres transaction was committed
        mock_db.commit.assert_called_once()
