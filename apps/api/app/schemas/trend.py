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

from app.models import RegionKind


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


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    updated_at: datetime
    #: Links, publishers and thumbnails behind the row, for the Desk panel.
    evidence: list[dict[str, Any]]


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
