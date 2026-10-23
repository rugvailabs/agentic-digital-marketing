"""Raw per-source captures (`trend_snapshots`) and the merged board (`trends`)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

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

from app.db.base import Base, TimestampMixin
from app.models.region import Region


class SourceName(enum.StrEnum):
    google_trends = "google_trends"
    google_news = "google_news"
    youtube = "youtube"
    x = "x"


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
    # Set by the safety filter in step 2 (disaster/death/communal/election-result).
    safety_flag: Mapped[str | None] = mapped_column(String(64), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("region_id", "topic_key", name="uq_trends_region_id_topic_key"),
        Index("ix_trends_region_rank", "region_id", "rank"),
        Index("ix_trends_last_seen_at", "last_seen_at"),
    )
