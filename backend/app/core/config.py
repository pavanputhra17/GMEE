from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_URL: str
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    REDIS_URL: str
    CORS_ORIGINS: str | list[str]
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    
    JWT_SECRET: str
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7

    # Data Collection
    COLLECTION_INTERVAL_MINUTES: int = 30
    NEWSAPI_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "python:gmee:v0.1.0"
    
    # Preprocessing
    NEAR_DUP_JACCARD_THRESHOLD: float = 0.75
    NEAR_DUP_WINDOW_DAYS: int = 14
    
    # NLP
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    NLP_MAX_ARTICLES_PER_CYCLE: int = 10

    # Evolution Engine
    MIN_CORPUS_SIZE_FOR_CLUSTERING: int = 30
    MIN_NEW_CLAIMS_TO_RECLUSTER: int = 10
    EVOLUTION_SIMILARITY_THRESHOLD: float = 0.85
    SIMILAR_TO_THRESHOLD: float = 0.75
    BERTOPIC_MIN_TOPIC_SIZE: int = 5

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Loads from local .env or parent root .env if running outside container
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
