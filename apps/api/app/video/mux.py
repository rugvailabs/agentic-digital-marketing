"""Put the voice on the picture.

The renderer returns a silent mp4 and the narration arrives as one file per
card. This lays those files out on the timeline — each one padded with
silence to the exact length of the card it belongs to — mixes an optional
music bed under them, and muxes the result against the video.

The video stream is copied, never re-encoded. The render is the expensive
part of this pipeline and there is nothing to gain by passing it through an
encoder a second time.

The output is checked for an audio stream before it is returned. A muxed file
with no audio plays perfectly well and is silent, so nothing short of asking
ffprobe catches it — and a silent reel that was asked for with a voiceover
looks finished, which is the worst way for this to fail.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.video.ffmpeg import FFmpegError, audio_stream, duration_seconds, run_ffmpeg
from app.video.timing import Narration

log = get_logger("video.mux")

#: AAC at this bitrate is transparent for speech and is what every social
#: platform re-encodes from anyway.
AUDIO_BITRATE = "192k"
SAMPLE_RATE = 48_000


#: Where to take the poster from, as a fraction of the reel.
#:
#: Not frame zero. The opening card settles over the first third of a second,
#: so frame zero is a blank sheet of paper — which is exactly what a player
#: shows before anyone presses play, and it looks like a failed render.
POSTER_AT = 0.35


@dataclass(slots=True)
class MuxedVideo:
    mp4: bytes
    duration_seconds: float
    audio_codec: str
    audio_channels: int
    has_music: bool
    #: A still for the player to show before it is played.
    poster: bytes = b""


def _voice_graph(narration: Narration) -> tuple[list[str], str]:
    """Pad each card's narration out to its card, then join them end to end.

    Padding rather than delaying: `adelay` on each line and then mixing works
    too, but it leaves the levels to amix, and a line that overlaps the next
    by a frame is audible. Concatenating padded segments cannot overlap.
    """
    parts: list[str] = []
    labels: list[str] = []
    for index, card in enumerate(narration.cards):
        label = f"s{index}"
        # Input 0 is the video, so the first audio input is 1.
        parts.append(f"[{index + 1}:a]apad=pad_dur={card.gap_seconds:.3f}[{label}]")
        labels.append(f"[{label}]")

    joined = "".join(labels)
    parts.append(f"{joined}concat=n={len(labels)}:v=0:a=1[voice]")
    return parts, "[voice]"


def _bed_graph(bed_input: int, total: float) -> tuple[list[str], str]:
    """Loop the bed to length, drop it under the voice, and duck it.

    Two things keep it out of the way: a flat cut of MUSIC_GAIN_DB, and a
    sidechain compressor keyed on the narration so it steps back further
    whenever anyone is speaking. The gain alone is not enough — a bed that
    sits politely under one sentence will fight the next quieter one.
    """
    fade = max(0.1, min(settings.music_fade_seconds, total / 3))
    out = max(0.0, total - fade)
    parts = [
        f"[{bed_input}:a]aloop=loop=-1:size=2147483647,atrim=0:{total:.3f},"
        f"asetpts=N/SR/TB,volume={settings.music_gain_db:.1f}dB,"
        f"afade=t=in:st=0:d={fade:.2f},afade=t=out:st={out:.3f}:d={fade:.2f}[bed]",
        # The voice is the key, the bed is what gets compressed.
        "[bed][voicekey]sidechaincompress="
        "threshold=0.03:ratio=12:attack=15:release=350:makeup=1[ducked]",
    ]
    return parts, "[ducked]"


async def mux(
    video: bytes,
    narration: Narration,
    *,
    bed: Path | None = None,
) -> MuxedVideo:
    """Combine the silent render with the narration and an optional bed."""
    if not narration.cards:
        raise FFmpegError("There is no narration to put on this reel.")

    with tempfile.TemporaryDirectory(prefix="tf-mux-") as directory:
        work = Path(directory)
        silent = work / "silent.mp4"
        silent.write_bytes(video)

        inputs: list[str] = ["-i", str(silent)]
        for index, card in enumerate(narration.cards):
            path = work / f"card-{index}.{card.speech.format}"
            path.write_bytes(card.speech.audio)
            inputs += ["-i", str(path)]

        parts, voice = _voice_graph(narration)
        total = narration.duration_seconds

        if bed is not None:
            bed_input = len(narration.cards) + 1
            inputs += ["-i", str(bed)]
            # The voice feeds both the mix and the compressor's key input, so
            # it has to be split: a filter output can only be consumed once.
            parts.append(f"{voice}asplit=2[voicemix][voicekey]")
            bed_parts, ducked = _bed_graph(bed_input, total)
            parts += bed_parts
            parts.append(f"{ducked}[voicemix]amix=inputs=2:duration=longest:normalize=0[mix]")
            final = "[mix]"
        else:
            final = voice

        out = work / "reel.mp4"
        await run_ffmpeg(
            [
                *inputs,
                "-filter_complex",
                ";".join(parts),
                "-map",
                "0:v:0",
                "-map",
                final,
                # The render is the expensive part; there is nothing to gain
                # by sending it through an encoder again.
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                AUDIO_BITRATE,
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                "-shortest",
                str(out),
            ]
        )

        stream = await audio_stream(out)
        if stream is None:
            raise FFmpegError(
                "The mix produced a video with no audio track. The narration was not applied."
            )

        mp4 = out.read_bytes()
        seconds = await duration_seconds(out)
        poster = await _poster(out, work, seconds)

    log.info(
        "reel mixed",
        seconds=round(seconds, 2),
        codec=stream.codec,
        channels=stream.channels,
        music=bed.name if bed else None,
        bytes=len(mp4),
    )
    return MuxedVideo(
        mp4=mp4,
        duration_seconds=seconds,
        audio_codec=stream.codec,
        audio_channels=stream.channels,
        has_music=bed is not None,
        poster=poster,
    )


async def _poster(video: Path, work: Path, seconds: float) -> bytes:
    """One frame, for the player to show before it is played.

    Never fatal: a reel without a poster is a reel with a dull first frame,
    and failing the whole job over a thumbnail would be absurd.
    """
    at = max(0.1, seconds * POSTER_AT)
    out = work / "poster.jpg"
    try:
        await run_ffmpeg(
            ["-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(out)],
            timeout=60.0,
        )
        return out.read_bytes()
    except (FFmpegError, OSError) as exc:
        log.warning("no poster frame", error=str(exc)[:200])
        return b""
