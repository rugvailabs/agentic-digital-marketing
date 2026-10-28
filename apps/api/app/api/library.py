"""The content library: everything this workspace has generated.

A read endpoint, deliberately. Creating work is `/content/jobs` and moving
it through draft → approved → scheduled → posted is a PATCH on the job
itself; this is the one place that asks "what do we have", and it answers
with the handful of fields a row needs rather than the whole job.

That distinction is the point. A library page showing fifty items would
otherwise carry fifty jobs' worth of assets — every caption, every image
variant, every meta blob — to render fifty lines of text and a thumbnail.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.brands import workspace_id
from app.core.logging import get_logger
from app.db.session import get_session
from app.models import (
    AssetKind,
    Brand,
    ContentJob,
    EditorialStatus,
    JobKind,
    JobStatus,
    Language,
    Region,
    Trend,
)

router = APIRouter(tags=["library"])
log = get_logger("api.library")

#: A page. Big enough that scrolling is rare on a real workspace, small
#: enough that one request stays under a megabyte.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class LibraryItem(BaseModel):
    """One row. Flat on purpose — a row is read, not traversed."""

    id: int
    kind: JobKind
    language: Language
    formats: list[str]
    #: Where the pipeline got to.
    status: JobStatus
    #: Where a person got to. The two move independently.
    editorial_status: EditorialStatus
    scheduled_at: datetime | None
    created_at: datetime
    error: str | None

    brand_id: int
    brand_name: str

    trend_id: int
    topic: str
    region_code: str
    region_name: str

    #: The caption's hook, which is what a person recognises an item by —
    #: the topic is what it is about, the hook is what this post says.
    hook: str | None
    #: First image or video, for the row's thumbnail. Null while a job is
    #: still running, and null forever if it failed.
    preview_url: str | None
    #: How many assets exist, so a row can say "3 images" without carrying
    #: three asset objects to do it.
    asset_count: int


class LibraryPage(BaseModel):
    items: list[LibraryItem]
    #: Matching the filters, not on the page. The header says "12 of 340".
    total: int
    limit: int
    offset: int


class LibraryFacets(BaseModel):
    """What the filters can usefully offer.

    Built from the workspace's own rows rather than from the enums: offering
    Bengali in a dropdown when nothing has ever been written in Bengali is a
    dead end dressed as a choice.
    """

    brands: list[dict[str, object]]
    regions: list[dict[str, object]]
    languages: list[str]
    formats: list[str]


def _filtered(
    ws: int,
    *,
    brand_id: int | None,
    region: str | None,
    language: Language | None,
    kind: JobKind | None,
    editorial_status: EditorialStatus | None,
    fmt: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    q: str | None,
) -> Select:
    """The shared WHERE, so the page and its count cannot disagree."""
    stmt = (
        select(ContentJob)
        .join(Trend, Trend.id == ContentJob.trend_id)
        .join(Region, Region.id == Trend.region_id)
        .where(ContentJob.workspace_id == ws)
    )

    if brand_id is not None:
        stmt = stmt.where(ContentJob.brand_id == brand_id)
    if region:
        # A state board's items, or — for a country — the country's and
        # every region under it, because "show me India" from the region
        # strip should not mean "only the national board".
        stmt = stmt.where(or_(Region.code == region, Region.code.like(f"{region}-%")))
    if language is not None:
        stmt = stmt.where(ContentJob.language == language)
    if kind is not None:
        stmt = stmt.where(ContentJob.kind == kind)
    if editorial_status is not None:
        stmt = stmt.where(ContentJob.editorial_status == editorial_status)
    if fmt:
        # JSONB containment, which the GIN-less column still answers quickly
        # at this size and which beats loading every row to filter in Python.
        stmt = stmt.where(ContentJob.formats.contains([fmt]))
    if created_from is not None:
        stmt = stmt.where(ContentJob.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(ContentJob.created_at <= created_to)
    if q:
        stmt = stmt.where(Trend.topic.ilike(f"%{q}%"))

    return stmt


@router.get("", response_model=LibraryPage)
async def list_library(
    brand_id: int | None = None,
    region: str | None = None,
    language: Language | None = None,
    kind: JobKind | None = None,
    #: Named `status` in the query string because that is what a user calls
    #: it; the pipeline's own status is not filterable here, since nobody
    #: browses their library by "currently rendering".
    status: EditorialStatus | None = None,
    format: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    q: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> LibraryPage:
    base = _filtered(
        ws,
        brand_id=brand_id,
        region=region,
        language=language,
        kind=kind,
        editorial_status=status,
        fmt=format,
        created_from=created_from,
        created_to=created_to,
        q=q,
    )

    total = await session.scalar(base.with_only_columns(func.count(ContentJob.id)).order_by(None))

    rows = (
        await session.scalars(
            base.options(
                selectinload(ContentJob.brand),
                selectinload(ContentJob.assets),
            )
            # Newest first, and by id as a tiebreak: created_at has
            # microsecond resolution but a batch writes several rows inside
            # one, and a page boundary that falls in the middle of a tie
            # would repeat or drop an item.
            .order_by(ContentJob.created_at.desc(), ContentJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    # One query for the topics on this page, rather than a lazy load per row.
    trends = (
        {
            trend.id: trend
            for trend in (
                await session.scalars(
                    select(Trend)
                    .options(selectinload(Trend.region))
                    .where(Trend.id.in_([job.trend_id for job in rows]))
                )
            ).all()
        }
        if rows
        else {}
    )

    items = [_item(job, trends.get(job.trend_id)) for job in rows]
    return LibraryPage(items=items, total=total or 0, limit=limit, offset=offset)


def _item(job: ContentJob, trend: Trend | None) -> LibraryItem:
    caption = next((a for a in job.assets if a.kind is AssetKind.caption), None)
    preview = next(
        (a for a in job.assets if a.kind in (AssetKind.video, AssetKind.image) and a.url),
        None,
    )
    return LibraryItem(
        id=job.id,
        kind=job.kind,
        language=job.language,
        formats=list(job.formats or []),
        status=job.status,
        editorial_status=job.editorial_status,
        scheduled_at=job.scheduled_at,
        created_at=job.created_at,
        error=job.error,
        brand_id=job.brand_id,
        brand_name=job.brand.name,
        trend_id=job.trend_id,
        # A trend can be swept up by the maintenance task while its content
        # survives, so the topic is restated rather than required.
        topic=trend.topic if trend else "Topic no longer on the board",
        region_code=trend.region.code if trend and trend.region else "",
        region_name=trend.region.name if trend and trend.region else "",
        hook=(caption.meta_json or {}).get("hook") if caption else None,
        preview_url=preview.url if preview else None,
        asset_count=len(job.assets),
    )


@router.get("/facets", response_model=LibraryFacets)
async def library_facets(
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> LibraryFacets:
    """What this workspace has actually produced, for the filter controls."""
    brands = (
        await session.execute(
            select(Brand.id, Brand.name, func.count(ContentJob.id))
            .join(ContentJob, ContentJob.brand_id == Brand.id)
            .where(ContentJob.workspace_id == ws)
            .group_by(Brand.id, Brand.name)
            .order_by(Brand.name)
        )
    ).all()

    regions = (
        await session.execute(
            select(Region.code, Region.name, func.count(ContentJob.id))
            .join(Trend, Trend.region_id == Region.id)
            .join(ContentJob, ContentJob.trend_id == Trend.id)
            .where(ContentJob.workspace_id == ws)
            .group_by(Region.code, Region.name)
            .order_by(Region.name)
        )
    ).all()

    languages = (
        await session.scalars(
            select(ContentJob.language)
            .where(ContentJob.workspace_id == ws)
            .group_by(ContentJob.language)
        )
    ).all()

    # Formats live in a JSONB array, so they are flattened here rather than
    # in SQL: the set is tiny and fixed, and jsonb_array_elements_text in a
    # group-by reads far worse than four lines of Python.
    formats: set[str] = set()
    for row in (
        await session.scalars(select(ContentJob.formats).where(ContentJob.workspace_id == ws))
    ).all():
        formats.update(row or [])

    return LibraryFacets(
        brands=[{"id": i, "name": n, "count": c} for i, n, c in brands],
        regions=[{"code": c, "name": n, "count": k} for c, n, k in regions],
        languages=sorted(str(language) for language in languages),
        formats=sorted(formats),
    )
