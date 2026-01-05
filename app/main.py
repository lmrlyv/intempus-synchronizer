from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api import router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.db import init_db


# Initialize logging before creating logger
setup_logging()
logger = get_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)


@app.on_event("startup")
def on_startup():
    init_db()


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
