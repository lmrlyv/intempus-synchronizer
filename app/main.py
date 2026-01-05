from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api import router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.db import init_db
from app.sync_jobs import run_incremental_sync_job, run_full_sync_job


# Initialize logging before creating logger
setup_logging()
logger = get_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup
    init_db()

    scheduler = BackgroundScheduler()

    # Schedule sync jobs
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

    scheduler.start()
    logger.info(
        f"Scheduler started - Incremental sync every {settings.INCREMENTAL_SYNC_INTERVAL_SECONDS}s, "
        f"Full sync every {settings.FULL_SYNC_INTERVAL_SECONDS}s"
    )

    yield

    # Application shutdown
    scheduler.shutdown()
    logger.info("Scheduler shut down")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(router.api_router, prefix=settings.API_PREFIX)
