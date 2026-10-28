"""GET /dashboard — everything the home page shows, in one request.

One endpoint rather than six, because the dashboard is a single view of a
single moment: six requests would paint it in six steps and let the map
disagree with the movers beside it.

Every number here is measured. There is nothing on this page that is not
read out of the database or off a live budget counter, which is worth
stating because a dashboard is where invented figures normally live.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.brands import workspace_id
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.llm import get_llm
from app.models import (
    AssetKind,
    ContentJob,
    EditorialStatus,
    JobKind,
    Region,
    RegionKind,
    SafetyFlag,
    Trend,
)
from app.sources import configured_source_names

router = APIRouter(tags=["dashboard"])
log = get_logger("api.dashboard")

#: The dead band either side of flat, matching the ladder's own reading of
#: a velocity series. Without it every board flickers between rising and
#: cooling on rank noise, and the map would repaint itself hourly.
RISING_BAND = 0.1

MOVERS = 5
SCHEDULED = 5
RECENT_WORK = 8


class StateHeat(BaseModel):
    """One state's square on the map."""

    region_code: str
    region_name: str
    topics: int
    rising: int
    #: rising / topics, 0..1. The map colours on this rather than on the
    #: count: a board with 50 topics is not hotter than one with 20 for
    #: having more of them.
    share: float


class Mover(BaseModel):
    trend_id: int
    topic: str
    region_code: str
    region_name: str
    rank: int
    volume: int
    velocity: list[float]
    #: How much the last point is above the mean of the ones before it, as
    #: a fraction. 0.4 is "forty percent above where it had been sitting".
    delta: float


class WorkItem(BaseModel):
    job_id: int
    kind: JobKind
    title: str
    brand_name: str
    region_code: str
    created_at: datetime
    preview_url: str | None


class WeekOfWork(BaseModel):
    posts: int
    reels: int
    #: The most recent few, for the posters. Not all of them — this is a
    #: dashboard, and the library is where the rest live.
    items: list[WorkItem]


class ProviderBar(BaseModel):
    name: str
    configured: bool
    used_today: int | None
    remaining_today: int | None
    #: used + remaining, so a bar has a denominator without the client
    #: inventing one. None where the provider does not meter calls.
    limit: int | None
    #: Held back for Desk actions, so scheduled work cannot spend the lot.
    reserved_for_desk: int | None
    #: Where the provider bills money rather than counting calls.
    remaining_usd: float | None


class ScheduledItem(BaseModel):
    job_id: int
    kind: JobKind
    title: str
    brand_name: str
    region_code: str
    scheduled_at: datetime
    preview_url: str | None


class Pipeline(BaseModel):
    database: bool
    regions: int
    trends: int
    sources_configured: list[str]
    #: When the board was last written to, which is the only honest answer
    #: to "is the ingest running".
    last_ingest_at: datetime | None
    #: Jobs that failed in the last day. A dashboard that does not show
    #: these is a dashboard that hides the only thing needing attention.
    failed_today: int


class Dashboard(BaseModel):
    now_ist: str
    heat: list[StateHeat]
    movers: list[Mover]
    week: WeekOfWork
    budget: list[ProviderBar]
    scheduled: list[ScheduledItem]
    pipeline: Pipeline


def velocity_delta(series: Sequence[float]) -> float | None:
    """How far the last point sits above the mean of the ones before it.

    The same derivation the ladder's sparkline uses, so a topic the board
    draws in chilli is a topic this page counts as rising. None when there
    is no history to compare against — a brand-new topic is not rising,
    it is new.
    """
    points = [float(v) for v in series or []]
    if len(points) < 2:
        return None
    history = [v for v in points[:-1] if v > 0]
    if not history:
        return None
    mean = sum(history) / len(history)
    if mean == 0:
        return None
    return (points[-1] - mean) / mean


