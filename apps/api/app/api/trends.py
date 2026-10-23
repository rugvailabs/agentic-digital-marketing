"""GET /trends — the ranked ladder for one region."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.session import get_session
from app.models import Region, SafetyFlag, Trend
from app.schemas.trend import RegionOut, TrendOut, TrendsResponse

router = APIRouter(tags=["trends"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@router.get("", response_model=TrendsResponse)
async def list_trends(
    region: str = Query(default="IN", description="Region code, e.g. IN or IN-MH"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    include_flagged: bool = Query(
        default=False,
        description="Include topics the curator flagged `skip` (disaster, death, "
        "communal, election result). Off by default: we do not market against these.",
    ),
    session: AsyncSession = Depends(get_session),
) -> TrendsResponse:
    parent = aliased(Region)
    row = (
        await session.execute(
            select(Region, parent.code)
            .join(parent, Region.parent_id == parent.id, isouter=True)
            .where(Region.code == region)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown region: {region}")
    region_row, parent_code = row

    visible = [Trend.region_id == region_row.id, Trend.rank > 0]
    if not include_flagged:
        # is_distinct_from, not !=: a NULL flag (never curated) must still show.
        visible.append(Trend.safety_flag.is_distinct_from(SafetyFlag.skip.value))

    trends = (
        await session.scalars(select(Trend).where(*visible).order_by(Trend.rank).limit(limit))
    ).all()

    totals = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Trend.volume), 0))
            .select_from(Trend)
            .where(*visible)
        )
    ).one()
    total, total_volume = int(totals[0] or 0), int(totals[1] or 0)
    # Board freshness, not row freshness: the newest last_seen_at in the region.
    updated_at = await session.scalar(
        select(func.max(Trend.last_seen_at)).where(Trend.region_id == region_row.id)
    )

    return TrendsResponse(
        region=RegionOut(
            code=region_row.code,
            name=region_row.name,
            kind=region_row.kind,
            parent_code=parent_code,
            google_trends_geo=region_row.google_trends_geo,
            x_woeid=region_row.x_woeid,
            trend_count=total,
            total_volume=total_volume,
        ),
        updated_at=updated_at,
        count=total,
        trends=[
            TrendOut(
                id=t.id,
                rank=t.rank,
                topic=t.topic,
                category=t.category,
                hashtags=t.hashtags,
                volume=t.volume,
                velocity=t.velocity,
                sources=t.sources,
                score=t.score,
                summary=t.summary,
                safety_flag=t.safety_flag,
                updated_at=t.last_seen_at,
                evidence=t.evidence,
            )
            for t in trends
        ],
    )
