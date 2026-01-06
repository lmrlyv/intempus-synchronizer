"""Background sync jobs for synchronizing between Intempus and System B."""

import asyncio
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.config import settings
from app.core.logging import get_logger
from app.services.sync_service import SyncService

logger = get_logger(__name__)


async def initial_sync_job():
    """Initial sync job that runs once on startup.

    Performs a full initialization sync to populate sync tables and establish
    baseline synchronization state.
    """
    logger.info("Starting initial sync job")
    sync_service = SyncService()

    try:
        await sync_service.sync(is_full_sync=True, is_initialization=True)
        logger.info("Initial sync job completed successfully")
    except Exception as e:
        logger.error(f"Initial sync job failed: {e}", exc_info=True)
    finally:
        await sync_service.close()


async def incremental_sync_job():
    """Incremental sync job that runs frequently.

    Syncs only diffs by using the last-read Logical-Timestamp value in a filter.
    Less load on the APIs and faster execution due to smaller data sets.
    """
    logger.info("Starting incremental sync job")
    sync_service = SyncService()

    try:
        await sync_service.sync(is_full_sync=False, is_initialization=False)
        logger.info("Incremental sync job completed successfully")
    except Exception as e:
        logger.error(f"Incremental sync job failed: {e}", exc_info=True)
    finally:
        await sync_service.close()


async def full_sync_job():
    """Full sync job that runs less frequently.

    Performs a complete sync to capture deletions. This is required because
    incremental sync (using logical_timestamp filter) cannot detect deleted cases.
    """
    logger.info("Starting full sync job")
    sync_service = SyncService()

    try:
        await sync_service.sync(is_full_sync=True, is_initialization=False)
        logger.info("Full sync job completed successfully")
    except Exception as e:
        logger.error(f"Full sync job failed: {e}", exc_info=True)
    finally:
        await sync_service.close()


def run_incremental_sync_job():
    """Wrapper to run incremental sync job in async context.

    APScheduler runs jobs in separate threads, so asyncio.run() will
    create a new event loop for each execution.
    """
    asyncio.run(incremental_sync_job())


def run_full_sync_job():
    """Wrapper to run full sync job in async context.

    APScheduler runs jobs in separate threads, so asyncio.run() will
    create a new event loop for each execution.
    """
    asyncio.run(full_sync_job())


def schedule_recurring_sync_jobs(scheduler: BackgroundScheduler):
    """Schedule recurring sync jobs (incremental and full sync).

    This should be called after the initial sync completes to ensure
    recurring jobs only start after initialization is done.

    Args:
        scheduler: The APScheduler instance to add jobs to.
    """
    scheduler.add_job(
        run_incremental_sync_job,
        trigger=IntervalTrigger(seconds=settings.INCREMENTAL_SYNC_INTERVAL_SECONDS),
        id="incremental_sync",
        name="Incremental Sync Job",
        replace_existing=True,
    )

    scheduler.add_job(
        run_full_sync_job,
        trigger=IntervalTrigger(seconds=settings.FULL_SYNC_INTERVAL_SECONDS),
        id="full_sync",
        name="Full Sync Job",
        replace_existing=True,
    )


async def run_initial_sync_and_schedule_jobs(scheduler: BackgroundScheduler):
    """Run initial sync and schedule recurring jobs after it completes.

    This runs as a background task and waits for FastAPI to be ready
    by checking if System B API (this FastAPI app) is accessible.

    Args:
        scheduler: The APScheduler instance to schedule recurring jobs on.
    """
    # Wait for FastAPI to be ready by checking System B API
    max_retries = 10
    retry_delay = 3.0  # 1 second between retries

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                # Try to reach System B API case endpoint to verify it's ready
                response = await client.get(
                    f"{settings.SYSTEM_B_API_BASE_URL}{settings.API_PREFIX}/case/",
                    timeout=2.0,
                )
                if response.status_code < 500:  # Any non-server-error means it's ready
                    logger.info("FastAPI is ready, starting initial sync...")
                    break
        except Exception:
            if attempt < max_retries - 1:
                logger.debug(
                    f"Waiting for FastAPI to be ready (attempt {attempt + 1}/{max_retries})..."
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.warning(
                    "FastAPI readiness check failed, proceeding with initial sync anyway..."
                )

    try:
        await initial_sync_job()
        logger.info("Initial sync completed successfully")
    except Exception as e:
        logger.error(f"Initial sync failed: {e}", exc_info=True)
        logger.warning("Scheduling recurring sync jobs despite initial sync failure")

    # Schedule recurring jobs only after initial sync completes
    schedule_recurring_sync_jobs(scheduler)
    logger.info(
        f"Recurring jobs scheduled - Incremental sync every {settings.INCREMENTAL_SYNC_INTERVAL_SECONDS}s, "
        f"Full sync every {settings.FULL_SYNC_INTERVAL_SECONDS}s"
    )