@router.get("", response_model=Dashboard)
async def dashboard(
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> Dashboard:
    now = utcnow()

    return Dashboard(
        now_ist=now.isoformat(),
        heat=await _heat(session),
        movers=await _movers(session),
        week=await _week(session, ws, since=now - timedelta(days=7)),
        budget=await _budget(),
        scheduled=await _scheduled(session, ws, after=now),
        pipeline=await _pipeline(session, ws, since=now - timedelta(days=1)),
    )


async def _heat(session: AsyncSession) -> list[StateHeat]:
    """Where things are moving, per state.

    Rising share rather than topic count or search volume, both of which
    were tried. Counts are near-identical across boards because the ingest
    takes the same depth everywhere, so that map was flat. Volume is a
    population map — Uttar Pradesh is always hottest and the page tells you
    nothing you did not know before opening it.
    """
    rows = (
        await session.execute(
            select(Region, Trend)
            .join(Trend, Trend.region_id == Region.id)
            .where(
                Region.kind.in_([RegionKind.state, RegionKind.union_territory]),
                Trend.rank > 0,
                Trend.safety_flag.is_distinct_from(SafetyFlag.skip.value),
            )
        )
    ).all()

    seen: dict[str, dict] = {}
    for region, trend in rows:
        bucket = seen.setdefault(region.code, {"name": region.name, "topics": 0, "rising": 0})
        bucket["topics"] += 1
        delta = velocity_delta(trend.velocity)
        if delta is not None and delta > RISING_BAND:
            bucket["rising"] += 1

    return sorted(
        (
            StateHeat(
                region_code=code,
                region_name=bucket["name"],
                topics=bucket["topics"],
                rising=bucket["rising"],
                share=round(bucket["rising"] / bucket["topics"], 4) if bucket["topics"] else 0.0,
            )
            for code, bucket in seen.items()
        ),
        key=lambda s: s.region_code,
    )


async def _movers(session: AsyncSession) -> list[Mover]:
    """The five topics climbing hardest right now, anywhere.

    Ranked by delta rather than by rank: a topic that is twelfth and
    accelerating is the news, and a topic that has been first all day is
    not. Computed in Python because the derivation has to match the
    ladder's exactly, and a second implementation in SQL is a second thing
    to keep in step.
    """
    rows = (
        await session.scalars(
            select(Trend)
            .options(selectinload(Trend.region))
            .where(
                Trend.rank > 0,
                Trend.safety_flag.is_distinct_from(SafetyFlag.skip.value),
                # A mover with no audience is a rounding error on a small
                # board, not a story.
                Trend.volume > 0,
            )
            .order_by(Trend.rank)
            # Bounded: the delta cannot be computed in SQL, so this reads
            # the top of every board rather than every row in the table.
            .limit(600)
        )
    ).all()

    scored: list[tuple[float, Trend]] = []
    seen_topics: set[str] = set()
    for trend in rows:
        delta = velocity_delta(trend.velocity)
        if delta is None or delta <= RISING_BAND:
            continue
        # One row per story, or a national surge fills all five slots with
        # the same headline from five boards.
        if trend.topic_key in seen_topics:
            continue
        seen_topics.add(trend.topic_key)
        scored.append((delta, trend))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        Mover(
            trend_id=trend.id,
            topic=trend.topic,
            region_code=trend.region.code if trend.region else "",
            region_name=trend.region.name if trend.region else "",
            rank=trend.rank,
            volume=trend.volume,
            velocity=[float(v) for v in trend.velocity or []],
            delta=round(delta, 4),
        )
        for delta, trend in scored[:MOVERS]
    ]


def _preview_of(job: ContentJob) -> str | None:
    """A still, never an mp4 — a <video> draws nothing until it has fetched
    a frame, and the renderer saves a poster beside every reel."""
    for asset in job.assets:
        if asset.kind is AssetKind.image and asset.url:
            return asset.url
    for asset in job.assets:
        if asset.kind is AssetKind.video:
            poster = (asset.meta_json or {}).get("poster_url")
            if isinstance(poster, str) and poster:
                return poster
    return None


def _title_of(job: ContentJob, fallback: str) -> str:
    caption = next((a for a in job.assets if a.kind is AssetKind.caption), None)
    hook = (caption.meta_json or {}).get("hook") if caption else None
    return hook if isinstance(hook, str) and hook else fallback


async def _topics_for(session: AsyncSession, jobs: Sequence[ContentJob]) -> dict[int, Trend]:
    if not jobs:
        return {}
    rows = await session.scalars(
        select(Trend)
        .options(selectinload(Trend.region))
        .where(Trend.id.in_([job.trend_id for job in jobs]))
    )
    return {trend.id: trend for trend in rows.all()}


