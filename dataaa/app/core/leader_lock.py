"""Redis-backed leader election for scheduled jobs.

When multiple backend replicas run, each has its own APScheduler. Without
coordination every replica fires the same collection/NLP cycle, double-
fetching sources and racing on the same rows.

This lock makes only ONE replica per interval execute a job:
  - SET key value NX EX ttl  ->  won by exactly one caller
  - losers skip silently and retry next tick
  - stale locks expire (ttl = 75% of interval) so a crashed leader
    can't wedge the pipeline

The lock is best-effort: if Redis is down every replica runs (same as
today's behaviour) rather than none.
"""

import logging
import uuid
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class LeaderLock:
    def __init__(self, redis_wrapper: Any, namespace: str = "gmee") -> None:
        # ``redis_wrapper`` is the app's redis_client wrapper (has get_client())
        self._wrapper = redis_wrapper
        self.namespace = namespace
        self.instance_id = uuid.uuid4().hex[:12]

    async def _client(self) -> Redis:
        client: Redis = await self._wrapper.get_client()
        return client

    async def try_acquire(self, job: str, ttl_seconds: int) -> bool:
        """Attempt to become the leader for ``job``. True when acquired."""
        key = f"{self.namespace}:lock:{job}"
        try:
            client = await self._client()
            acquired = await client.set(key, self.instance_id, nx=True, ex=ttl_seconds)
            return bool(acquired)
        except Exception as exc:
            logger.warning("leader lock unavailable (%s) — proceeding uncoordinated", exc)
            return True

    async def release(self, job: str) -> None:
        """Release only if we still own it (avoid freeing a newer leader)."""
        key = f"{self.namespace}:lock:{job}"
        try:
            client = await self._client()
            current = await client.get(key)
            token = current.decode() if isinstance(current, bytes) else current
            if current and token == self.instance_id:
                await client.delete(key)
        except Exception as exc:
            logger.debug("leader lock release skipped: %s", exc)
