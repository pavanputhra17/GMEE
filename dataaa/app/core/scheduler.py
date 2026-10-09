import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.core.leader_lock import LeaderLock
from app.db.postgres import async_session_maker
from app.db.redis_client import redis_client
from app.services.collection_orchestrator import (
    SourceCollectionSummary,
    orchestrator,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# We need to store the latest run summary for the /status endpoint since we aren't using a DB table
latest_collection_summary: list[SourceCollectionSummary] = []
last_run_time: datetime | None = None

_leader: LeaderLock | None = None


def _get_leader() -> LeaderLock:
    global _leader
    if _leader is None:
        _leader = LeaderLock(redis_client)
    return _leader


async def scheduled_collection_job() -> None:
    global latest_collection_summary
    global last_run_time

    settings = get_settings()
    ttl = max(60, int(settings.COLLECTION_INTERVAL_MINUTES * 60 * 0.75))
    leader = _get_leader()
    if not await leader.try_acquire("collection", ttl):
        logger.debug("Another replica leads this collection cycle — skipping")
        return

    logger.info("Scheduler triggered collection job (leader)")
    try:
        async with async_session_maker() as db:
            summaries = await orchestrator.run_collection_cycle(db)
            latest_collection_summary = summaries
            last_run_time = datetime.now(UTC)
    except Exception:
        logger.exception("Scheduled collection job failed entirely")
    finally:
        await leader.release("collection")


def start_scheduler() -> None:
    settings = get_settings()
    interval_minutes = settings.COLLECTION_INTERVAL_MINUTES

    scheduler.add_job(
        scheduled_collection_job,
        'interval',
        minutes=interval_minutes,
        id='periodic_collection',
        max_instances=1,
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"Started collection scheduler (interval: {interval_minutes} minutes)")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Stopped collection scheduler")
