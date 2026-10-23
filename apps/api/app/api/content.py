"""Content studio endpoints: brands, jobs, assets."""

from __future__ import annotations

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
    JobStatus,
    Language,
    SafetyFlag,
    Trend,
)

router = APIRouter(tags=["content"])
log = get_logger("api.content")


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    voice_prompt: str
    logo_url: str | None
    primary_color: str
    secondary_color: str
    languages: list[str]
    font_choice: str


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
    language: Language
    formats: list[str]
    status: JobStatus
    error: str | None
    assets: list[AssetOut]


class JobCreate(BaseModel):
    trend_id: int
    brand_id: int
    language: Language = Language.english
    #: Any of SIZES; empty means square only.
    formats: list[str] = Field(default_factory=lambda: ["square", "portrait"])


class AssetPatch(BaseModel):
    """Only a caption's text fields are editable."""

    caption: str | None = None
    hook: str | None = None
    hashtags: list[str] | None = None
    alt_text: str | None = None


@router.get("/brands", response_model=list[BrandOut], tags=["brands"])
async def list_brands(session: AsyncSession = Depends(get_session)) -> list[Brand]:
    return list((await session.scalars(select(Brand).order_by(Brand.id))).all())


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

    formats = [f for f in payload.formats if f in SIZES] or ["square"]
    job = ContentJob(
        trend_id=trend.id,
        brand_id=brand.id,
        language=payload.language,
        formats=formats,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    try:
        from app.tasks.ingest import generate_content

        generate_content.delay(job.id)
        log.info("job queued", job_id=job.id, language=job.language.value, formats=formats)
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
    session: AsyncSession = Depends(get_session),
) -> ContentJob | None:
    """The most recent job for a topic, or null.

    Without this a generated post disappears on reload, which makes the studio
    feel like it lost your work even though the assets are still stored.
    """
    return await session.scalar(
        select(ContentJob)
        .where(ContentJob.trend_id == trend_id)
        .order_by(ContentJob.id.desc())
        .limit(1)
    )


@router.get("/content/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> ContentJob:
    job = await session.get(ContentJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown job")
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
