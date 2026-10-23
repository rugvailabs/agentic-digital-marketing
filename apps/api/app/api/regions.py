"""GET /regions — everything the region strip needs, in display order."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.session import get_session
from app.models import Region, RegionKind, Trend
from app.schemas.trend import RegionOut

router = APIRouter(tags=["regions"])


@router.get("", response_model=list[RegionOut])
async def list_regions(
    kind: RegionKind | None = Query(default=None, description="Filter to one tier"),
    with_trends_only: bool = Query(
        default=False, description="Only regions that currently have a board"
    ),
    session: AsyncSession = Depends(get_session),
) -> list[RegionOut]:
    parent = aliased(Region)
    # rank 0 means "dropped off the board but keep the history", so it must not
    # count towards a region looking populated.
    counts = (
        select(
            Trend.region_id,
            func.count().label("n"),
            # Drives the region strip's ordering: busiest states first. Summed
            # over the live board only, for the same reason as the count.
            func.coalesce(func.sum(Trend.volume), 0).label("volume"),
        )
        .where(Trend.rank > 0)
        .group_by(Trend.region_id)
        .subquery()
    )

    query = (
        select(Region, parent.code, func.coalesce(counts.c.n, 0), func.coalesce(counts.c.volume, 0))
        .join(parent, Region.parent_id == parent.id, isouter=True)
        .join(counts, counts.c.region_id == Region.id, isouter=True)
        .where(Region.is_active.is_(True))
        .order_by(Region.sort_order, Region.name)
    )
    if kind is not None:
        query = query.where(Region.kind == kind)
    if with_trends_only:
        query = query.where(func.coalesce(counts.c.n, 0) > 0)

    return [
        RegionOut(
            code=region.code,
            name=region.name,
            kind=region.kind,
            parent_code=parent_code,
            google_trends_geo=region.google_trends_geo,
            x_woeid=region.x_woeid,
            trend_count=int(count),
            total_volume=int(volume),
        )
        for region, parent_code, count, volume in (await session.execute(query)).all()
    ]
