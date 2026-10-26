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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Language
from app.tts.base import DEFAULT_VOICE, Boundary, Speech, TTSProvider, voice_for
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

#: Voice ids the service reports, fetched once. None means the list could not
#: be fetched — which is not the same as a voice being missing, so nothing is
#: downgraded on that basis.
_known: frozenset[str] | None = None
_known_lock = asyncio.Lock()


async def _fetch_voices() -> list[Mapping[str, Any]]:
    """The raw listing. A seam, so the cache can be tested without a network."""
    import edge_tts

    # edge-tts types these as TypedDicts; Mapping is what is actually read.
    return list(await edge_tts.list_voices())


async def known_voices() -> frozenset[str] | None:
    """Every voice id edge-tts offers, or None if the list is unavailable.

    Fetched once per process and cached. Microsoft retires voice ids without
    notice, and a retired id does not fail loudly — it is simply not found,
    which is how a Tamil reel ends up narrated in English with nothing in the
    logs saying so.
    """
    global _known
    if _known is not None:
        return _known

    async with _known_lock:
        if _known is not None:
            return _known
        try:
            voices = await asyncio.wait_for(_fetch_voices(), timeout=20.0)
            _known = frozenset(str(v.get("ShortName") or "") for v in voices)
            log.info("voice list fetched", voices=len(_known))
        except Exception as exc:
            # Could not ask. Proceed with what was requested rather than
            # assuming the voice is gone.
            log.warning("could not list voices", error=f"{type(exc).__name__}: {exc}"[:200])
            return None
    return _known


async def resolve_voice(language: Language) -> str:
    """The voice for `language`, falling back to English if it is gone."""
    wanted = voice_for(language)
    known = await known_voices()
    if known is None or wanted in known:
        return wanted

    log.warning(
        "voice unavailable, falling back",
        wanted=wanted,
        language=language.value,
        using=DEFAULT_VOICE,
    )
    return DEFAULT_VOICE


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

        voice = await resolve_voice(language)
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

    async def _synthesise(self, text: str, voice: str) -> tuple[bytes, list[Boundary]]:
        """Stream one utterance, collecting audio and whatever timings come with it."""
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - the package is a dependency
            raise TTSError("edge-tts is not installed in this image.") from exc

        audio = bytearray()
        boundaries: list[Boundary] = []

        async def collect() -> None:
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                kind = chunk.get("type")
                if kind == "audio":
                    audio.extend(chunk.get("data") or b"")
                elif kind in BOUNDARY_TYPES:
                    # Duration as well as offset: a caption needs to know when
                    # to leave, not only when to arrive.
                    start = float(chunk.get("offset") or 0) / TICKS_PER_SECOND
                    length = float(chunk.get("duration") or 0) / TICKS_PER_SECOND
                    text_ = str(chunk.get("text") or "").strip()
                    if text_:
                        boundaries.append(Boundary(round(start, 3), round(length, 3), text_))

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
