from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BeforeValidator, computed_field
from pydantic_settings import BaseSettings


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Intempus Synchronizer"
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    API_PREFIX: str = "/api/v1"

    CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    # Intempus API Configuration
    INTEMPUS_API_BASE_URL: str = "https://intempus.dk"
    INTEMPUS_API_KEY: str
    INTEMPUS_PAGINATION_LIMIT: int = 1000

    # System B API Configuration
    SYSTEM_B_API_BASE_URL: str = "http://localhost:8000"

    # Sync Configuration
    INCREMENTAL_SYNC_INTERVAL_SECONDS: int = 60  # Run every minute
    FULL_SYNC_INTERVAL_SECONDS: int = 3600  # Run every hour

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.CORS_ORIGINS]


settings = Settings()
