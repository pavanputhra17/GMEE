import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.postgres import async_session_maker
from app.services.collection_orchestrator import orchestrator

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# We need to store the latest run summary for the /status endpoint since we aren't using a DB table
latest_collection_summary = []
last_run_time = None

async def scheduled_collection_job():
    global latest_collection_summary
    global last_run_time
    
    logger.info("Scheduler triggered collection job")
    try:
        async with async_session_maker() as db:
            summaries = await orchestrator.run_collection_cycle(db)
            latest_collection_summary = summaries
            last_run_time = datetime.now()
    except Exception as e:
        logger.exception(f"Scheduled collection job failed entirely: {e}")


def start_scheduler():
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


def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info("Stopped collection scheduler")
