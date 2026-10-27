"""Liveness/readiness. Used by the compose healthcheck and the top-bar dot."""

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time import to_ist, utcnow
from app.db.session import get_session
from app.llm import get_llm
from app.models import Region, Trend
from app.sources import configured_source_names
from app.sources.x import XAdapter
from app.video.remotion import RemotionVideoProvider

router = APIRouter(tags=["health"])


class ProviderHealth(BaseModel):
    """One LLM provider's wiring and remaining day."""

    name: str
    configured: bool
    #: Calls left today, or null where the provider does not meter a day.
    #: Null is not zero: one means "not counted here", the other "spent".
    remaining_today: int | None = None
    #: Per model id. Gemini's free tier counts a day per model, so one
    #: exhausted entry here is routine and not an exhausted provider.
    per_model: dict[str, int] = Field(default_factory=dict)
    #: Money left, for a vendor that meters money rather than calls.
    #: OpenRouter is the only one today. Null means either "not metered in
    #: dollars" or "could not be read" — both of which are different from 0.
    remaining_usd: float | None = None


class XRequests(BaseModel):
    """Today's spend on the one source that is billed per request."""

    used: int = Field(examples=[24])
    cap: int = Field(examples=[200])
    #: False when X_BEARER_TOKEN is unset, in which case `used` is always 0
    #: and means "nothing was asked for", not "nothing was spent".
    configured: bool


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    now_ist: str
    database: bool
    regions: int
    trends: int
    # Sources with credentials; the rest are skipped, never fatal.
    sources_configured: list[str]
    #: Whether the Remotion service is answering. False means reels are off,
    #: which the studio says before a user queues one and waits.
    renderer: bool
    #: Every LLM provider in the chain, primary first. The counts come from
    #: the shared Redis budget rather than this process's own, because this
    #: process never calls a model — the worker does.
    llm_providers: list[ProviderHealth]
    #: X requests spent today against X_DAILY_CAP. X is the one source billed
    #: per request, and a region that rolls up several cities spends one per
    #: WOEID, so the figure that matters is requests rather than regions.
    x_requests: XRequests


@router.get("/health", response_model=Health)
async def health(session: AsyncSession = Depends(get_session)) -> Health:
    database = True
    regions = trends = 0
    try:
        await session.execute(text("SELECT 1"))
        regions = (await session.scalar(select(func.count()).select_from(Region))) or 0
        trends = (await session.scalar(select(func.count()).select_from(Trend))) or 0
    except Exception:
        # Health must report degraded, never raise: the top-bar dot depends on
        # this endpoint answering even when Postgres is down.
        database = False

    renderer = bool((await RemotionVideoProvider().health()).get("ok"))

    providers = [ProviderHealth(**asdict(s)) for s in await get_llm().statuses()]
    x = XAdapter()
    x_requests = XRequests(
        used=await x.requests_used_today(),
        cap=settings.x_daily_cap,
        configured=x.is_configured(),
    )
    writing = any(p.configured for p in providers)

    return Health(
        # The renderer is not load-bearing for the board, so it degrades the
        # status rather than failing it: reels are off, everything else works.
        # No configured provider degrades it for the same reason: the board
        # still ranks topics, and nothing can be written about them.
        status="ok" if database and renderer and writing else "degraded",
        env=settings.env,
        now_ist=to_ist(utcnow()).isoformat(),
        database=database,
        regions=regions,
        trends=trends,
        sources_configured=configured_source_names(),
        renderer=renderer,
        llm_providers=providers,
        x_requests=x_requests,
    )
