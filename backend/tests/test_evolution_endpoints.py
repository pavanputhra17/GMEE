from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.user import RoleEnum


@pytest.mark.asyncio
async def test_evolution_trigger_auth_non_admin(client: AsyncClient, get_auth_headers):
    # Non-admin user should get 403
    headers = get_auth_headers(RoleEnum.user)
    resp = await client.post("/api/v1/evolution/trigger", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_evolution_trigger_auth_admin(client: AsyncClient, get_auth_headers):
    headers = get_auth_headers(RoleEnum.admin)
    with patch("app.api.v1.evolution.EvolutionOrchestrator") as MockOrchestrator:
        instance = MockOrchestrator.return_value
        instance.run_evolution_cycle.return_value = {"status": "success"}

        resp = await client.post("/api/v1/evolution/trigger?force=true", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["result"]["status"] == "success"
        
        # Verify force flag passed
        instance.run_evolution_cycle.assert_called_once()
        assert instance.run_evolution_cycle.call_args.kwargs["force"] is True


@pytest.mark.asyncio
async def test_evolution_status_unauth(client: AsyncClient):
    resp = await client.get("/api/v1/evolution/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_evolution_status_auth(client: AsyncClient, get_auth_headers):
    headers = get_auth_headers(RoleEnum.user)
    resp = await client.get("/api/v1/evolution/status", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_evolution_clusters_unauth(client: AsyncClient):
    resp = await client.get("/api/v1/evolution/clusters")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_evolution_clusters_auth(client: AsyncClient, get_auth_headers):
    headers = get_auth_headers(RoleEnum.user)
    resp = await client.get("/api/v1/evolution/clusters", headers=headers)
    assert resp.status_code == 200
