import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_helpers import is_access_token_blocklisted
from app.core.security import decode_access_token
from app.db.neo4j_client import neo4j_client
from app.db.postgres import async_session_maker
from app.db.redis_client import redis_client
from app.models.user import RoleEnum, User
from app.repositories import user_repository

security = HTTPBearer()

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def get_neo4j_driver() -> AsyncDriver:
    return await neo4j_client.get_driver()

async def get_redis_client() -> AsyncGenerator[Redis, None]:
    client = await redis_client.get_client()
    try:
        yield client
    finally:
        pass

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception
        
    user_id: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")
    
    if user_id is None or jti is None:
        raise credentials_exception
        
    if await is_access_token_blocklisted(redis, jti):
        raise credentials_exception
        
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception
        
    user = await user_repository.get_by_id(db, user_uuid)
    if user is None or not user.is_active:
        raise credentials_exception
        
    return user

def require_role(*allowed_roles: RoleEnum | str) -> Callable[..., Any]:
    allowed = [r.value if isinstance(r, RoleEnum) else r for r in allowed_roles]
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker
