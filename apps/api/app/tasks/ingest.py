"""The ingest cycle: fetch -> snapshot -> merge -> upsert.

Idempotency: every snapshot row is unique on (region, source, run_id) and
inserted with ON CONFLICT DO NOTHING, so a Celery redelivery re-runs the cycle
without duplicating history. The trends upsert is keyed on
(region, topic_key), so re-running only moves scores.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.llm.priority import background
from app.models import (
    PipelineStatus,
    Region,
    SnapshotStatus,
    Trend,
    TrendSnapshot,
)
from app.sources import all_sources
from app.sources.base import RawTrendItem, TrendSource
from app.tasks.merge import SourceItems, merge, next_velocity
from app.tasks.platforms import sync_platforms

log = get_logger("ingest")

#: Items to request per source per region. Enough for a long board, small
#: enough that one cycle over 53 regions stays polite to free endpoints.
FETCH_LIMIT = 25
#: Rows kept per region. The ladder is scannable, not exhaustive.
BOARD_LIMIT = 40


async def fetch_one(
    source: TrendSource, region: Region, run_id: str, captured_at: datetime
) -> dict[str, Any]:
    """Run one adapter against one region, never raising.

    Returns the row to insert into trend_snapshots. An unconfigured or
    unsupported source is recorded as `skipped` rather than silently omitted,
    so the board can explain a thin region.
    """
    started = utcnow()

    def row(status: SnapshotStatus, items: list[RawTrendItem], error: str | None = None) -> dict:
        return {
            "region_id": region.id,
            "source": source.name,
            "run_id": run_id,
            "captured_at": captured_at,
            "status": status,
            "error": error,
            "duration_ms": int((utcnow() - started).total_seconds() * 1000),
            "item_count": len(items),
            "items": [i.as_dict() for i in items],
        }

    if not source.is_configured():
        log.info(
            "source skipped", source=source.name.value, region=region.code, reason="not configured"
        )
        return row(SnapshotStatus.skipped, [], "not configured")

    if not source.supports(region):
        return row(SnapshotStatus.skipped, [], "region not supported by this source")

    try:
        items = await source.fetch(region, limit=FETCH_LIMIT)
    except Exception as exc:
        # One flaky endpoint must not cost us the other three sources.
        log.warning(
            "source failed",
            source=source.name.value,
            region=region.code,
            error=f"{type(exc).__name__}: {exc}",
        )
        return row(SnapshotStatus.error, [], f"{type(exc).__name__}: {exc}")

    status = SnapshotStatus.ok if items else SnapshotStatus.empty
    return row(status, items)


async def ingest_region(
    session: AsyncSession,
    region: Region,
    sources: list[TrendSource],
    run_id: str,
    captured_at: datetime,
    semaphore: asyncio.Semaphore,
) -> dict[str, int]:
    """Snapshot every source for one region, then rebuild that region's board."""

    async def guarded(source: TrendSource) -> dict[str, Any]:
        async with semaphore:
            return await fetch_one(source, region, run_id, captured_at)

    rows = await asyncio.gather(*(guarded(s) for s in sources))

    # ON CONFLICT DO NOTHING makes a retried task a no-op rather than a dupe.
    await session.execute(
        pg_insert(TrendSnapshot)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_trend_snapshots_run")
    )

    by_name = {s.name.value: s for s in sources}
    contributions = [
        SourceItems(
            source=str(row["source"].value),
            weight=by_name[str(row["source"].value)].weight,
            items=[RawTrendItem(**item) for item in row["items"]],
        )
        for row in rows
        if row["status"] is SnapshotStatus.ok
    ]

    # Read before the commit below. `expire_on_commit` is on, so every
    # attribute of `region` becomes a lazy refresh afterwards, and an
    # attribute refresh cannot await — it raises MissingGreenlet from inside
    # plain attribute access, with no frame of ours in the traceback.
    region_id, region_code = region.id, region.code

    merged = merge(contributions, limit=BOARD_LIMIT)
    wrote_board = await upsert_trends(session, region, merged, captured_at)
    await session.commit()

    # After the board exists, not alongside it: per-platform rows are
    # projected from the items attached to each trend, so this is correct
    # whether the merge wrote the board or the curator did. Runs even when
    # `upsert_trends` stepped aside for a curated region, which is exactly
    # the case that matters.
    platform_rows = await sync_platforms(session, region_id, captured_at, merged=merged)
    await session.commit()

    counts = {
        "items": sum(int(r["item_count"]) for r in rows),
        "topics": len(merged) if wrote_board else 0,
        "sources_ok": len(contributions),
        "platform_rows": platform_rows,
    }
    log.info("region ingested", region=region_code, **counts)
    return counts


