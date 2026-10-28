"""Brands: the profile a post is written and drawn from.

Separate from `content.py` because a brand is edited by a person filling in
a form and a job is created by a machine reacting to a topic. The two have
almost no shared vocabulary.

Everything here reads and writes the one default workspace. The parameter is
threaded through anyway — `workspace_id()` is where a Clerk dependency goes
later, and every query already filters on what it returns.
"""

from __future__ import annotations

import asyncio
import hashlib
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.models import Brand, ContentJob, Language, Workspace
from app.storage import put_bytes

router = APIRouter(tags=["brands"])
log = get_logger("api.brands")

#: Which bundled face the templates set headlines in. Two, deliberately:
#: the design system names two, and a brand picking a third would stop
#: looking like this product.
FONT_CHOICES = ("display", "ui")

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

#: A logo is drawn into a 1080px image, so anything past a couple of
#: megabytes is a camera roll upload rather than a logo. Enforced while
#: reading rather than from content-length, which the client controls.
MAX_LOGO_BYTES = 2 * 1024 * 1024
#: No SVG, deliberately. Pillow cannot rasterise one, so an SVG logo would
#: look right on the brand page and then silently fall back to the wordmark
#: on every post — the worst of both. Accepting only what all three renderers
#: can draw means what a team uploads is what they get.
LOGO_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
#: Lists that arrive from a textarea. Capped so one paste cannot make every
#: later writer prompt enormous.
MAX_LINES = 40


def workspace_id() -> int:
    """The workspace this request acts in.

    One workspace until auth lands, and then this reads the session instead
    of returning a constant. A function rather than the constant inlined at
    each call site, so that change is one edit.
    """
    return Workspace.DEFAULT_ID


def slugify(name: str) -> str:
    """An ASCII slug, or empty when the name has no ASCII in it.

    Deliberately ASCII-only, and deliberately not in `core.hashtags`: a URL
    segment is not text normalisation. A brand named only in Devanagari gets
    nothing back from this and the caller is asked for a slug, rather than
    handed a transliteration nobody chose.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]


def _hex(value: str) -> str:
    if not HEX.match(value):
        raise ValueError("expected a hex colour like #D8322B")
    body = value[1:]
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    return f"#{body.upper()}"


def _face(value: str) -> str:
    if value not in FONT_CHOICES:
        raise ValueError(f"expected one of {', '.join(FONT_CHOICES)}")
    return value


def _lines(value: list[str]) -> list[str]:
    # Stripped and de-blanked here rather than in the form: these arrive as
    # a textarea split on newlines, where a blank line is a keystroke rather
    # than an entry.
    return [line.strip() for line in value if line.strip()][:MAX_LINES]


def _slug(value: str) -> str:
    clean = slugify(value)
    if not clean:
        raise ValueError("a slug needs at least one ascii letter or digit")
    return clean


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
    products: list[str]
    default_region_code: str | None
    do_not_mention: list[str]


class BrandIn(BaseModel):
    """Create. Everything but the name has a default, because a team should
    be able to make a brand and generate something, then fill the rest in
    once they have seen what the posts look like."""

    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    voice_prompt: str = ""
    primary_color: str = "#1B2230"
    secondary_color: str = "#D8322B"
    languages: list[Language] = Field(default_factory=lambda: [Language.english])
    font_choice: str = "display"
    products: list[str] = Field(default_factory=list)
    default_region_code: str | None = Field(default=None, max_length=16)
    do_not_mention: list[str] = Field(default_factory=list)

    @field_validator("primary_color", "secondary_color")
    @classmethod
    def _check_colour(cls, value: str) -> str:
        return _hex(value)

    @field_validator("font_choice")
    @classmethod
    def _check_face(cls, value: str) -> str:
        return _face(value)

    @field_validator("products", "do_not_mention")
    @classmethod
    def _check_lines(cls, value: list[str]) -> list[str]:
        return _lines(value)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str | None) -> str | None:
        return None if value is None else _slug(value)


class BrandPatch(BaseModel):
    """Update. Every field optional, and absent is not null — the form sends
    only what the user touched."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    voice_prompt: str | None = None
    #: Settable to null, which is how a logo is removed.
    logo_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    languages: list[Language] | None = None
    font_choice: str | None = None
    products: list[str] | None = None
    default_region_code: str | None = Field(default=None, max_length=16)
    do_not_mention: list[str] | None = None

    @field_validator("primary_color", "secondary_color")
    @classmethod
    def _check_colour(cls, value: str | None) -> str | None:
        return None if value is None else _hex(value)

    @field_validator("font_choice")
    @classmethod
    def _check_face(cls, value: str | None) -> str | None:
        return None if value is None else _face(value)

    @field_validator("products", "do_not_mention")
    @classmethod
    def _check_lines(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _lines(value)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str | None) -> str | None:
        return None if value is None else _slug(value)


async def _load(brand_id: int, session: AsyncSession, ws: int) -> Brand:
    brand = await session.get(Brand, brand_id)
    # Checked against the workspace rather than just fetched by id: once
    # there is more than one, a wrong id must be a 404 and not somebody
    # else's brand.
    if brand is None or brand.workspace_id != ws:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown brand")
    return brand


