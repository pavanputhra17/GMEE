import uuid

import pytest
from httpx import AsyncClient

from app.models.user import RoleEnum, User

pytestmark = pytest.mark.asyncio


def _override_user(role: RoleEnum = RoleEnum.user) -> None:
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="user@test.com", role=role
    )


def _clear_overrides() -> None:
    from app.main import app

    app.dependency_overrides.clear()


async def test_evolution_trigger_endpoint_admin(async_client: AsyncClient):
    _override_user(RoleEnum.admin)
    from unittest.mock import AsyncMock, patch

    try:
        with patch("app.api.v1.evolution.EvolutionOrchestrator") as mock_orch:
            instance = mock_orch.return_value
            instance.run_evolution_cycle = AsyncMock(return_value={"status": "success"})

            resp = await async_client.post("/api/v1/evolution/trigger?force=true")
            assert resp.status_code == 200
            assert instance.run_evolution_cycle.call_args.kwargs["force"] is True
    finally:
        _clear_overrides()


async def test_evolution_status_unauth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/evolution/status")
    assert resp.status_code == 401


async def test_evolution_status_auth(async_client: AsyncClient):
    _override_user(RoleEnum.user)
    try:
        resp = await async_client.get("/api/v1/evolution/status")
        assert resp.status_code == 200
    finally:
        _clear_overrides()


async def test_evolution_clusters_unauth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/evolution/clusters")
    assert resp.status_code == 401


async def test_evolution_clusters_auth(async_client: AsyncClient):
    _override_user(RoleEnum.user)
    try:
        resp = await async_client.get("/api/v1/evolution/clusters")
        assert resp.status_code == 200
    finally:
        _clear_overrides()
