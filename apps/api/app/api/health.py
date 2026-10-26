"""Liveness/readiness. Used by the compose healthcheck and the top-bar dot."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time import to_ist, utcnow
from app.db.session import get_session
from app.models import Region, Trend
from app.sources import configured_source_names
from app.video.remotion import RemotionVideoProvider

router = APIRouter(tags=["health"])


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

    return Health(
        # The renderer is not load-bearing for the board, so it degrades the
        # status rather than failing it: reels are off, everything else works.
        status="ok" if database and renderer else "degraded",
        env=settings.env,
        now_ist=to_ist(utcnow()).isoformat(),
        database=database,
        regions=regions,
        trends=trends,
        sources_configured=configured_source_names(),
        renderer=renderer,
    )
