import pytest
from fastapi import APIRouter, Depends
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.security import verify_password
from app.main import app
from app.models.session import Session
from app.models.user import RoleEnum, User

# Test route for role checking
test_router = APIRouter()
@test_router.get("/admin-only")
async def admin_only_route(user: User = Depends(require_role("admin"))) -> dict[str, str]:
    return {"status": "ok"}
app.include_router(test_router, prefix="/api/v1/test")

@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # 1. Register -> 201
    payload = {"email": "test1@example.com", "password": "password123", "full_name": "Test User"}
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    
    # Check DB
    result = await db_session.execute(select(User).where(User.email == "test1@example.com"))
    user = result.scalars().first()
    assert user is not None
    assert user.hashed_password != "password123"
    assert verify_password(user.hashed_password, "password123")

@pytest.mark.asyncio
async def test_register_duplicate(async_client: AsyncClient) -> None:
    # 2. Duplicate email register -> 409
    payload = {"email": "duplicate@example.com", "password": "password123"}
    await async_client.post("/api/v1/auth/register", json=payload)
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # Setup user
    payload = {"email": "login@example.com", "password": "password123"}
    await async_client.post("/api/v1/auth/register", json=payload)
    
    # 3. Login with correct credentials -> 200
    response = await async_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # session row created
    result = await db_session.execute(select(Session))
    sessions = result.scalars().all()
    assert len(sessions) > 0

@pytest.mark.asyncio
async def test_login_wrong_password(async_client: AsyncClient) -> None:
    payload = {"email": "wrongpass@example.com", "password": "password123"}
    await async_client.post("/api/v1/auth/register", json=payload)
    
    # 4. Wrong password -> generic 401
    response = await async_client.post("/api/v1/auth/login", json={"email": "wrongpass@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

@pytest.mark.asyncio
async def test_login_nonexistent_email(async_client: AsyncClient) -> None:
    # 5. Nonexistent email -> SAME generic 401
    response = await async_client.post("/api/v1/auth/login", json={"email": "nonexistent@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

@pytest.mark.asyncio
async def test_login_rate_limit(async_client: AsyncClient) -> None:
    # 6. Exceeding login rate limit -> 429
    email = "ratelimit@example.com"
    payload = {"email": email, "password": "wrong"}
    # 5 attempts fail with 401
    for _ in range(5):
        res = await async_client.post("/api/v1/auth/login", json=payload)
        assert res.status_code == 401
    
    # 6th attempt should be 429
    res = await async_client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 429
    assert "Retry-After" in res.headers

@pytest.mark.asyncio
async def test_get_me_success(async_client: AsyncClient) -> None:
    # 7. GET /me with valid access token -> 200, correct profile
    payload = {"email": "me@example.com", "password": "password123", "full_name": "Me User"}
    reg_res = await async_client.post("/api/v1/auth/register", json=payload)
    access_token = reg_res.json()["access_token"]
    
    res = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "me@example.com"
    assert data["full_name"] == "Me User"
    assert "hashed_password" not in data

@pytest.mark.asyncio
async def test_get_me_invalid_token(async_client: AsyncClient) -> None:
    # 8. GET /me with no token / malformed -> 401
    res1 = await async_client.get("/api/v1/auth/me")
    assert res1.status_code == 401
    
    res2 = await async_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed_token"})
    assert res2.status_code == 401

@pytest.mark.asyncio
async def test_refresh_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # 9. POST /refresh with valid refresh token -> 200
    reg_res = await async_client.post("/api/v1/auth/register", json={"email": "refresh@example.com", "password": "password123"})
    refresh_token = reg_res.json()["refresh_token"]
    
    res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    
    # Old session marked revoked
    from app.core.security import hash_refresh_token
    token_hash = hash_refresh_token(refresh_token)
    session = (await db_session.execute(select(Session).where(Session.refresh_token_hash == token_hash))).scalars().first()
    assert session is not None
    assert session.revoked == True

@pytest.mark.asyncio
async def test_refresh_reuse_detection(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # 10. POST /refresh reusing already-rotated refresh token -> 401 + revoke all active sessions
    payload = {"email": "reuse@example.com", "password": "password123"}
    reg_res = await async_client.post("/api/v1/auth/register", json=payload)
    refresh_token_1 = reg_res.json()["refresh_token"]
    
    # Create another session by logging in again
    log_res = await async_client.post("/api/v1/auth/login", json=payload)
    refresh_token_2 = log_res.json()["refresh_token"]
    
    # Rotate refresh_token_1 legitimately
    await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token_1})
    
    # Reuse refresh_token_1 maliciously
    res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token_1})
    assert res.status_code == 401
    
    # Assert all sessions are revoked
    user_id = (await db_session.execute(select(User.id).where(User.email == "reuse@example.com"))).scalar()
    sessions = (await db_session.execute(select(Session).where(Session.user_id == user_id))).scalars().all()
    assert len(sessions) > 0
    for s in sessions:
        assert s.revoked == True
        
    # Specifically assert that refresh_token_2 is rejected now
    res_2 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token_2})
    assert res_2.status_code == 401

@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient) -> None:
    # 11. POST /logout -> 204
    payload = {"email": "logout@example.com", "password": "password123"}
    reg_res = await async_client.post("/api/v1/auth/register", json=payload)
    access_token = reg_res.json()["access_token"]
    refresh_token = reg_res.json()["refresh_token"]
    
    headers = {"Authorization": f"Bearer {access_token}"}
    res = await async_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token}, headers=headers)
    assert res.status_code == 204
    
    # Access token rejected (blocklist)
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 401
    
    # Refresh token rejected
    ref_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_res.status_code == 401

@pytest.mark.asyncio
async def test_require_role(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # 12. require_role dependency
    payload_user = {"email": "user_role@example.com", "password": "password123"}
    res_user = await async_client.post("/api/v1/auth/register", json=payload_user)
    token_user = res_user.json()["access_token"]
    
    payload_admin = {"email": "admin_role@example.com", "password": "password123"}
    res_admin = await async_client.post("/api/v1/auth/register", json=payload_admin)
    token_admin = res_admin.json()["access_token"]
    
    # Manually make admin_role an admin in DB
    user = (await db_session.execute(select(User).where(User.email == "admin_role@example.com"))).scalars().first()
    assert user is not None
    user.role = RoleEnum.admin
    await db_session.commit()
    
    # user role should 403
    route_res_1 = await async_client.get("/api/v1/test/admin-only", headers={"Authorization": f"Bearer {token_user}"})
    assert route_res_1.status_code == 403
    
    # admin role should 200
    route_res_2 = await async_client.get("/api/v1/test/admin-only", headers={"Authorization": f"Bearer {token_admin}"})
    assert route_res_2.status_code == 200
