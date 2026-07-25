from datetime import UTC, datetime

from redis.asyncio import Redis


async def blocklist_access_token(redis: Redis, jti: str, expires_at: datetime) -> None:
    now = datetime.now(UTC)
    ttl = int((expires_at - now).total_seconds())
    if ttl > 0:
        await redis.set(f"gmee:auth:blocklist:{jti}", "revoked", ex=ttl)

async def is_access_token_blocklisted(redis: Redis, jti: str) -> bool:
    exists = await redis.exists(f"gmee:auth:blocklist:{jti}")
    return exists > 0

async def check_login_rate_limit(redis: Redis, email: str, ip: str) -> int:
    """
    Returns TTL in seconds if rate limited, else 0.
    Limits to 5 attempts per 15 minutes per (email, IP) pair.
    """
    key = f"gmee:auth:ratelimit:login:{email}:{ip}"
    current = await redis.get(key)
    if current and int(current) >= 5:
        return await redis.ttl(key)
    
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 900) # 15 minutes
    await pipe.execute()
    return 0