async def _week(session: AsyncSession, ws: int, *, since: datetime) -> WeekOfWork:
    counts = (
        await session.execute(
            select(ContentJob.kind, func.count(ContentJob.id))
            .where(ContentJob.workspace_id == ws, ContentJob.created_at >= since)
            .group_by(ContentJob.kind)
        )
    ).all()
    by_kind = dict(counts)

    jobs = (
        await session.scalars(
            select(ContentJob)
            .options(selectinload(ContentJob.brand), selectinload(ContentJob.assets))
            .where(ContentJob.workspace_id == ws, ContentJob.created_at >= since)
            .order_by(ContentJob.created_at.desc(), ContentJob.id.desc())
            .limit(RECENT_WORK)
        )
    ).all()
    topics = await _topics_for(session, jobs)

    return WeekOfWork(
        posts=by_kind.get(JobKind.post, 0),
        reels=by_kind.get(JobKind.reel, 0),
        items=[
            WorkItem(
                job_id=job.id,
                kind=job.kind,
                title=_title_of(job, _topic_text(topics.get(job.trend_id))),
                brand_name=job.brand.name,
                region_code=_region_code(topics.get(job.trend_id)),
                created_at=job.created_at,
                preview_url=_preview_of(job),
            )
            for job in jobs
        ],
    )


async def _scheduled(session: AsyncSession, ws: int, *, after: datetime) -> list[ScheduledItem]:
    jobs = (
        await session.scalars(
            select(ContentJob)
            .options(selectinload(ContentJob.brand), selectinload(ContentJob.assets))
            .where(
                ContentJob.workspace_id == ws,
                ContentJob.editorial_status == EditorialStatus.scheduled,
                ContentJob.scheduled_at.is_not(None),
                # What is next, not what was missed. A calendar shows the
                # past; a dashboard is about what happens now.
                ContentJob.scheduled_at >= after,
            )
            .order_by(ContentJob.scheduled_at.asc())
            .limit(SCHEDULED)
        )
    ).all()
    topics = await _topics_for(session, jobs)

    return [
        ScheduledItem(
            job_id=job.id,
            kind=job.kind,
            title=_title_of(job, _topic_text(topics.get(job.trend_id))),
            brand_name=job.brand.name,
            region_code=_region_code(topics.get(job.trend_id)),
            # Narrowed by the query's is_not(None), which mypy cannot see.
            scheduled_at=job.scheduled_at or utcnow(),
            preview_url=_preview_of(job),
        )
        for job in jobs
    ]


async def _budget() -> list[ProviderBar]:
    """What each provider has left today.

    Read off the same shared counters the workers spend against, so this
    is the live figure rather than a copy — the point of a bar here is to
    answer "can I generate ten posts right now" before clicking.
    """
    try:
        statuses = await get_llm().statuses()
    except Exception as exc:  # pragma: no cover - a budget read must not fail the page
        log.warning("budget unreadable", error=f"{type(exc).__name__}: {exc}"[:200])
        return []

    bars: list[ProviderBar] = []
    for status in statuses:
        used = status.used_today
        remaining = status.remaining_today
        bars.append(
            ProviderBar(
                name=status.name,
                configured=status.configured,
                used_today=used,
                remaining_today=remaining,
                limit=(used + remaining) if used is not None and remaining is not None else None,
                reserved_for_desk=getattr(status, "reserved_for_desk", None),
                remaining_usd=status.remaining_usd,
            )
        )
    return bars


async def _pipeline(session: AsyncSession, ws: int, *, since: datetime) -> Pipeline:
    database = True
    regions = trends = 0
    last_ingest: datetime | None = None
    failed = 0
    try:
        regions = (await session.scalar(select(func.count()).select_from(Region))) or 0
        trends = (
            await session.scalar(select(func.count()).select_from(Trend).where(Trend.rank > 0))
        ) or 0
        last_ingest = await session.scalar(select(func.max(Trend.last_seen_at)))
        failed = (
            await session.scalar(
                select(func.count())
                .select_from(ContentJob)
                .where(
                    ContentJob.workspace_id == ws,
                    ContentJob.status == "failed",
                    ContentJob.created_at >= since,
                )
            )
        ) or 0
    except Exception:
        # The dashboard reports a degraded pipeline; it does not become one.
        database = False

    return Pipeline(
        database=database,
        regions=regions,
        trends=trends,
        sources_configured=configured_source_names(),
        last_ingest_at=last_ingest,
        failed_today=failed,
    )


def _topic_text(trend: Trend | None) -> str:
    return trend.topic if trend else "Topic no longer on the board"


def _region_code(trend: Trend | None) -> str:
    return trend.region.code if trend and trend.region else ""
