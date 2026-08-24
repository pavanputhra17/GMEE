import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    # Health router is mounted under /api/v1 (see app/main.py)
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_readiness_check(async_client: AsyncClient) -> None:
    # Since we don't mock the DB connections in this basic scaffold, 
    # and they'll fail in isolation unless the DBs are running,
    # the readiness probe will likely return 503 and report failures.
    # The requirement is to assert it returns a well-formed body.
    response = await async_client.get("/api/v1/health/ready")
    
    assert response.status_code in (200, 503)
    data = response.json()
    assert "postgres" in data
    assert "neo4j" in data
    assert "redis" in data
    assert "status" in data
