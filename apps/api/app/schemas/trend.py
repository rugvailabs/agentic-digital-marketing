"""Response models. These are the contract @trendforge/types is generated from."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import RegionKind


class RegionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(examples=["IN-MH"])
    name: str = Field(examples=["Maharashtra"])
    kind: RegionKind
    parent_code: str | None = Field(default=None, examples=["IN"])
    google_trends_geo: str | None = None
    x_woeid: int | None = None
    #: Rows currently on this region's board. 0 => never ingested, or all stale.
    trend_count: int = 0


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int = Field(ge=1, examples=[1])
    topic: str = Field(examples=["Asia cup final"])
    category: str | None = Field(default=None, examples=["Sports"])
    hashtags: list[str] = Field(default_factory=list, examples=[["#AsiaCupFinal"]])
    #: Best available volume proxy; 0 when no source reported one.
    volume: int = 0
    #: Six scores, oldest first: this cycle plus the previous five.
    velocity: list[float] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, examples=[["google_trends"]])
    score: float = 0.0
    updated_at: datetime
    #: Links, publishers and thumbnails behind the row, for the Desk panel.
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class TrendsResponse(BaseModel):
    region: RegionOut
    #: None when the region has never been ingested.
    updated_at: datetime | None
    count: int
    trends: list[TrendOut]


class IngestRunResponse(BaseModel):
    run_id: str
    captured_at: datetime
    regions: int
    items: int
    topics: int
    #: True when the cycle ran inline instead of being queued to Celery.
    inline: bool
