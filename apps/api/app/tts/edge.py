"""Microsoft Neural voices, via edge-tts.

No key and no cost, which is why it is the default — but it is also not an
official API, so `TTS_ENABLED` exists and a failure here is reported rather
than swallowed. A reel that was asked for with a voiceover and comes back
silent is worse than one that fails and says why: the silence looks like a
finished job.

Duration is measured from the encoded audio with ffprobe, not taken from the
boundary events. The last boundary ends at the last syllable, and the encoder
leaves trailing silence after it; using the boundary would put every cut a
fraction early and land it on a half-spoken word.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Language
from app.tts.base import Speech, TTSProvider, voice_for
from app.video.ffmpeg import FFmpegError, duration_seconds

log = get_logger("tts.edge")

#: edge-tts reports offsets in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000

#: Which boundary events to keep. Version 7 emits SentenceBoundary where
#: earlier ones emitted WordBoundary, and matching only the latter is how you
#: end up with a timings list that is always empty and nobody notices.
BOUNDARY_TYPES = {"WordBoundary", "SentenceBoundary"}

#: Narration longer than this is a script problem, not a TTS problem, and it
#: would make a reel nobody watches to the end.
MAX_SEGMENT_SECONDS = 20.0


class TTSError(RuntimeError):
    """A failure worth showing the user verbatim."""


class EdgeTTSProvider(TTSProvider):
    name = "edge-tts"

    def __init__(self, *, enabled: bool | None = None, timeout: float | None = None) -> None:
        self.enabled = settings.tts_enabled if enabled is None else enabled
        self.timeout = settings.tts_timeout_seconds if timeout is None else timeout

    def is_configured(self) -> bool:
        return bool(self.enabled)

    async def speak(self, text: str, language: Language) -> Speech:
        if not self.is_configured():
            raise TTSError("Voiceover is switched off (TTS_ENABLED), so reels have no narration.")

        spoken = " ".join(text.split())
        if not spoken:
            raise TTSError("There is nothing to narrate: the line is empty.")

        voice = voice_for(language)
        audio, boundaries = await self._synthesise(spoken, voice)

        # Written to disk because ffprobe reads files, and because a 20-second
        # mp3 is small enough that the round trip is not worth avoiding.
        with tempfile.TemporaryDirectory(prefix="tf-tts-") as directory:
            path = Path(directory) / "voice.mp3"
            path.write_bytes(audio)
            try:
                seconds = await duration_seconds(path)
            except FFmpegError as exc:
                raise TTSError(f"The narration came back unreadable: {exc}") from exc

        if seconds > MAX_SEGMENT_SECONDS:
            raise TTSError(
                f"One line narrates to {seconds:.0f}s, past the {MAX_SEGMENT_SECONDS:.0f}s "
                "a single card can hold. Shorten the script."
            )

        log.info(
            "narrated",
            voice=voice,
            language=language.value,
            seconds=round(seconds, 2),
            boundaries=len(boundaries),
            bytes=len(audio),
        )
        return Speech(
            audio=audio,
            format="mp3",
            duration_seconds=seconds,
            voice=voice,
            boundaries=boundaries,
            meta={"boundaries": len(boundaries)},
        )

    async def _synthesise(self, text: str, voice: str) -> tuple[bytes, list[tuple[float, str]]]:
        """Stream one utterance, collecting audio and whatever timings come with it."""
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - the package is a dependency
            raise TTSError("edge-tts is not installed in this image.") from exc

        audio = bytearray()
        boundaries: list[tuple[float, str]] = []

        async def collect() -> None:
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                kind = chunk.get("type")
                if kind == "audio":
                    audio.extend(chunk.get("data") or b"")
                elif kind in BOUNDARY_TYPES:
                    offset = float(chunk.get("offset") or 0) / TICKS_PER_SECOND
                    boundaries.append((round(offset, 3), str(chunk.get("text") or "")))

        try:
            await asyncio.wait_for(collect(), timeout=self.timeout)
        except TimeoutError:
            raise TTSError(
                f"The voice service did not answer within {self.timeout:.0f}s."
            ) from None
        except TTSError:
            raise
        except Exception as exc:
            # Unofficial endpoint: it returns a 403 when the handshake changes,
            # and the name of the exception is the most useful thing we have.
            raise TTSError(f"The voice service failed: {type(exc).__name__}: {exc}"[:300]) from exc

        if not audio:
            raise TTSError("The voice service returned no audio.")
        return bytes(audio), boundaries
