"""The Remotion renderer, over HTTP.

Remotion needs Node and its own Chromium, so it runs as a separate service
(packages/remotion/server/index.ts) and this adapter is the only thing in the
Python side that knows that. Swap in a different VideoProvider and nothing
above this file changes.

`is_configured()` means "we have somewhere to send this", not "it answered a
moment ago" — the same meaning it has for the Gemini adapters, where a key
being present does not promise the call succeeds. Unreachable is a render-time
failure with a message that names the cause, which is what lands on the job
row and then in front of the user.
"""

from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.video.base import SIZES, RenderedVideo, VideoBrief, VideoProvider

log = get_logger("video.remotion")

#: Composition ids registered in packages/remotion/src/Root.tsx.
COMPOSITIONS: dict[str, str] = {
    "reel": "Reel",
    "square": "Square",
}

#: Short, because /health is called by the compose healthcheck every ten
#: seconds and by the top-bar dot on every board load. Without this, one slow
#: renderer makes the API's own health check time out and marks the API
#: unhealthy — a service that is not even on the board's path taking the board
#: down with it.
HEALTH_TTL_SECONDS = 10.0
HEALTH_TIMEOUT_SECONDS = 2.0

_health_cache: tuple[float, dict[str, object]] | None = None


class VideoError(RuntimeError):
    """A failure worth showing the user verbatim."""


class RemotionVideoProvider(VideoProvider):
    name = "remotion"

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url if base_url is not None else settings.renderer_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.renderer_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def health(self) -> dict[str, object]:
        """What /health says, or why it could not be asked.

        Used by the API's own health endpoint and by the studio, so "reels are
        off because the renderer is down" is visible before a user queues one
        and waits. Cached for HEALTH_TTL_SECONDS — see the note there.
        """
        global _health_cache

        if not self.is_configured():
            return {"ok": False, "error": "RENDERER_URL is not set"}

        now = time.monotonic()
        if _health_cache and now - _health_cache[0] < HEALTH_TTL_SECONDS:
            return _health_cache[1]

        try:
            async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                data = response.json()
                result = data if isinstance(data, dict) else {"ok": False, "error": "bad response"}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

        _health_cache = (now, result)
        return result

    async def render(self, brief: VideoBrief) -> RenderedVideo:
        if not self.is_configured():
            raise VideoError("No renderer is configured, so reels cannot be rendered.")

        composition = COMPOSITIONS.get(brief.size)
        if composition is None:
            raise VideoError(f"There is no composition for the {brief.size!r} size.")

        payload = {"composition": composition, "props": brief.as_props()}
        try:
            # Long by default: a 30s reel at 1080x1920 is 900 frames through a
            # headless browser, which is minutes on a laptop.
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/render", json=payload)
        except httpx.TimeoutException as exc:
            raise VideoError(
                f"The renderer did not finish within {self.timeout:.0f}s. "
                "A shorter script renders faster."
            ) from exc
        except httpx.HTTPError as exc:
            raise VideoError(
                f"Could not reach the renderer at {self.base_url}. Is it running?"
            ) from exc

        if response.status_code >= 400:
            raise VideoError(f"The renderer failed: {_detail(response)}")

        mp4 = response.content
        if not mp4:
            raise VideoError("The renderer returned an empty video.")

        width, height = brief.dimensions
        frames = _int_header(response, "x-duration-frames", brief.duration_in_frames)
        fps = _int_header(response, "x-fps", brief.as_props()["fps"])

        log.info(
            "video rendered",
            composition=composition,
            frames=frames,
            bytes=len(mp4),
            render_id=response.headers.get("x-render-id", ""),
        )

        return RenderedVideo(
            mp4=mp4,
            width=_int_header(response, "x-width", width),
            height=_int_header(response, "x-height", height),
            fps=fps,
            duration_seconds=frames / fps if fps else brief.duration_seconds,
            template=brief.template,
            size=brief.size if brief.size in SIZES else "reel",
            # Rendered muted on purpose: the voiceover and the music bed are
            # mixed in by ffmpeg, where the voice decides the length.
            has_audio=False,
            meta={"composition": composition, "frames": frames},
        )


def _detail(response: httpx.Response) -> str:
    """The renderer's own message where it sent one.

    It reaches the job row and then the Desk, and "font file not found" is
    something a user can act on where "500" is not.
    """
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])[:400]
    except Exception:
        pass
    return f"HTTP {response.status_code}"


def _int_header(response: httpx.Response, name: str, fallback: int) -> int:
    try:
        return int(response.headers[name])
    except (KeyError, TypeError, ValueError):
        return int(fallback)
