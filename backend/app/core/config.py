from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_URL: str
    
    @field_validator("POSTGRES_URL", mode="before")
    @classmethod
    def fix_postgres_scheme(cls, v: Any) -> Any:
        """Render provides postgres:// but asyncpg needs postgresql+asyncpg://."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    NEO4J_URI: str = ""
    NEO4J_USER: str = ""
    NEO4J_PASSWORD: str = ""
    REDIS_URL: str = ""
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
    HUGGINGFACE_API_KEY: str = ""
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    NLP_MAX_ARTICLES_PER_CYCLE: int = 10

    # Evolution Engine
    MIN_CORPUS_SIZE_FOR_CLUSTERING: int = 30
    MIN_NEW_CLAIMS_TO_RECLUSTER: int = 10
    EVOLUTION_SIMILARITY_THRESHOLD: float = 0.85
    SIMILAR_TO_THRESHOLD: float = 0.75
    BERTOPIC_MIN_TOPIC_SIZE: int = 5

    # Verdict engine calibration
    # Cosine-similarity window in which two claims are considered "the same
    # assertion". The original hard-coded 0.75 floor proved too strict on real
    # news corpora (cross-outlet paraphrases of one event typically sit at
    # 0.55–0.75), collapsing ~95% of verdicts to UNSUPPORTED.
    VERDICT_NEAR_MIN: float = 0.60
    VERDICT_NEAR_MAX: float = 0.97

    # Embedding model. Default: all-mpnet-base-v2 (768-dim, English).
    # Cross-lingual lineage: set to paraphrase-multilingual-mpnet-base-v2
    # (also 768-dim, 50+ languages) — a drop-in swap for existing vector
    # columns. NOTE: changing the model after data exists requires
    # re-embedding the whole corpus (scripts/embed_articles.py) or the
    # vector spaces are incomparable.
    EMBEDDING_MODEL: str = "all-mpnet-base-v2"

    # Process model: run the APScheduler inside this process (dev / single
    # node). Set to false for API-only replicas and run scripts/run_nlp_cycle.py
    # as a separate process so heavy cycles never restart with the API.
    ENABLE_SCHEDULER: bool = True

    # Rate limiting. Disable in the test suite (tests share one IP and would
    # trip the login limiter against each other / against dev usage).
    RATE_LIMIT_ENABLED: bool = True

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
