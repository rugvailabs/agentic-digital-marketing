"""Thin wrappers around ffmpeg and ffprobe.

Everything that shells out lives here, so the mixing code reads as a filter
graph rather than as subprocess plumbing, and so there is one place that
decides what an ffmpeg failure looks like.

ffmpeg writes its real diagnostics to stderr and exits non-zero, but the
useful line is usually the last one — the rest is build configuration. A
failure here ends up on a job row and then in front of a marketer, so the
message is trimmed to the part that says what went wrong.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("video.ffmpeg")

#: Long enough for a 45-second reel on a slow laptop, short enough that a
#: hung process does not hold the worker for the whole task time limit.
DEFAULT_TIMEOUT = 300.0


class FFmpegError(RuntimeError):
    """A failure worth showing the user verbatim."""


@dataclass(slots=True)
class AudioStream:
    codec: str
    channels: int
    sample_rate: int
    duration_seconds: float


async def _run(
    binary: str,
    args: list[str],
    # Each operation has its own budget — a probe is seconds, a mix is
    # minutes — and wait_for below is what enforces it.
    timeout: float,  # noqa: ASYNC109
) -> tuple[bytes, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(
            f"{binary} is not installed in this image, so audio cannot be processed."
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise FFmpegError(f"{binary} did not finish within {timeout:.0f}s.") from None

    if process.returncode != 0:
        raise FFmpegError(f"{binary} failed: {_tail(stderr)}")
    return stdout, stderr


def _tail(stderr: bytes, lines: int = 3) -> str:
    """The last few lines of ffmpeg's output.

    ffmpeg prints its whole build configuration before saying anything useful,
    so the head of stderr is noise and the tail is the error.
    """
    text = stderr.decode("utf-8", "replace").strip()
    if not text:
        return "no output"
    return " / ".join(text.splitlines()[-lines:])[:400]


async def run_ffmpeg(
    args: list[str],
    timeout: float = DEFAULT_TIMEOUT,  # noqa: ASYNC109 - see _run
) -> None:
    """Run ffmpeg with `-nostdin -y` and the quiet log level already set."""
    await _run(
        settings.ffmpeg_path,
        ["-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
        timeout,
    )


async def probe(
    path: Path | str,
    timeout: float = 30.0,  # noqa: ASYNC109 - see _run
) -> dict[str, Any]:
    """ffprobe's JSON for one file."""
    stdout, _ = await _run(
        settings.ffprobe_path,
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout,
    )
    try:
        data = json.loads(stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe returned something that is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FFmpegError("ffprobe returned something that is not an object")
    return data


async def duration_seconds(path: Path | str) -> float:
    """How long a file actually is.

    Measured rather than estimated. A voiceover's length is what decides how
    many frames the reel is rendered for, and the obvious estimate — the last
    word-boundary event edge-tts reports — stops at the last syllable and
    ignores the trailing silence the encoder leaves, which is enough drift to
    land a cut on a half-spoken word.
    """
    data = await probe(path)
    raw = (data.get("format") or {}).get("duration")
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        raise FFmpegError(f"ffprobe reported no duration for {Path(path).name}") from None
    if value <= 0:
        raise FFmpegError(f"{Path(path).name} has no length")
    return value


async def audio_stream(path: Path | str) -> AudioStream | None:
    """The first audio stream, or None if the file is silent.

    This is the check that a reel which is supposed to have a voiceover
    actually has one. A muxed file with no audio stream plays fine and is
    silent, so nothing short of asking catches it.
    """
    data = await probe(path)
    for stream in data.get("streams") or []:
        if stream.get("codec_type") != "audio":
            continue
        return AudioStream(
            codec=str(stream.get("codec_name") or "unknown"),
            channels=int(stream.get("channels") or 0),
            sample_rate=int(stream.get("sample_rate") or 0),
            duration_seconds=float(stream.get("duration") or 0.0),
        )
    return None


async def ffmpeg_available() -> bool:
    """Whether both binaries are present. Used by is_configured()."""
    for binary in (settings.ffmpeg_path, settings.ffprobe_path):
        try:
            await _run(binary, ["-version"], timeout=10.0)
        except FFmpegError:
            log.warning("ffmpeg binary missing", binary=binary)
            return False
    return True
