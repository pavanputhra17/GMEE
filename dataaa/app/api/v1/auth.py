from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, get_redis_client
from app.core.ops_security import record_audit
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    logout_user,
    register_user,
    rotate_refresh_token,
)

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    user_in: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> Any:
    device_info = request.headers.get("user-agent")
    result = await register_user(db, user_in, device_info)
    await record_audit(db, actor=user_in.email, action="auth.register", request=request)
    return result

@router.post("/login", response_model=TokenResponse)
async def login(
    login_in: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
) -> Any:
    ip = request.client.host if request.client else "unknown"
    device_info = request.headers.get("user-agent")
    result = await authenticate_user(db, redis, login_in, ip, device_info)
    await record_audit(
        db, actor=login_in.email, action="auth.login", detail={"ip": ip}, request=request
    )
    return result

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    refresh_in: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> Any:
    device_info = request.headers.get("user-agent")
    return await rotate_refresh_token(db, refresh_in, device_info)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def logout(
    logout_in: LogoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
) -> Response:
    auth_header = request.headers.get("Authorization")
    await logout_user(db, redis, logout_in, current_user, auth_header)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    return current_user
