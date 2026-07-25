import os

from app.core.config import Settings


def test_settings_cors_origins_parsing() -> None:
    os.environ["POSTGRES_URL"] = "postgresql+asyncpg://postgres:postgres@localhost/test"
    os.environ["NEO4J_URI"] = "neo4j://localhost:7687"
    os.environ["NEO4J_USER"] = "test"
    os.environ["NEO4J_PASSWORD"] = "test"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://localhost:5173"
    
    settings = Settings()  # type: ignore
    
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]

def test_settings_cors_origins_json_parsing() -> None:
    os.environ["POSTGRES_URL"] = "postgresql+asyncpg://postgres:postgres@localhost/test"
    os.environ["NEO4J_URI"] = "neo4j://localhost:7687"
    os.environ["NEO4J_USER"] = "test"
    os.environ["NEO4J_PASSWORD"] = "test"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["CORS_ORIGINS"] = '["http://localhost:3000", "http://localhost:5173"]'
    
    settings = Settings()  # type: ignore
    
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]
