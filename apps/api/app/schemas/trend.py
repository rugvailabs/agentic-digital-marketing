"""Response models. These are the contract @trendforge/types is generated from.

Every field here is **required**, including the nullable ones. The API always
populates them — the DB columns are non-nullable with defaults — and a Pydantic
default would make the field optional in the OpenAPI schema, which lands in the
generated TypeScript as `hashtags?: string[]` and forces every call site in the
web app to defend against an `undefined` that cannot happen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import RegionKind, SourceName


class RegionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(examples=["IN-MH"])
    name: str = Field(examples=["Maharashtra"])
    kind: RegionKind
    parent_code: str | None = Field(examples=["IN"])
    google_trends_geo: str | None = Field(examples=["IN-MH"])
    x_woeid: int | None = Field(examples=[2295411])
    #: Rows currently on this region's board. 0 => never ingested, or all stale.
    trend_count: int = Field(examples=[40])
    #: Summed volume of those rows. Orders the region strip: busiest first.
    total_volume: int = Field(examples=[4200000])
    #: Platforms that are configured *and* cover this region. Both halves
    #: matter: YouTube is configured everywhere and covers only the country,
    #: and Reddit covers a region only where subreddits are mapped. A filter
    #: chip that can never match anything is worse than no chip.
    platforms: list[SourceName] = Field(examples=[[SourceName.google_trends]])


class PlatformOut(BaseModel):
    """One platform and whether this deployment can use it."""

    name: SourceName = Field(examples=[SourceName.reddit])
    label: str = Field(examples=["Reddit"])
    configured: bool
    #: Variables to set before `configured` can be true. The settings page
    #: lists these verbatim so a user is told what to set rather than that
    #: something is unavailable. Empty for sources needing no credentials.
    env_vars: list[str] = Field(examples=[["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]])
    #: Weight of this platform's ranks in the merge.
    weight: float = Field(examples=[0.7])


class TrendPlatformOut(BaseModel):
    """What one platform says about one topic.

    Not comparable across platforms, which is the reason these are separate
    rows rather than summed into the topic: `volume` is upvotes on Reddit,
    views on YouTube and a lifetime post count on Instagram.
    """

    model_config = ConfigDict(from_attributes=True)

    platform: SourceName = Field(examples=[SourceName.reddit])
    #: None where the platform has no ordering of its own — Instagram returns
    #: counts, not a chart. Null and 0 mean different things here.
    rank: int | None = Field(examples=[2])
    volume: int = Field(examples=[18400])
    #: This platform's hashtags, never pooled with another's.
    hashtags: list[str] = Field(examples=[["#AskIndia", "#Cricket"]])
    url: str | None = Field(examples=["https://reddit.com/r/india/comments/abc"])
    seen_at: datetime


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #: Database id. The content studio posts this back to create a job.
    id: int = Field(examples=[168])
    rank: int = Field(ge=1, examples=[1])
    topic: str = Field(examples=["Asia cup final"])
    category: str | None = Field(examples=["Sports"])
    hashtags: list[str] = Field(examples=[["#AsiaCupFinal", "#Sports"]])
    #: Best available volume proxy; 0 when no source reported one.
    volume: int = Field(examples=[200000])
    #: Six scores, oldest first: this cycle plus the previous five.
    velocity: list[float] = Field(examples=[[0.0, 0.0, 12.5, 40.0, 88.0, 100.0]])
    sources: list[str] = Field(examples=[["google_trends", "google_news"]])
    score: float = Field(examples=[100.0])
    #: Curator's one-line brief. None until a region has been curated.
    summary: str | None = Field(examples=["England face Sri Lanka in the third T20I."])
    #: none | sensitive | skip. `skip` rows are not served by default.
    safety_flag: str | None = Field(examples=["none"])
    updated_at: datetime
    #: Links, publishers and thumbnails behind the row, for the Desk panel.
    evidence: list[dict[str, Any]]
    #: Per-platform rows, ordered by platform. Empty until step 4's ingest
    #: has populated `trend_sources` for this topic.
    platforms: list[TrendPlatformOut]


class TrendsResponse(BaseModel):
    region: RegionOut
    #: None when the region has never been ingested.
    updated_at: datetime | None
    #: Full board size, independent of `limit`, so the UI can say "20 of 40".
    count: int = Field(examples=[40])
    trends: list[TrendOut]


class IngestRunResponse(BaseModel):
    run_id: str
    captured_at: datetime
    regions: int
    items: int
    topics: int
    #: True when the cycle ran inline instead of being queued to Celery.
    inline: bool
