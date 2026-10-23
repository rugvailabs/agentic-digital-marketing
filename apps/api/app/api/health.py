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

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    now_ist: str
    database: bool
    regions: int
    trends: int


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

    return Health(
        status="ok" if database else "degraded",
        env=settings.env,
        now_ist=to_ist(utcnow()).isoformat(),
        database=database,
        regions=regions,
        trends=trends,
    )
