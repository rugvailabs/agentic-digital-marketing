"""Raw per-source captures (`trend_snapshots`) and the merged board (`trends`)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
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
from app.models.region import Region

#: Must match GEMINI_EMBED_DIM; changing the setting alone does not reshape
#: the column, so a change needs a migration.
EMBED_DIM = settings.gemini_embed_dim


class SourceName(enum.StrEnum):
    google_trends = "google_trends"
    google_news = "google_news"
    youtube = "youtube"
    x = "x"
    reddit = "reddit"
    instagram = "instagram"


class SnapshotStatus(enum.StrEnum):
    ok = "ok"
    empty = "empty"
    skipped = "skipped"  # adapter not configured
    error = "error"


class PipelineStatus(enum.StrEnum):
    """Explicit pipeline position, per CLAUDE.md. Step 1 reaches `curated`."""

    ingested = "ingested"
    curated = "curated"
    planned = "planned"
    written = "written"
    image_rendered = "image_rendered"
    video_rendered = "video_rendered"
    reviewed = "reviewed"
    published = "published"
    skipped = "skipped"


class TrendSnapshot(Base, TimestampMixin):
    """One adapter run against one region. Append-only; never updated.

    Idempotency: a task may be retried, so (region, source, run_id) is unique
    and writes use ON CONFLICT DO NOTHING.
    """

    __tablename__ = "trend_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[Region] = relationship(lazy="selectin")

    source: Mapped[SourceName] = mapped_column(
        Enum(SourceName, name="source_name", native_enum=True), nullable=False
    )
    # Shared by every snapshot in one ingest cycle.
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status", native_enum=True),
        nullable=False,
        default=SnapshotStatus.ok,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # List[RawTrendItem] as dicts, in source rank order.
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("region_id", "source", "run_id", name="uq_trend_snapshots_run"),
        Index("ix_trend_snapshots_region_captured", "region_id", "captured_at"),
        Index("ix_trend_snapshots_captured_at", "captured_at"),
    )


class Trend(Base, TimestampMixin):
    """Merged, ranked topic for a region. One row per (region, topic_key)."""

    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[Region] = relationship(lazy="selectin")

    # Display text, best-cased variant seen across sources.
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    # Normalised dedupe key (lowercase, punctuation and stopwords stripped).
    topic_key: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Best available volume proxy (Trends traffic, YouTube views, else 0).
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Last 6 scores, oldest first: current + previous 5 snapshots.
    velocity: Mapped[list[float]] = mapped_column(JSONB, nullable=False, default=list)
    # camelCased from the topic, e.g. "#AsiaCupFinal".
    #
    # Two writers, and they do not agree. The curator rewrites this column
    # with handles it chose and length-capped; the non-LLM merge fills it by
    # camel-casing the whole source headline, which yields tags nobody would
    # publish — #AIToolHelpedRajasthanRoyals. Read `curator_hashtags` rather
    # than this column anywhere the value is going out to a network.
    hashtags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Source names that contributed, e.g. ["google_trends", "google_news"].
    sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Links/thumbnails/rank per source, for the Desk panel.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[PipelineStatus] = mapped_column(
        Enum(PipelineStatus, name="pipeline_status", native_enum=True),
        nullable=False,
        default=PipelineStatus.ingested,
    )
    # SafetyFlag value set by the curator: none | sensitive | skip. `skip` is
    # hidden from GET /trends by default.
    safety_flag: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── curator output (step 2) ──────────────────────────────────────────
    #: Durable topic id, minted once and carried forward on every match.
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Normalised keys of every source item ever folded into this topic —
    #: "google_news:<url>" or "google_trends:h<hash of title>". This is what
    #: identity is actually matched on: headlines get reworded and centroids
    #: drift, but the same article URL is the same article.
    member_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: One-line summary written by the curator; the writer's brief.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Cluster centroid, kept so a later run can match topics across cycles.
    #: Updated as an exponential moving average, so it drifts with the story
    #: rather than snapping to the most recent run.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)
    curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def curator_hashtags(self) -> list[str]:
        """Hashtags fit to publish, which is only ever the curator's.

        `curated_at` is the discriminator and it is exact: the merge never
        sets it, and `upsert_trends` leaves a curated region alone, so a
        non-null value means these tags came from the curator's own output
        and have been through its length cap. Null means they were
        camel-cased off a source headline and are the whole headline as one
        word, which is unusable on any network.
        """
        return list(self.hashtags or []) if self.curated_at else []

    #: Per-platform rows for this topic. Ordered by platform so the Desk's
    #: groups and the ladder's marks come out in a stable order rather than
    #: whatever the planner returned.
    platforms: Mapped[list[TrendPlatform]] = relationship(
        back_populates="trend",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TrendPlatform.platform",
    )

    __table_args__ = (
        UniqueConstraint("region_id", "topic_key", name="uq_trends_region_id_topic_key"),
        Index("ix_trends_region_rank", "region_id", "rank"),
        Index("ix_trends_last_seen_at", "last_seen_at"),
    )


class TrendPlatform(Base, TimestampMixin):
    """One platform's view of one topic. Table is `trend_sources`.

    The class is not called TrendSource because CLAUDE.md gives that name to
    the adapter interface, and two TrendSources — one you fetch with, one you
    store — would collide on every import that touched both. The table keeps
    the name it was specified with.

    A topic is usually trending in more than one place at once, and the
    platforms disagree about it in ways worth keeping: a story can be rank 2
    on Reddit and rank 14 on YouTube, and the tags that work on one are not
    the tags that work on the other. `trends` holds what is true about the
    topic; this holds what is true about the topic *on a platform*.

    Hashtags are stored per platform and never merged. Merging them was the
    obvious thing and it is wrong: #AskReddit has no meaning on Instagram and
    a 30-tag Instagram block reads as spam in a YouTube description. The Desk
    groups them by platform for the same reason, and a copy button per group
    only makes sense if they were never pooled.
    """

    __tablename__ = "trend_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SourceName] = mapped_column(
        Enum(SourceName, name="source_name", native_enum=True), nullable=False
    )

    #: Rank on that platform, 1-based. Null where the platform has no
    #: ordering of its own — Instagram hashtag search returns counts, not a
    #: chart, and inventing a rank for it would make it sortable by accident.
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Whatever that platform counts: X tweet volume, Reddit upvotes,
    #: YouTube views, Instagram media count. Not comparable across
    #: platforms, which is why it is stored per row rather than summed.
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hashtags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: Where to see it on that platform. The Desk links the platform mark to
    #: this, so a marketer can check the claim before posting about it.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trend: Mapped[Trend] = relationship(back_populates="platforms")

    __table_args__ = (
        # One row per platform per topic: an ingest cycle updates the row it
        # already has rather than appending, so the table stays the size of
        # the board and not of its history. `trend_snapshots` is the
        # append-only record if you need to know what changed.
        UniqueConstraint("trend_id", "platform", name="uq_trend_sources_trend_platform"),
        Index("ix_trend_sources_trend_id", "trend_id"),
        # The ?platform= filter on /trends reads this, so it is indexed with
        # rank: filtering by platform and ordering by its rank is one query.
        Index("ix_trend_sources_platform_rank", "platform", "rank"),
    )
