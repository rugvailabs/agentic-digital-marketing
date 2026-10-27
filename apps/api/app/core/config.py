"""Settings. .env.example is the source of truth; everything is overridable."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The repo-root .env, bind-mounted here in dev (see docker-compose.yml).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Loaded before Settings is constructed, and with override=True on purpose.
#
# Compose passes every variable explicitly — `GROQ_API_KEY: ${GROQ_API_KEY:-}`
# and so on — and those are baked into the container when it is created. A
# value read from the file at import time would therefore lose to an empty
# string that compose set hours ago, and saving a key would appear to do
# nothing until the stack was recreated. Overriding makes the file the
# authority, which is what "save a key and the process picks it up" requires.
#
# Dev convenience, and it degrades to nothing: with no file mounted this is a
# no-op and the container environment stands on its own, which is what
# happens in prod.
load_dotenv(ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore", case_sensitive=False)

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

    #: Ask Google Trends for explicit rising related queries per topic.
    #:
    #: Off by default and that is measured, not cautious. Probed 2026-10-27
    #: from this machine: the endpoint raised TrendsQuotaExceededError, and
    #: with the referer trendspy recommends it returned empty frames instead
    #: of raising. `trending_now` already hands back eight rising queries per
    #: topic for free, so paying five sequential requests for nothing is the
    #: worse default. Turn it on where the IP is not rate-limited.
    trends_rising_queries: bool = False

    # Trend source credentials. Blank => adapter reports not configured.
    youtube_api_key: str = ""

    # ── X ─────────────────────────────────────────────────────────────────
    #: App-only bearer. A real one is ~112 characters and begins "AAAA"; the
    #: 25-character value X calls the "API Key" is the consumer key and will
    #: return 401 here, which is worth knowing before blaming the account.
    x_bearer_token: str = ""
    #: The consumer pair, used to mint a bearer when only these are issued.
    x_consumer_key: str = ""
    x_consumer_secret: str = ""
    #: X bills per request, so a region is pulled at most this often however
    #: many times the beat runs.
    x_pull_interval_minutes: int = 120
    #: Hard ceiling on requests per day, counted in Redis so the api can
    #: report it and the worker cannot exceed it. Spends stop, never queue.
    x_daily_cap: int = 200

    # ── Reddit ────────────────────────────────────────────────────────────
    #: Script-type app: id and secret authenticate, and Reddit requires a
    #: descriptive user agent or it answers 429 regardless of the keys.
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "trendforge/0.1 (by /u/trendforge)"

    # ── Instagram (not yet issued) ────────────────────────────────────────
    #: Hashtag search needs a Business account id and a long-lived token.
    #: Blank => InstagramHashtagAdapter reports not configured and is skipped.
    ig_access_token: str = ""
    ig_business_id: str = ""

    #: Stock imagery, for later use as post backgrounds.
    pixabay_api_key: str = ""

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

    # ── Groq (spillover) ──────────────────────────────────────────────────
    #: Used only when every Gemini model has spent its daily budget. Blank =>
    #: no spillover, and the studio simply stops until the budget resets.
    groq_api_key: str = ""
    #: `llama-3.3-70b-versatile` is the obvious choice and is not served to
    #: every key — this one does not have it. Probed on 2026-10-27: of what
    #: is available, gpt-oss-120b returns clean structured JSON and
    #: gpt-oss-20b fails json_object validation outright.
    groq_model: str = "openai/gpt-oss-120b"
    groq_rpm: int = 30
    #: Tokens per minute, which is the limit that actually bites. Measured on
    #: this key 2026-10-27: a single curate_v3 call is 2,448 prompt + 3,072
    #: output = 5,520 tokens, so at the free tier's 8,000 TPM the second call
    #: in a minute is refused. Without pacing, spillover works for one call
    #: and then 429s, which is the same as not working.
    groq_tpm: int = 8000
    #: Reserved for the answer before it exists, since the limit counts both
    #: halves and the response cannot be measured in advance.
    #:
    #: 5,200 because that is what the answers actually cost, not what the
    #: visible JSON suggests. gpt-oss-120b is a reasoning model: a five-
    #: cluster curate_v3 batch measured 2,441 prompt + 5,000 output = 7,441
    #: total, almost the whole minute, with most of the output spent
    #: thinking rather than on the array. Reserving 3,200 let a second call
    #: start inside the same window and take the 429 this exists to avoid.
    #:
    #: The consequence is worth stating plainly: at 8,000 TPM this is roughly
    #: one batch a minute, so spillover is usable for a single post and slow
    #: for bulk curation. The fix is quota, not pacing.
    #:
    #: And there is a second ceiling underneath that one. The free tier also
    #: caps tokens per *day* at 200,000, which at ~7,400 a batch is about 27
    #: batches — one full curate of three regions and nothing else. Reached
    #: on 2026-10-28, after which both providers were out and the boards
    #: could only be ingested, not described. Nothing in this file can pace
    #: around a daily ceiling; it is reported so the next person recognises
    #: "tokens per day (TPD)" in a 429 for what it is.
    groq_output_reserve: int = 5200
    #: Sent as max_completion_tokens. Without it Groq applies its own default
    #: — about 3,072 for this model — and a batch that needs more comes back
    #: truncated mid-array, which surfaces as "Failed to validate JSON" and
    #: reads like a prompt problem rather than a length one. Kept under the
    #: TPM ceiling so prompt plus answer still fit one minute's allowance.
    groq_max_output_tokens: int = 5000
    groq_timeout_seconds: float = 90.0

    # ── OpenRouter (second spillover) ─────────────────────────────────────
    #: Last in the chain: gemini -> groq -> openrouter. One more free tier
    #: with its own daily ceiling, which is the point — the two before it
    #: can both be spent while this one still answers.
    openrouter_api_key: str = ""
    #: Model ids are config for the same reason Gemini's are: a free-tier id
    #: is withdrawn or renamed without warning, and the chain should survive
    #: it without a deploy. Probed before being set — see .env.example.
    #: nemotron leads on the evidence of the real workload rather than the
    #: probe. xing4.0 won a 200-token probe and then returned an empty body
    #: on every 2,300-token curate prompt it was given — the probe was not
    #: representative, so it is last now.
    openrouter_model: str = "nvidia/nemotron-3.5-super-vl:free"
    openrouter_model_fallbacks: str = ",".join(
        ("recursive/flint-v1.0:free", "xingchen-agi/xing4.0-29b-a4b:free")
    )
    openrouter_rpm: int = 20
    openrouter_timeout_seconds: float = 90.0
    #: OpenRouter asks for these on every request and shows them on the
    #: model's activity page. Not credentials; identification.
    openrouter_referer: str = "https://github.com/rugvailabs/agentic-digital-marketing"
    openrouter_title: str = "TrendForge"

    # ── Curation ──────────────────────────────────────────────────────────
    #: Measured on real gemini-embedding-001 vectors: genuine cross-source
    #: matches land at 0.686-0.693 and unrelated same-genre titles at <=0.67,
    #: so the useful band is narrow. See the step 2 notes in DESIGN_NOTES.
    cluster_similarity: float = 0.68
    #: Clusters described per call. Was 10 for curate_v2; v3 adds
    #: platform_hashtags, why_trending and relevance_to_region to every
    #: cluster, and at 10 the answer overran Groq's output cap and came back
    #: as truncated JSON. Five fits with room to spare on both providers, at
    #: the cost of more calls — which the TPM bucket now paces.
    curate_batch_size: int = 5
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
    #: Measured at roughly 11s of render per second of video on an 8-core
    #: laptop, so a 12s reel is about two minutes and the 45s ceiling is
    #: nearer nine. Generous rather than tight: a timeout here throws away a
    #: render that was going to succeed.
    renderer_timeout_seconds: float = 900.0
    #: Microsoft Neural voices via edge-tts. No key, but it is an unofficial
    #: endpoint, so it is allowed to be switched off.
    tts_enabled: bool = True
    tts_timeout_seconds: float = 60.0
    #: Royalty-free beds dropped into app/assets/music. Empty directory =>
    #: no bed, and the reel ships with voiceover only.
    music_enabled: bool = True
    #: Bed level under the voice, in dB.
    #:
    #: Measured, not guessed. Royalty-free beds arrive mastered around -14 to
    #: -18 dBFS mean, and the narration sits near -23 dBFS, so -18 dB on top
    #: put the bed at -41 dBFS — eighteen below the voice, which is not a
    #: quiet bed but an inaudible one. At -12 it lands about ten below: heard,
    #: and never in the way.
    music_gain_db: float = -12.0
    #: Seconds of fade in and out on the bed.
    music_fade_seconds: float = 1.5
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def openrouter_model_chain(self) -> list[str]:
        """Primary model first, then each configured fallback."""
        chain = [self.openrouter_model] if self.openrouter_model else []
        chain += [m.strip() for m in self.openrouter_model_fallbacks.split(",") if m.strip()]
        return list(dict.fromkeys(chain))

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
