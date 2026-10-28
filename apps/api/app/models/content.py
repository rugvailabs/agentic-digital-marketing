"""Step 2 tables: curated raw items, brands, and generated content."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin
from app.models.trend import SourceName

#: Vector width must match GEMINI_EMBED_DIM. gemini-embedding-001 is asked for
#: 768 dims explicitly; changing the setting alone would not reshape the column.
EMBED_DIM = settings.gemini_embed_dim


class SafetyFlag(enum.StrEnum):
    """Per CLAUDE.md: the planner skips disaster/death/communal/election-result.

    `sensitive` still shows on the board — a marketer should know it is moving
    — but the studio refuses to generate for it. `skip` is hidden outright.
    """

    none = "none"
    sensitive = "sensitive"
    skip = "skip"


class TrendItem(Base, TimestampMixin):
    """One raw source item, with the cluster it was assigned to.

    This is what the Evidence list reads: the snapshot JSON is append-only and
    awkward to query, where these rows join straight to a trend.
    """

    __tablename__ = "trend_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trend_id: Mapped[int | None] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), nullable=True
    )
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("trend_snapshots.id", ondelete="SET NULL"), nullable=True
    )

    source: Mapped[SourceName] = mapped_column(
        Enum(SourceName, name="source_name", native_enum=True, create_type=False), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: Cluster this item was assigned to within its run.
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)

    __table_args__ = (
        UniqueConstraint("region_id", "run_id", "source", "rank", name="uq_trend_items_slot"),
        Index("ix_trend_items_trend_id", "trend_id"),
        Index("ix_trend_items_region_run", "region_id", "run_id"),
    )


class Workspace(Base, TimestampMixin):
    """Who owns a brand and its content.

    There is exactly one of these today and no way to make another, because
    there is no auth yet. It exists now so that adding auth is a matter of
    creating rows and filtering queries, rather than a migration that
    backfills an owner onto every brand, job and asset already in the
    database — which is the expensive kind of change to make later.

    The trend board is deliberately not workspace-owned. What is trending in
    India is the same fact for everyone, so regions, trends and snapshots
    stay shared; only what a team makes from them is theirs.
    """

    __tablename__ = "workspaces"

    #: The single workspace everything belongs to until auth exists. Fixed
    #: rather than looked up by slug, so the default cannot drift.
    DEFAULT_ID = 1

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class EditorialStatus(enum.StrEnum):
    """Where a finished item is in a human's workflow.

    Separate from JobStatus, which is where the *pipeline* got to. The two
    answer different questions and move independently: a job can be `ready`
    and still `draft`, and a `posted` item is still `ready`. One column
    carrying both would have to describe a render failure and an editor's
    approval in the same vocabulary.
    """

    draft = "draft"
    approved = "approved"
    scheduled = "scheduled"
    posted = "posted"


class Brand(Base, TimestampMixin):
    """Who the post sounds like and looks like."""

    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    #: Unique per workspace, not globally: two teams may both have a brand
    #: called "acme", and the slug is how a URL names one.
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Free text dropped into the writer prompt.
    voice_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Where a browser fetches the logo: the public, host-facing URL.
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The same object's storage key, kept because the renderers cannot use
    #: the URL above. `logo_url` is built from S3_PUBLIC_URL, which is
    #: localhost from the browser's point of view and nothing at all from
    #: inside the worker — so Pillow reads the bytes by key, and Remotion is
    #: handed an endpoint-internal URL built from it.
    logo_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#1B2230")
    secondary_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#D8322B")
    #: Languages this brand publishes in, as Language values.
    languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: "display" | "ui" — which bundled face the templates set headlines in.
    font_choice: Mapped[str] = mapped_column(String(32), nullable=False, default="display")

    #: What the brand sells, in its own words. Goes to the writer so a post
    #: about a trend can connect it to something the brand actually offers.
    products: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: Region whose board this brand opens on. A code rather than a foreign
    #: key: regions are seeded reference data and a brand pointing at one
    #: should not be able to block reseeding them.
    default_region_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Words, people and competitors this brand will not mention. Enforced in
    #: the writer prompt and checked after, because a prompt is a request
    #: rather than a guarantee.
    do_not_mention: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_brands_workspace_slug"),
        Index("ix_brands_workspace_id", "workspace_id"),
    )


class Language(enum.StrEnum):
    english = "english"
    hinglish = "hinglish"
    hindi = "hindi"
    tamil = "tamil"
    telugu = "telugu"
    bengali = "bengali"
    marathi = "marathi"


class JobStatus(enum.StrEnum):
    queued = "queued"
    writing = "writing"
    #: Reels only: the voiceover is being narrated. It comes before the frames
    #: because its length decides how many frames there are.
    voicing = "voicing"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class JobKind(enum.StrEnum):
    """What the job produces.

    A reel runs a longer pipeline than a post — script, voiceover, frames,
    audio mix — with its own ways of failing. Sharing one row would mean one
    `status` column describing two pipelines, so each gets its own row and the
    status stays unambiguous.
    """

    post = "post"
    reel = "reel"


class AssetKind(enum.StrEnum):
    caption = "caption"
    image = "image"
    video = "video"
    #: The voiceover on its own, kept so a user can hear it without the video
    #: and so a re-render can skip the TTS call.
    audio = "audio"
    #: The spoken script and its on-screen beats.
    script = "script"


class ContentJob(Base, TimestampMixin):
    """One request to generate a post or a reel for one topic."""

    __tablename__ = "content_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False
    )
    brand: Mapped[Brand] = relationship(lazy="selectin")

    language: Mapped[Language] = mapped_column(
        Enum(Language, name="content_language", native_enum=True), nullable=False
    )
    kind: Mapped[JobKind] = mapped_column(
        Enum(JobKind, name="job_kind", native_enum=True),
        nullable=False,
        default=JobKind.post,
        server_default=JobKind.post.value,
    )
    #: Requested output sizes: ["square", "portrait"] for a post,
    #: ["reel", "square"] for a reel.
    formats: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=True),
        nullable=False,
        default=JobStatus.queued,
    )
    #: Set when status is failed; shown verbatim in the Desk so a user can act.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Where a human has taken it. Independent of `status` above — see
    #: EditorialStatus.
    editorial_status: Mapped[EditorialStatus] = mapped_column(
        Enum(EditorialStatus, name="editorial_status", native_enum=True),
        nullable=False,
        default=EditorialStatus.draft,
        server_default=EditorialStatus.draft.value,
    )
    #: When this is meant to go out, in UTC. Set by the calendar and nothing
    #: else reads it yet: scheduling stores a time, and publishing is a later
    #: step. Null for anything not scheduled.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assets: Mapped[list[ContentAsset]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_content_jobs_trend_kind", "trend_id", "kind"),
        # The library lists one workspace's items newest first, and the
        # calendar asks for a date range; both read this.
        Index("ix_content_jobs_workspace_created", "workspace_id", "created_at"),
        Index("ix_content_jobs_scheduled_at", "scheduled_at"),
    )


class ContentAsset(Base, TimestampMixin):
    """A caption, image, video, voiceover or script belonging to a job."""

    __tablename__ = "content_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    job: Mapped[ContentJob] = relationship(back_populates="assets")

    kind: Mapped[AssetKind] = mapped_column(
        Enum(AssetKind, name="asset_kind", native_enum=True), nullable=False
    )
    #: "<size>:<template>" for images and video; the language for a caption.
    variant: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: Public URL for anything with bytes behind it; null for captions and
    #: scripts, whose text lives in meta.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Caption fields, or width/height/template/duration/alt text.
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: True once a human has edited it, so a regenerate can refuse to clobber.
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_content_assets_job_id", "job_id"),)
