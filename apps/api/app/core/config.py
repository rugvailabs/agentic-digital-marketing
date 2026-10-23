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

    # ── Gemini ────────────────────────────────────────────────────────────
    # Model ids are config, not constants: this key's tier serves
    # gemini-3.5-flash and gemini-embedding-001, while text-embedding-004 and
    # the 2.5 family are 404s. See .env.example for the probe results.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    #: Tried in order when the primary returns 503/429. This tier throws 503
    #: "high demand" often enough that a single model id is not dependable.
    gemini_model_fallbacks: str = "gemini-flash-latest,gemini-3.6-flash,gemini-3-flash-preview"
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_embed_dim: int = 768
    #: Blank => GeminiImageProvider is not configured and Pillow renders all.
    gemini_image_model: str = ""
    #: Free-tier budgets, enforced locally so we rarely see a 429 at all.
    gemini_rpm: int = 10
    gemini_rpd: int = 250
    gemini_embed_rpm: int = 100
    gemini_timeout_seconds: float = 90.0

    # ── Curation ──────────────────────────────────────────────────────────
    #: Measured on real gemini-embedding-001 vectors: genuine cross-source
    #: matches land at 0.686-0.693 and unrelated same-genre titles at <=0.67,
    #: so the useful band is narrow. See the step 2 notes in DESIGN_NOTES.
    cluster_similarity: float = 0.68
    curate_batch_size: int = 10
    #: Regions curated on the beat. Everything else curates when opened.
    curate_regions: str = "IN"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def gemini_model_chain(self) -> list[str]:
        """Primary model first, then each configured fallback."""
        chain = [self.gemini_model]
        chain += [m.strip() for m in self.gemini_model_fallbacks.split(",") if m.strip()]
        return list(dict.fromkeys(chain))

    @property
    def curate_region_list(self) -> list[str]:
        return [c.strip() for c in self.curate_regions.split(",") if c.strip()]

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
