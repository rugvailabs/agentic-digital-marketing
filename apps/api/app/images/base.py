"""The ImageProvider interface and the brief a template renders from."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

#: Output sizes. Square for the feed, portrait for the 4:5 slot that takes the
#: most vertical space Instagram allows.
SIZES: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
}


@dataclass(slots=True)
class ImageBrief:
    """Everything a template needs. No database objects reach the renderer."""

    headline: str
    subline: str
    hashtags: list[str]
    brand_name: str
    primary_color: str
    secondary_color: str
    alt_text: str = ""
    logo_url: str | None = None
    #: "square" | "portrait"
    size: str = "square"
    template: str = "bold-type"

    @property
    def dimensions(self) -> tuple[int, int]:
        return SIZES.get(self.size, SIZES["square"])


@dataclass(slots=True)
class RenderedImage:
    png: bytes
    width: int
    height: int
    template: str
    size: str
    meta: dict[str, Any] = field(default_factory=dict)


class ImageProvider(abc.ABC):
    """Same contract as the other adapters: check, then call."""

    name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False => the caller skips this provider, logging why."""

    @abc.abstractmethod
    def render(self, brief: ImageBrief) -> RenderedImage:
        """Render one image. Raise on failure; the caller decides what to do."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.is_configured()}>"
