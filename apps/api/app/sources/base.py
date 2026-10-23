"""The TrendSource interface.

Every external capability is an adapter behind an interface (CLAUDE.md). The
contract that matters here: `is_configured()` is checked before a source is
ever called, and `fetch()` must raise rather than return junk — the caller
records the failure on the snapshot row and carries on with the other sources.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Any

from app.models import Region, SourceName


@dataclass(slots=True)
class RawTrendItem:
    """One topic as a single source saw it, before any merging.

    `rank` is 1-based within that source's response: it is the only signal
    every source agrees on, so it carries most of the scoring weight.
    """

    title: str
    rank: int
    # Source-native volume proxy: Trends traffic, YouTube view count, else None.
    volume: int | None = None
    url: str | None = None
    category: str | None = None
    # Anything source-specific worth showing on the Desk panel.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrendSource(abc.ABC):
    """Base class for every trend source."""

    #: Enum member stored on the snapshot row.
    name: SourceName
    #: Weight of this source's ranks in the merge. Higher = more trusted.
    weight: float = 1.0

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False => the orchestrator skips this source, logging why."""

    @abc.abstractmethod
    def supports(self, region: Region) -> bool:
        """False => this source has no identifier for that region."""

    @abc.abstractmethod
    async def fetch(self, region: Region, limit: int = 20) -> list[RawTrendItem]:
        """Return items in source rank order. Raise on transport failure."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name.value} configured={self.is_configured()}>"
