"""Settings. .env.example is the source of truth; everything is overridable."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    env: str = "dev"
    log_level: str = "INFO"
    tz: str = "Asia/Kolkata"

    database_url: str = "postgresql+asyncpg://trendforge:trendforge@postgres:5432/trendforge"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Kept as a raw string: pydantic-settings JSON-decodes list-typed fields
    # straight from the env var, before any validator can split on commas.
    cors_origins: str = "http://localhost:3020"

    ingest_interval_minutes: int = 30
    ingest_max_concurrency: int = 4

    # Trend source credentials. Blank => adapter reports not configured.
    youtube_api_key: str = ""
    x_bearer_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