@router.get("", response_model=list[BrandOut])
async def list_brands(
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> list[Brand]:
    rows = await session.scalars(
        select(Brand).where(Brand.workspace_id == ws).order_by(Brand.name, Brand.id)
    )
    return list(rows.all())


@router.get("/{brand_id}", response_model=BrandOut)
async def get_brand(
    brand_id: int,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> Brand:
    return await _load(brand_id, session, ws)


@router.post("", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandIn,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> Brand:
    slug = payload.slug or slugify(payload.name)
    if not slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="this name has no ascii in it, so send a slug as well",
        )

    brand = Brand(
        workspace_id=ws,
        slug=slug,
        name=payload.name,
        voice_prompt=payload.voice_prompt,
        primary_color=payload.primary_color,
        secondary_color=payload.secondary_color,
        languages=[str(language) for language in payload.languages],
        font_choice=payload.font_choice,
        products=payload.products,
        default_region_code=payload.default_region_code,
        do_not_mention=payload.do_not_mention,
    )
    session.add(brand)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"a brand called {slug!r} already exists"
        ) from exc
    await session.commit()
    log.info("brand created", brand_id=brand.id, slug=brand.slug)
    return brand


@router.patch("/{brand_id}", response_model=BrandOut)
async def update_brand(
    brand_id: int,
    payload: BrandPatch,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> Brand:
    brand = await _load(brand_id, session, ws)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("languages") is not None:
        fields["languages"] = [str(language) for language in fields["languages"]]

    for key, value in fields.items():
        # None clears logo_url and default_region_code, which are nullable.
        # Clearing anything else would violate the column, so it is skipped:
        # PATCH cannot tell a deliberate blank from a field the form left
        # out, and the safe reading is "unchanged".
        if value is None and key not in ("logo_url", "default_region_code"):
            continue
        setattr(brand, key, value)
        if key == "logo_url" and value is None:
            # Or the renderers would keep drawing a logo the brand page says
            # has been removed.
            brand.logo_key = None

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="another brand already has that slug"
        ) from exc
    await session.commit()
    log.info("brand updated", brand_id=brand.id, fields=sorted(fields))
    return brand


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: int,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> None:
    """Delete a brand, refusing while it still has content.

    `content_jobs.brand_id` is ON DELETE RESTRICT on purpose: a brand is a
    settings page and the library is a body of work, and a stray click on a
    settings page should not be able to destroy the work. So the first
    attempt counts what would go and refuses with the number, which is what
    a confirm dialog needs to say. `?force=true` is the answer to it.

    Not a soft delete either, because the slug has to come free — a brand
    nobody can see but whose name is still taken is its own kind of bug.
    """
    brand = await _load(brand_id, session, ws)
    items = await session.scalar(
        select(func.count()).select_from(ContentJob).where(ContentJob.brand_id == brand_id)
    )
    if items and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"{brand.name} has {items} item{'s' if items > 1 else ''} in the library. "
                "Deleting the brand deletes them too."
            ),
        )

    if items:
        # Explicitly, rather than by cascade: the constraint is what makes
        # the refusal above possible, so the force path has to do the work
        # the database is declining to do for it.
        await session.execute(delete(ContentJob).where(ContentJob.brand_id == brand_id))
    await session.delete(brand)
    await session.commit()
    log.info("brand deleted", brand_id=brand_id, items=items or 0)


@router.post("/{brand_id}/logo", response_model=BrandOut)
async def upload_logo(
    brand_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    ws: int = Depends(workspace_id),
) -> Brand:
    """Store a logo and point the brand at it.

    The key carries a digest of the bytes, so re-uploading the same file is
    the same URL and a different file is a different one. The bucket's cache
    headers are immutable, and a stable key would serve the old logo for a
    year.
    """
    brand = await _load(brand_id, session, ws)

    extension = LOGO_TYPES.get((file.content_type or "").split(";")[0].strip())
    if extension is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="a logo must be png, jpeg, webp or svg",
        )

    data = b""
    while chunk := await file.read(64 * 1024):
        data += chunk
        if len(data) > MAX_LOGO_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"a logo must be under {MAX_LOGO_BYTES // (1024 * 1024)} MB",
            )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the file was empty")

    digest = hashlib.sha256(data).hexdigest()[:16]
    key = f"brands/{brand.id}/logo-{digest}.{extension}"
    # boto3 is synchronous and this is a request handler, so off the loop it
    # goes. Every other caller of put_bytes is a Celery task, which does not
    # care.
    url = await asyncio.to_thread(put_bytes, key, data, file.content_type)

    # Both, because they are for different readers: the URL is what a browser
    # fetches and the key is what the renderers read, since the URL is
    # host-facing and resolves to nothing inside the worker.
    brand.logo_url = url
    brand.logo_key = key
    await session.commit()
    log.info("logo stored", brand_id=brand.id, key=key, bytes=len(data))
    return brand
