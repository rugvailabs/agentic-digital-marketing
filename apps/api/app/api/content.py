"""Content studio endpoints: brands, jobs, assets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.images.base import SIZES
from app.models import (
    AssetKind,
    Brand,
    ContentAsset,
    ContentJob,
    EditorialStatus,
    JobKind,
    JobStatus,
    Language,
    SafetyFlag,
    Trend,
)
from app.video.base import SIZES as VIDEO_SIZES

router = APIRouter(tags=["content"])
log = get_logger("api.content")


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: AssetKind
    variant: str
    url: str | None
    meta_json: dict[str, Any]
    edited: bool


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trend_id: int
    brand_id: int
    kind: JobKind
    language: Language
    formats: list[str]
    status: JobStatus
    editorial_status: EditorialStatus
    scheduled_at: datetime | None
    error: str | None
    assets: list[AssetOut]


class JobCreate(BaseModel):
    trend_id: int
    brand_id: int
    #: "post" for captions and images, "reel" for a narrated video.
    kind: JobKind = JobKind.post
    language: Language = Language.english
    #: Image sizes for a post, video sizes for a reel. Empty falls back to the
    #: one size that kind always supports.
    formats: list[str] = Field(default_factory=list)


class AssetPatch(BaseModel):
    """Only a caption's text fields are editable."""

    caption: str | None = None
    hook: str | None = None
    hashtags: list[str] | None = None
    alt_text: str | None = None


@router.post("/content/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate, session: AsyncSession = Depends(get_session)
) -> ContentJob:
    trend = await session.get(Trend, payload.trend_id)
    if trend is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown topic")
    if trend.safety_flag == SafetyFlag.skip.value:
        # Refused here as well as in the worker: a client should get a clear
        # 422 rather than a job that queues and then fails.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="this topic is flagged as one we do not market against",
        )

    brand = await session.get(Brand, payload.brand_id)
    if brand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown brand")

    reel = payload.kind is JobKind.reel
    allowed = VIDEO_SIZES if reel else SIZES
    formats = [f for f in payload.formats if f in allowed] or (
        ["reel"] if reel else ["square", "portrait"]
    )

    job = ContentJob(
        # One workspace until auth exists, and the job records it rather
        # than reaching through its brand: the library and the calendar
        # filter on it, and a join through brands on every query is a cost
        # paid forever to avoid one column.
        workspace_id=brand.workspace_id,
        trend_id=trend.id,
        brand_id=brand.id,
        kind=payload.kind,
        language=payload.language,
        formats=formats,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    try:
        from app.tasks.ingest import generate_content, render_video

        task = render_video if reel else generate_content
        task.delay(job.id)
        log.info(
            "job queued",
            job_id=job.id,
            kind=job.kind.value,
            language=job.language.value,
            formats=formats,
        )
    except Exception as exc:
        # No broker: say so on the row rather than leaving it queued forever.
        job.status = JobStatus.failed
        job.error = f"could not queue the job: {type(exc).__name__}. Is the worker running?"
        await session.commit()
        await session.refresh(job)

    return job


@router.get("/content/jobs", response_model=JobOut | None)
async def latest_job(
    trend_id: int,
    kind: JobKind = JobKind.post,
    session: AsyncSession = Depends(get_session),
) -> ContentJob | None:
    """The most recent job of one kind for a topic, or null.

    Without this a generated post disappears on reload, which makes the studio
    feel like it lost your work even though the assets are still stored. Posts
    and reels are asked for separately, because the Desk shows both at once
    and "the latest job" would otherwise be whichever was run last.
    """
    return await session.scalar(
        select(ContentJob)
        .where(ContentJob.trend_id == trend_id, ContentJob.kind == kind)
        .order_by(ContentJob.id.desc())
        .limit(1)
    )


@router.get("/content/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> ContentJob:
    job = await session.get(ContentJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown job")
    return job


class JobPatch(BaseModel):
    """Where a person has got to with an item, and when it should go out.

    Separate from JobStatus, which is where the pipeline got to. A job can
    be `ready` and still a draft; a `posted` item is still `ready`; a failed
    render says nothing about whether its author had approved the caption.
    One column could not carry both.
    """

    editorial_status: EditorialStatus | None = None
    #: Null clears the schedule. A time only — nothing publishes yet.
    scheduled_at: datetime | None = None


@router.patch("/content/jobs/{job_id}", response_model=JobOut)
async def patch_job(
    job_id: int,
    payload: JobPatch = Body(...),
    session: AsyncSession = Depends(get_session),
) -> ContentJob:
    """Move an item through draft -> approved -> scheduled -> posted.

    The library and the calendar both write here. Scheduling is the only
    transition with a rule attached, and it is enforced rather than assumed:
    a `scheduled` row with no time is invisible on the calendar and looks
    like work that was lost.
    """
    job = await session.get(ContentJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown job")

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="nothing to update")

    wanted = fields.get("editorial_status", job.editorial_status)
    # exclude_unset above is what makes this readable: an absent
    # scheduled_at means "leave it", an explicit null means "clear it".
    when = fields.get("scheduled_at", job.scheduled_at)

    if wanted is EditorialStatus.scheduled and when is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a scheduled item needs a time",
        )
    if when is not None and wanted in (EditorialStatus.draft, EditorialStatus.approved):
        # Dragging a scheduled item back to draft is a real action, and it
        # means the time no longer applies. Keeping it would leave the item
        # on the calendar after the user took it off.
        when = None

    job.editorial_status = wanted
    job.scheduled_at = when
    await session.commit()
    await session.refresh(job)
    log.info(
        "job moved",
        job_id=job.id,
        editorial_status=job.editorial_status.value,
        scheduled_at=job.scheduled_at.isoformat() if job.scheduled_at else None,
    )
    return job


@router.patch("/content/assets/{asset_id}", response_model=AssetOut)
async def patch_asset(
    asset_id: int,
    payload: AssetPatch = Body(...),
    session: AsyncSession = Depends(get_session),
) -> ContentAsset:
    asset = await session.get(ContentAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown asset")
    if asset.kind is not AssetKind.caption:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="only captions are editable"
        )

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="nothing to update")

    # Copy, don't mutate: SQLAlchemy does not see in-place JSONB edits.
    meta = dict(asset.meta_json)
    meta.update(fields)
    meta["edited_at"] = utcnow().isoformat()
    asset.meta_json = meta
    # Marks the caption as human-owned, so a re-run keeps it.
    asset.edited = True

    await session.commit()
    await session.refresh(asset)
    log.info("caption edited", asset_id=asset.id, fields=sorted(fields))
    return asset
