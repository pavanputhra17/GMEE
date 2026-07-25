from redis.asyncio import Redis

from app.core.config import get_settings


class RedisClient:
    def __init__(self) -> None:
        self.client: Redis | None = None

    async def get_client(self) -> Redis:
        if self.client is None:
            settings = get_settings()
            self.client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.client

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

redis_client = RedisClient()