async def upsert_trends(
    session: AsyncSession, region: Region, merged: list, captured_at: datetime
) -> bool:
    """Rewrite one region's board from the non-LLM merge.

    Skipped entirely once a region has been curated. The merge keys topics on
    the *source* title and the curator keys them on its own rewritten title,
    so running both against one table is not a merge — it is two writers with
    different primary keys. The beat was re-creating every curated topic under
    its raw headline and blanking the categories and summaries the curator had
    written. A curated region's board belongs to the curator; everything else
    still gets the merge, which is what keeps the other 50 regions populated.
    """
    curated = await session.scalar(
        select(func.count())
        .select_from(Trend)
        .where(Trend.region_id == region.id, Trend.curated_at.is_not(None))
    )
    if curated:
        log.info("board is curated, leaving it alone", region=region.code, curated_rows=curated)
        return False

    existing = {
        t.topic_key: t
        for t in (await session.scalars(select(Trend).where(Trend.region_id == region.id))).all()
    }
    seen: set[str] = set()

    for position, topic in enumerate(merged, start=1):
        seen.add(topic.topic_key)
        row = existing.get(topic.topic_key)
        if row is None:
            row = Trend(
                region_id=region.id,
                topic_key=topic.topic_key,
                first_seen_at=captured_at,
                status=PipelineStatus.curated,
            )
            session.add(row)

        row.topic = topic.topic
        row.category = topic.category
        row.rank = position
        row.score = topic.score
        row.volume = topic.volume
        row.velocity = next_velocity(row.velocity, topic.score)
        row.hashtags = topic.hashtags
        row.sources = topic.sources
        row.evidence = topic.evidence
        row.last_seen_at = captured_at
        if row.status is PipelineStatus.ingested:
            row.status = PipelineStatus.curated

    # A topic that dropped off keeps its row and history but loses its rank, so
    # it can come back without resetting the sparkline to zeros.
    for key, row in existing.items():
        if key not in seen and row.rank != 0:
            row.rank = 0
            row.velocity = next_velocity(row.velocity, 0.0)

    return True


async def run_cycle(region_codes: list[str] | None = None) -> dict[str, Any]:
    """One full ingest cycle. Used by the Celery task and by `run_once`."""
    run_id = str(uuid.uuid4())
    captured_at = utcnow()
    sources = all_sources()
    semaphore = asyncio.Semaphore(max(1, settings.ingest_max_concurrency))

    log.info(
        "cycle started",
        run_id=run_id,
        sources=[s.name.value for s in sources if s.is_configured()],
        skipped=[s.name.value for s in sources if not s.is_configured()],
    )

    async with SessionLocal() as session:
        query = (
            select(Region)
            .where(Region.is_active.is_(True))
            .order_by(Region.sort_order)
            # XAdapter.supports() reads `woeids_for_rollup`, which walks
            # `children` for any region without a WOEID of its own — every
            # state and union territory. Lazily loading it inside the cycle
            # raises MissingGreenlet from plain attribute access.
            .options(selectinload(Region.children))
        )
        if region_codes:
            query = query.where(Region.code.in_(region_codes))
        regions = (await session.scalars(query)).all()

        totals = {"regions": 0, "items": 0, "topics": 0}
        for region in regions:
            counts = await ingest_region(session, region, sources, run_id, captured_at, semaphore)
            totals["regions"] += 1
            totals["items"] += counts["items"]
            totals["topics"] += counts["topics"]

    result = {"run_id": run_id, "captured_at": captured_at.isoformat(), **totals}
    log.info("cycle finished", **result)
    return result


async def _run_cycle_and_release(region_codes: list[str] | None) -> dict[str, Any]:
    """Run a cycle and drop the connection pool *inside the same loop*.

    The worker process is reused across tasks and each task gets a fresh
    asyncio.run() loop. Disposing the engine from a later loop leaves asyncpg
    trying to close sockets bound to the finished one, which surfaces as
    `RuntimeError: Event loop is closed` after an otherwise successful task.
    """
    try:
        return await run_cycle(region_codes)
    finally:
        await engine.dispose()


