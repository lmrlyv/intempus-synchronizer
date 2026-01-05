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

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.CORS_ORIGINS]


settings = Settings()
