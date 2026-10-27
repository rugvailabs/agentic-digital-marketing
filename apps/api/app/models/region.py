"""Region hierarchy: country > state/UT > city.

X WOEIDs attach to cities only; a state's WOEIDs are its cities' WOEIDs
(see `Region.woeids_for_rollup`). Google Trends geo codes attach to the
country and to states/UTs, which is the granularity Trends actually serves.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class RegionKind(enum.StrEnum):
    country = "country"
    state = "state"
    union_territory = "union_territory"
    city = "city"


class Region(Base, TimestampMixin):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Stable external code: "IN", "IN-MH", "IN-MH-MUM". Used in API query params.
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[RegionKind] = mapped_column(
        Enum(RegionKind, name="region_kind", native_enum=True), nullable=False
    )

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=True
    )
    parent: Mapped[Region | None] = relationship(
        remote_side=lambda: [Region.id], back_populates="children"
    )
    children: Mapped[list[Region]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )

    # Google Trends geo code, e.g. "IN", "IN-MH". None => not served by Trends.
    google_trends_geo: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Yahoo WOEID used by X's trends/place.json. Cities only.
    x_woeid: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Display order on the region strip (lower = earlier). India first.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_regions_kind_sort_order", "kind", "sort_order"),
        Index("ix_regions_parent_id", "parent_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Region {self.code} {self.name}>"

    @property
    def woeids_for_rollup(self) -> list[int]:
        """X WOEIDs to pull for this region: its own, else its children's.

        Callers must eager-load `children` — `selectinload(Region.children)`.
        Every region except the country and the cities falls through to the
        relationship, and a lazy load here happens inside plain attribute
        access, which cannot await: it surfaces as MissingGreenlet with no
        frame of the caller's in the traceback. It has now been fixed in
        three places (the ingest cycle, /regions, /trends), so it is worth
        saying here rather than finding again.
        """
        if self.x_woeid is not None:
            return [self.x_woeid]
        return [c.x_woeid for c in self.children if c.x_woeid is not None]
