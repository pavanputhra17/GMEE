from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.models.source import Source


class RawArticle(BaseModel):
    title: str
    url: str
    content: str | None
    published_at: datetime | None
    author: str | None
    raw_metadata: dict[str, Any]


class MissingCredentialsError(Exception):
    """Raised when a collector cannot run because credentials are not configured."""


class BaseCollector(ABC):
    # Concrete collectors populate this in their __init__ via get_settings().
    settings: Settings

    @abstractmethod
    async def collect(self, source: Source) -> list[RawArticle]:
        """Fetch and return articles for a single source. Must not raise on
        expected failure modes (bad feed, rate limit, missing creds) —
        log and return an empty list instead. Only raise for truly
        unexpected errors the orchestrator should be aware of."""
