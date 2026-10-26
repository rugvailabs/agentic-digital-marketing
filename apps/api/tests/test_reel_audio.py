"""The mix, against a real ffmpeg.

Mocking ffmpeg here would test the argument list and nothing else, and the
thing worth testing is whether the file that comes out has audio in it. A
muxed mp4 with no audio stream plays perfectly well and is silent — so these
build a real video and real tones, mix them, and ask ffprobe.

Skipped automatically where ffmpeg is not installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.models import Language
from app.tts.base import Speech
from app.video.base import FPS
from app.video.ffmpeg import (
    FFmpegError,
    audio_stream,
    duration_seconds,
    ffmpeg_available,
    run_ffmpeg,
)
from app.video.mux import mux
from app.video.script import ReelScript, Segment
from app.video.timing import narrate
from tests.test_reel_timing import FakeTTS


@pytest.fixture(scope="module", autouse=True)
async def _needs_ffmpeg():
    if not await ffmpeg_available():
        pytest.skip("ffmpeg is not installed")


async def silent_video(path: Path, seconds: float) -> None:
    """A real h264 file of the right length, with no audio."""
    await run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0xEEF1F6:s=270x480:r={FPS}:d={seconds:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


async def tone(path: Path, seconds: float, hz: int = 440) -> bytes:
    """A real mp3 of a known length, standing in for a narrated line."""
    await run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={hz}:duration={seconds:.3f}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "96k",
            str(path),
        ]
    )
    return path.read_bytes()  # noqa: ASYNC240 - a test fixture, not the event loop


async def narration_of(work: Path, lengths: list[float]):
    """A Narration whose cards carry real audio of the given lengths."""
    segments = [Segment(kind="title", say="Opening line.")]
    segments += [
        Segment(kind="beat", text=f"Beat {i}", say=f"Line {i}.") for i in range(1, len(lengths) - 1)
    ]
    segments.append(Segment(kind="outro", say="Closing line."))

    narration = await narrate(FakeTTS(lengths), ReelScript("Headline", segments), Language.english)
    for index, card in enumerate(narration.cards):
        audio = await tone(work / f"t{index}.mp3", lengths[index], hz=330 + index * 110)
        card.speech = Speech(
            audio=audio,
            format="mp3",
            duration_seconds=card.speech.duration_seconds,
            voice=card.speech.voice,
        )
    return narration


class TestMux:
    async def test_the_result_actually_has_an_audio_stream(self) -> None:
        """The check this whole module exists for."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 2.0, 1.5])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)

            mixed = await mux(video.read_bytes(), narration)

            assert mixed.audio_codec == "aac"
            assert mixed.audio_channels == 2
            assert mixed.mp4[:12]

    async def test_ffprobe_agrees_once_it_is_written_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 2.0, 1.5])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)

            mixed = await mux(video.read_bytes(), narration)
            out = work / "out.mp4"
            out.write_bytes(mixed.mp4)

            stream = await audio_stream(out)
            assert stream is not None
            assert stream.sample_rate == 48_000

    async def test_the_audio_is_as_long_as_the_picture(self) -> None:
        """Out by a second here is the voice finishing after the last frame."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 2.0, 1.5])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)

            mixed = await mux(video.read_bytes(), narration)
            out = work / "out.mp4"
            out.write_bytes(mixed.mp4)

            assert await duration_seconds(out) == pytest.approx(
                narration.duration_seconds, abs=0.25
            )

    async def test_the_lines_are_padded_out_to_their_cards(self) -> None:
        """Each line starts when its card does, not back to back."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            # Very different lengths, so back-to-back concatenation would be
            # obviously shorter than the timeline.
            narration = await narration_of(work, [0.5, 4.0, 0.5])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)

            mixed = await mux(video.read_bytes(), narration)

            spoken = sum(c.speech.duration_seconds for c in narration.cards)
            assert mixed.duration_seconds > spoken + 0.5
            assert mixed.duration_seconds == pytest.approx(narration.duration_seconds, abs=0.25)

    async def test_the_video_stream_is_not_re_encoded(self) -> None:
        """The render is the expensive part; copying keeps it untouched."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 1.0, 1.0])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)
            before = video.read_bytes()

            mixed = await mux(before, narration)
            out = work / "out.mp4"
            out.write_bytes(mixed.mp4)

            from app.video.ffmpeg import probe

            streams = (await probe(out)).get("streams") or []
            video_stream = next(s for s in streams if s.get("codec_type") == "video")
            assert video_stream.get("codec_name") == "h264"

    async def test_a_music_bed_does_not_replace_the_voice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 2.0, 1.0])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)
            bed = work / "bed.mp3"
            await tone(bed, 2.0, hz=180)

            mixed = await mux(video.read_bytes(), narration, bed=bed)

            assert mixed.has_music is True
            assert mixed.audio_codec == "aac"
            # Looped to the full length rather than stopping after two seconds.
            assert mixed.duration_seconds == pytest.approx(narration.duration_seconds, abs=0.25)

    async def test_a_poster_frame_comes_back_with_the_reel(self) -> None:
        """Frame zero is a blank sheet of paper — the opening card is still
        settling — so a player with no poster looks like a failed render."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 2.0, 1.5])
            video = work / "silent.mp4"
            await silent_video(video, narration.duration_seconds)

            mixed = await mux(video.read_bytes(), narration)

            assert mixed.poster
            # JPEG magic, so this is an image and not an ffmpeg error page.
            assert mixed.poster.startswith(bytes([0xFF, 0xD8]))

    async def test_nothing_to_narrate_is_a_failure_not_a_silent_reel(self) -> None:
        from app.video.timing import Narration

        with pytest.raises(FFmpegError, match="no narration"):
            await mux(b"not a video", Narration(cards=[], voice=""))

    async def test_a_broken_video_fails_with_ffmpegs_own_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            narration = await narration_of(work, [1.0, 1.0, 1.0])

            with pytest.raises(FFmpegError) as caught:
                await mux(b"this is not an mp4", narration)

            assert "ffmpeg failed" in str(caught.value)


class TestProbe:
    async def test_a_silent_video_reports_no_audio_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silent.mp4"
            await silent_video(path, 1.0)

            assert await audio_stream(path) is None

    async def test_duration_is_measured_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tone.mp3"
            await tone(path, 2.5)

            assert await duration_seconds(path) == pytest.approx(2.5, abs=0.15)

    async def test_a_missing_file_says_so(self) -> None:
        with pytest.raises(FFmpegError, match="ffprobe failed"):
            await duration_seconds("/tmp/does-not-exist.mp4")
