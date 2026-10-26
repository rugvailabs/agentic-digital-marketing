"""Video rendering registry."""

from app.video.base import (
    FPS,
    MAX_BEAT_SECONDS,
    MAX_DURATION_SECONDS,
    MIN_BEAT_SECONDS,
    SIZES,
    Beat,
    RenderedVideo,
    VideoBrief,
    VideoProvider,
)
from app.video.remotion import COMPOSITIONS, RemotionVideoProvider, VideoError

__all__ = [
    "COMPOSITIONS",
    "FPS",
    "MAX_BEAT_SECONDS",
    "MAX_DURATION_SECONDS",
    "MIN_BEAT_SECONDS",
    "SIZES",
    "Beat",
    "RemotionVideoProvider",
    "RenderedVideo",
    "VideoBrief",
    "VideoError",
    "VideoProvider",
]
