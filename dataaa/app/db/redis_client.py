import logging

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self) -> None:
        self.client: Redis | None = None
        self._disabled = False

    async def get_client(self) -> Redis:
        if self._disabled:
            raise RuntimeError("Redis is not configured (REDIS_URL is empty)")
        if self.client is None:
            settings = get_settings()
            if not settings.REDIS_URL:
                self._disabled = True
                logger.warning("REDIS_URL not set — Redis features disabled")
                raise RuntimeError("Redis is not configured (REDIS_URL is empty)")
            self.client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.client

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

redis_client = RedisClient()