@shared_task(name="app.tasks.content.generate_content", bind=True, max_retries=0)
def generate_content(self, job_id: int) -> dict[str, Any]:
    """Run one content job. No retries: run_job records failure on the row and
    the Desk offers "Try again", which is a clearer loop than a silent retry."""
    from app.db.session import task_sessions
    from app.tasks.content import run_job

    async def _run() -> dict[str, Any]:
        # A per-task engine, not the shared one: see task_sessions().
        async with task_sessions() as sessions:
            return await run_job(job_id, sessions)

    return asyncio.run(_run())


@shared_task(
    name="app.tasks.video.render_video",
    bind=True,
    max_retries=0,
    # A reel is a render, a voice service and a mix. The default limits are
    # sized for an ingest cycle and would kill it part way through.
    soft_time_limit=1500,
    time_limit=1800,
)
def render_video(self, job_id: int) -> dict[str, Any]:
    """Run one reel job. No retries: run_reel records failure on the row and
    the Desk offers "Try again", which is clearer than a silent retry."""
    from app.db.session import task_sessions
    from app.tasks.video import run_reel

    async def _run() -> dict[str, Any]:
        async with task_sessions() as sessions:
            return await run_reel(job_id, sessions)

    return asyncio.run(_run())


@shared_task(name="app.tasks.curate.curate_daily", bind=True, max_retries=0)
def curate_daily(self) -> dict[str, Any]:
    """The once-a-day scheduled curate. One region per run, in order.

    Sequential rather than dispatched together: two curate tasks in flight
    share one process's rate limiters, and the second loses every batch to
    the first — measured, when Maharashtra and Tamil Nadu were queued at the
    same time and Tamil Nadu came back empty in two minutes.

    No retry. A failure here is the daily budget being gone, and retrying
    spends what is left of it to fail again; the next day's run is the
    retry. The curator preserves a previously described row when it cannot
    describe one, so a bad day costs freshness rather than content.
    """
    from app.tasks.curate import run_curate

    regions = settings.curate_region_list
    results: dict[str, Any] = {"regions": {}}

    async def _run(code: str) -> dict[str, Any]:
        try:
            with background():
                return await run_curate([code])
        finally:
            await engine.dispose()

    for code in regions:
        try:
            results["regions"][code] = asyncio.run(_run(code))
        except Exception as exc:
            # One region failing must not cost the others their turn.
            log.error("daily curate failed", region=code, error=f"{type(exc).__name__}: {exc}")
            results["regions"][code] = {"error": f"{type(exc).__name__}"}

    log.info("daily curate finished", regions=list(results["regions"]))
    return results


@shared_task(name="app.tasks.curate.curate_regions", bind=True, max_retries=1)
def curate_regions(self, region_codes: list[str] | None = None) -> dict[str, Any]:
    """Curate after ingest. Only the configured regions run on the beat —
    curating all 53 would be ~80 Gemini calls a cycle, well past the free
    tier; everything else curates when a user opens it."""
    from app.tasks.curate import run_curate

    async def _run() -> dict[str, Any]:
        try:
            return await run_curate(region_codes)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.error("curate failed", error=f"{type(exc).__name__}: {exc}")
        raise self.retry(exc=exc, countdown=300) from exc


@shared_task(name="app.tasks.ingest.ingest_all_regions", bind=True, max_retries=2)
def ingest_all_regions(self, region_codes: list[str] | None = None) -> dict[str, Any]:
    """Beat entrypoint. Every 30 minutes by default."""
    try:
        result = asyncio.run(_run_cycle_and_release(region_codes))
    except Exception as exc:
        log.error("cycle failed", error=f"{type(exc).__name__}: {exc}")
        raise self.retry(exc=exc, countdown=60) from exc

    # No curate here any more. It used to be dispatched after every cycle,
    # which on the free tier was 48 attempts a day against an allowance of
    # 20 per model: the budget was gone by mid-morning and every later run
    # re-described the boards from source titles. It now runs once a day on
    # its own schedule — see curate_daily.
    return result
