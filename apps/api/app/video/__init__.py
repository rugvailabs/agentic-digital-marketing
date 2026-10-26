"""Video rendering registry."""

from app.video.base import (
    DEFAULT_OUTRO_SECONDS,
    DEFAULT_TITLE_SECONDS,
    FPS,
    MAX_BEAT_SECONDS,
    MAX_DURATION_SECONDS,
    MIN_BEAT_SECONDS,
    SIZES,
    Beat,
    Caption,
    RenderedVideo,
    VideoBrief,
    VideoProvider,
)
from app.video.remotion import COMPOSITIONS, RemotionVideoProvider, VideoError

__all__ = [
    "COMPOSITIONS",
    "DEFAULT_OUTRO_SECONDS",
    "DEFAULT_TITLE_SECONDS",
    "FPS",
    "MAX_BEAT_SECONDS",
    "MAX_DURATION_SECONDS",
    "MIN_BEAT_SECONDS",
    "SIZES",
    "Beat",
    "Caption",
    "RemotionVideoProvider",
    "RenderedVideo",
    "VideoBrief",
    "VideoError",
    "VideoProvider",
]
