"""In-process scheduler for the collection pipeline.

Each tick:
  1. Elect a leader through Redis (fail closed; lease renewed while running).
  2. Open a durable ``pipeline_jobs`` row (single-flight per job type in
     Postgres, survives restarts — replaces the old worker-local globals).
  3. Run collection -> preprocessing -> NLP -> evolution.

Redis election only avoids wasted duplicate work; correctness against two
workers touching the same article comes from row-level claims in Postgres.
"""

import logging
from dataclasses import asdict

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.core.leader_lock import LeaderLock
from app.db.postgres import async_session_maker
from app.db.redis_client import redis_client
from app.models.pipeline import JobTypeEnum
from app.services.collection_orchestrator import orchestrator
from app.services.pipeline.jobs import JobAlreadyRunning, run_job

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_leader: LeaderLock | None = None


def _get_leader() -> LeaderLock:
    global _leader
    if _leader is None:
        _leader = LeaderLock(redis_client)
    return _leader


async def scheduled_collection_job() -> None:
    settings = get_settings()
    # Lease is renewed while the cycle runs; the TTL only bounds how long a
    # crashed leader can block the next tick.
    ttl = max(60, int(settings.COLLECTION_INTERVAL_MINUTES * 60 * 0.75))
    leader = _get_leader()
    async with leader.hold("collection", ttl) as lease:
        if not lease.acquired:
            logger.debug("Not the leader for this collection cycle — skipping")
            return
        logger.info("Scheduler triggered collection job (leader)")
        try:
            async with async_session_maker() as db:
                async with run_job(db, JobTypeEnum.collection, trigger="scheduler") as job:
                    summaries = await orchestrator.run_collection_cycle(db)
                    job.summary = {"sources": [asdict(s) for s in summaries]}
                    if lease.is_lost:
                        logger.error("Leader lease lost during collection; results were fenced")
        except JobAlreadyRunning:
            logger.warning("A collection job is already running (durable record) — skipping")
        except Exception:
            logger.exception("Scheduled collection job failed entirely")


def start_scheduler() -> None:
    settings = get_settings()
    interval_minutes = settings.COLLECTION_INTERVAL_MINUTES

    scheduler.add_job(
        scheduled_collection_job,
        'interval',
        minutes=interval_minutes,
        id='periodic_collection',
        max_instances=1,
        coalesce=True,
        replace_existing=True
    )

    scheduler.start()
    logger.info("Started collection scheduler (interval: %d minutes)", interval_minutes)


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Stopped collection scheduler")
