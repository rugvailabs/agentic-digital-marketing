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

    # ── Object storage (MinIO locally, Cloudflare R2 in prod) ─────────────
    s3_endpoint_url: str = "http://minio:9000"
    #: Browser-reachable base; the container endpoint is not resolvable there.
    s3_public_url: str = "http://localhost:9020"
    s3_access_key_id: str = "trendforge"
    s3_secret_access_key: str = "trendforge-secret"
    s3_bucket: str = "trendforge-assets"
    s3_region: str = "auto"
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
    #: Tried in order when the primary returns 503/429. Long on purpose: this
    #: tier throws 503 "high demand" routinely, and the daily request budget is
    #: per model id, so each entry carries its own allowance.
    gemini_model_fallbacks: str = ",".join(
        (
            "gemini-flash-latest",
            "gemini-3-flash-preview",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
        )
    )
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_embed_dim: int = 768
    #: Blank => GeminiImageProvider is not configured and Pillow renders all.
    gemini_image_model: str = ""
    #: Free-tier budgets, enforced locally so we rarely see a 429 at all.
    gemini_rpm: int = 10
    #: Per model, not per project: the free tier allows 20 generate_content
    #: requests per day for each model id, which is why the chain is long.
    gemini_rpd: int = 20
    gemini_embed_rpm: int = 100
    gemini_timeout_seconds: float = 90.0

    # ── Curation ──────────────────────────────────────────────────────────
    #: Measured on real gemini-embedding-001 vectors: genuine cross-source
    #: matches land at 0.686-0.693 and unrelated same-genre titles at <=0.67,
    #: so the useful band is narrow. See the step 2 notes in DESIGN_NOTES.
    cluster_similarity: float = 0.68
    curate_batch_size: int = 10
    #: Cosine above which a cluster is judged to be the *same topic* as an
    #: existing row from an earlier run, so a reworded title updates it rather
    #: than forking a second row. Deliberately far above cluster_similarity:
    #: this decides identity, not grouping.
    topic_match_similarity: float = 0.9
    #: Regions curated on the beat. Everything else curates when opened.
    curate_regions: str = "IN"

    # ── Video (step 3) ────────────────────────────────────────────────────
    #: The Remotion renderer, a separate Node service: it needs its own
    #: Chromium, which has no business in the Python image. Blank => the
    #: provider reports not configured and reels are refused with a reason.
    renderer_url: str = "http://renderer:3100"
    #: A 30s reel at 1080x1920 takes well over a minute on a laptop.
    renderer_timeout_seconds: float = 300.0
    #: Microsoft Neural voices via edge-tts. No key, but it is an unofficial
    #: endpoint, so it is allowed to be switched off.
    tts_enabled: bool = True
    tts_timeout_seconds: float = 60.0
    #: Royalty-free beds dropped into app/assets/music. Empty directory =>
    #: no bed, and the reel ships with voiceover only.
    music_enabled: bool = True
    #: Bed level under the voice, in dB. -18 keeps it audible without
    #: fighting the narration on a phone speaker.
    music_gain_db: float = -18.0
    #: Seconds of fade in and out on the bed.
    music_fade_seconds: float = 1.5
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

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
