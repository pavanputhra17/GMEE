import uuid

import pytest
from httpx import AsyncClient

from app.models.user import RoleEnum, User

pytestmark = pytest.mark.asyncio

async def test_nlp_trigger_endpoint_admin(async_client: AsyncClient):
    from app.api.deps import get_current_user
    from app.main import app
    
    # Mock admin user
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="admin@test.com", role=RoleEnum.admin)
    
    response = await async_client.post("/api/v1/nlp/trigger")
    assert response.status_code == 200
    assert "summary" in response.json()
    
    app.dependency_overrides.clear()

async def test_nlp_trigger_endpoint_non_admin(async_client: AsyncClient):
    from app.api.deps import get_current_user
    from app.main import app
    
    # Mock normal user
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="user@test.com", role=RoleEnum.user)
    
    response = await async_client.post("/api/v1/nlp/trigger")
    assert response.status_code == 403
    
    app.dependency_overrides.clear()

async def test_nlp_status_endpoint_auth(async_client: AsyncClient):
    from app.api.deps import get_current_user
    from app.main import app
    
    # Mock normal user
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="user@test.com", role=RoleEnum.user)
    
    response = await async_client.get("/api/v1/nlp/status")
    assert response.status_code == 200
    assert "status_counts" in response.json()
    
    app.dependency_overrides.clear()

async def test_nlp_status_endpoint_unauth(async_client: AsyncClient):
    # No user mocked
    response = await async_client.get("/api/v1/nlp/status")
    assert response.status_code == 401

