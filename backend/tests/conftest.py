import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["POSTGRES_URL"] = "postgresql+asyncpg://postgres:postgres@localhost/test"
os.environ["NEO4J_URI"] = "neo4j://localhost:7687"
os.environ["NEO4J_USER"] = "test"
os.environ["NEO4J_PASSWORD"] = "test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["JWT_SECRET"] = "super_secret_test_jwt_key_that_is_at_least_32_chars"

from app.api.deps import get_db_session, get_redis_client
from app.main import app
from app.models.base import Base

# Test DB Engine
engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine, class_=AsyncSession)

@pytest_asyncio.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[FakeAsyncRedis, None]:
    client = FakeAsyncRedis()
    yield client
    await client.flushall()

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession, redis_client: FakeAsyncRedis) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()
