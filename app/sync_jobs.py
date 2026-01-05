"""Background sync jobs for synchronizing between Intempus and System B."""

import asyncio
from app.core.logging import get_logger

logger = get_logger(__name__)


async def incremental_sync_job():
    """Incremental sync job that runs frequently.

    Syncs only diffs by using the last-read Logical-Timestamp value in a filter.
    Less load on the APIs and faster execution due to smaller data sets.
    """
    pass


async def full_sync_job():
    """Full sync job that runs less frequently.

    Performs a complete sync to capture deletions. This is required because
    incremental sync (using logical_timestamp filter) cannot detect deleted cases.
    """
    pass


def run_incremental_sync_job():
    """Wrapper to run incremental sync job in async context."""
    asyncio.run(incremental_sync_job())


def run_full_sync_job():
    """Wrapper to run full sync job in async context."""
    asyncio.run(full_sync_job())
