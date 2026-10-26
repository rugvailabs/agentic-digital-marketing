"""The VideoProvider interface and the brief a composition renders from.

Same shape as ImageProvider: a plain dataclass in, bytes out, and
`is_configured()` so an unreachable renderer skips the video leg rather than
failing the job. No database objects reach the renderer — it is a separate
process (and a separate language), so the brief is the whole contract.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

#: Output sizes. Reel is the 9:16 slot every short-form surface takes; square
#: is the feed. Both at 1080 wide, which is what Instagram serves.
SIZES: dict[str, tuple[int, int]] = {
    "reel": (1080, 1920),
    "square": (1080, 1080),
}

#: 30 is enough for type and a wipe, and halves the render against 60.
FPS = 30

#: What the opening and closing cards hold for when nothing has been narrated
#: over them. Once there is a voiceover these come from its measured length,
#: like every other card.
DEFAULT_TITLE_SECONDS = 2.0
DEFAULT_OUTRO_SECONDS = 1.5

#: A beat shorter than this cannot be read; longer and the reel drags.
MIN_BEAT_SECONDS = 1.6
MAX_BEAT_SECONDS = 4.5
#: Hard ceiling on the whole reel. Past this, reach drops on every network and
#: the free-tier TTS call starts timing out.
MAX_DURATION_SECONDS = 45.0


@dataclass(slots=True)
class Beat:
    """One on-screen card: a line of type held for `seconds`."""

    text: str
    seconds: float
    #: Optional second line, set smaller under the first.
    detail: str = ""

    @property
    def frames(self) -> int:
        return max(1, round(self.seconds * FPS))

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "detail": self.detail, "frames": self.frames}


@dataclass(slots=True)
class VideoBrief:
    """Everything a composition needs, serialisable straight to --props."""

    headline: str
    beats: list[Beat]
    brand_name: str
    primary_color: str
    secondary_color: str
    #: "reel" | "square"
    size: str = "reel"
    template: str = "wire"
    logo_url: str | None = None
    region_name: str = ""
    hashtags: list[str] = field(default_factory=list)
    #: Drawn as a sparkline on the closing card; empty means no chart.
    velocity: list[float] = field(default_factory=list)
    #: Unicode script name ("DEVANAGARI", "TAMIL", "LATIN") so the composition
    #: picks the same bundled Noto face Pillow would.
    script: str = "LATIN"
    alt_text: str = ""
    #: Lengths of the opening and closing cards. None means "use the default":
    #: a reel with narration measures them, a silent one does not.
    title_seconds: float | None = None
    outro_seconds: float | None = None

    @property
    def dimensions(self) -> tuple[int, int]:
        return SIZES.get(self.size, SIZES["reel"])

    @property
    def title_frames(self) -> int:
        return _frames(self.title_seconds, DEFAULT_TITLE_SECONDS)

    @property
    def outro_frames(self) -> int:
        return _frames(self.outro_seconds, DEFAULT_OUTRO_SECONDS)

    @property
    def duration_in_frames(self) -> int:
        beats = sum(beat.frames for beat in self.beats)
        return max(FPS, self.title_frames + beats + self.outro_frames)

    @property
    def duration_seconds(self) -> float:
        return self.duration_in_frames / FPS

    def as_props(self) -> dict[str, Any]:
        """The JSON handed to Remotion. Keys are camelCase on that side."""
        width, height = self.dimensions
        return {
            "headline": self.headline,
            "beats": [beat.as_dict() for beat in self.beats],
            "brandName": self.brand_name,
            "primaryColor": self.primary_color,
            "secondaryColor": self.secondary_color,
            "logoUrl": self.logo_url,
            "regionName": self.region_name,
            "hashtags": self.hashtags,
            "velocity": self.velocity,
            "script": self.script,
            "width": width,
            "height": height,
            "fps": FPS,
            "titleFrames": self.title_frames,
            "outroFrames": self.outro_frames,
            "durationInFrames": self.duration_in_frames,
        }


@dataclass(slots=True)
class RenderedVideo:
    mp4: bytes
    width: int
    height: int
    fps: int
    duration_seconds: float
    template: str
    size: str
    #: True when the mp4 already carries an audio track.
    has_audio: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


def _frames(seconds: float | None, fallback: float) -> int:
    value = fallback if seconds is None or seconds <= 0 else seconds
    return max(1, round(value * FPS))


class VideoProvider(abc.ABC):
    """Check, then call. A provider that is not configured is skipped."""

    name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False => the caller skips this provider, logging why."""

    @abc.abstractmethod
    async def render(self, brief: VideoBrief) -> RenderedVideo:
        """Render one silent video. Raise on failure; the caller decides."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} configured={self.is_configured()}>"
