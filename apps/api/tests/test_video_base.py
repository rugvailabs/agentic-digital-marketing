"""The video and TTS briefs: timing arithmetic and the props contract.

The renderer is a separate process in a different language, so `as_props()` is
the entire interface between them. A silently renamed key here is a blank reel
there, which is why the shape is pinned rather than inspected by eye.
"""

from __future__ import annotations

import pytest

from app.models import Language
from app.storage import content_type_for, public_url
from app.tts import DEFAULT_VOICE, VOICES, voice_for
from app.video import FPS, SIZES, Beat, VideoBrief


def brief(**kwargs) -> VideoBrief:
    defaults = {
        "headline": "Rafale Marine begins flight trials in Goa",
        "beats": [Beat("Trials have begun", 3.0), Beat("Off the Goa coast", 2.5)],
        "brand_name": "Demo",
        "primary_color": "#1B2230",
        "secondary_color": "#D8322B",
    }
    return VideoBrief(**{**defaults, **kwargs})


class TestBeat:
    def test_seconds_become_whole_frames(self) -> None:
        assert Beat("x", 2.0).frames == 60
        assert Beat("x", 2.5).frames == 75

    def test_a_beat_always_holds_at_least_one_frame(self) -> None:
        """A zero-length beat would make Remotion render nothing at all."""
        assert Beat("x", 0.0).frames == 1

    def test_a_beat_serialises_frames_not_seconds(self) -> None:
        """Remotion counts frames; seconds there would be re-derived and drift."""
        assert Beat("Trials begin", 2.0, detail="Goa").as_dict() == {
            "text": "Trials begin",
            "detail": "Goa",
            "frames": 60,
        }


class TestVideoBrief:
    def test_duration_is_the_sum_of_its_beats(self) -> None:
        assert brief().duration_in_frames == 90 + 75
        assert brief().duration_seconds == pytest.approx(5.5)

    def test_a_brief_with_no_beats_still_lasts_a_second(self) -> None:
        """Zero frames is a render error rather than an empty video."""
        assert brief(beats=[]).duration_in_frames == FPS

    def test_reel_is_nine_by_sixteen_and_square_is_one_by_one(self) -> None:
        assert brief(size="reel").dimensions == (1080, 1920)
        assert brief(size="square").dimensions == (1080, 1080)

    def test_an_unknown_size_falls_back_to_reel(self) -> None:
        assert brief(size="letterbox").dimensions == SIZES["reel"]

    def test_props_carry_everything_the_composition_reads(self) -> None:
        """The other half of this list is REQUIRED_PROP_KEYS in
        packages/remotion/src/props.ts, and the renderer refuses a payload
        missing any of them. Change one, change both."""
        props = brief(region_name="Goa", velocity=[1.0, 2.0], script="DEVANAGARI").as_props()

        assert set(props) == {
            "headline",
            "beats",
            "brandName",
            "primaryColor",
            "secondaryColor",
            "logoUrl",
            "regionName",
            "hashtags",
            "velocity",
            "script",
            "width",
            "height",
            "fps",
            "durationInFrames",
        }

    def test_props_state_the_geometry_the_renderer_must_use(self) -> None:
        props = brief(size="reel").as_props()

        assert (props["width"], props["height"]) == (1080, 1920)
        assert props["fps"] == FPS
        assert props["durationInFrames"] == 165

    def test_props_are_json_serialisable(self) -> None:
        """They are handed to another process as --props; anything exotic in
        here surfaces as an unreadable CLI error."""
        import json

        assert json.loads(json.dumps(brief().as_props()))["brandName"] == "Demo"


class TestVoices:
    def test_every_language_we_write_in_can_be_narrated(self) -> None:
        assert set(VOICES) == set(Language)

    def test_every_voice_is_an_indian_locale(self) -> None:
        """A US English voice reading Indian place names is the giveaway that
        nobody listened to the output."""
        assert all(voice.split("-")[1] == "IN" for voice in VOICES.values())

    def test_hinglish_is_read_by_the_indian_english_voice(self) -> None:
        """It is written in Latin script, which the Hindi voice spells out."""
        assert voice_for(Language.hinglish) == voice_for(Language.english)

    def test_a_language_string_resolves_too(self) -> None:
        assert voice_for("tamil") == VOICES[Language.tamil]

    def test_an_unknown_language_falls_back_rather_than_raising(self) -> None:
        assert voice_for("klingon") == DEFAULT_VOICE


class TestStorageTypes:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("jobs/1/square-poster.png", "image/png"),
            ("jobs/1/reel-wire.mp4", "video/mp4"),
            ("jobs/1/voice.mp3", "audio/mpeg"),
            ("jobs/1/voice.wav", "audio/wav"),
            ("jobs/1/mystery", "application/octet-stream"),
        ],
    )
    def test_the_extension_decides_the_content_type(self, key: str, expected: str) -> None:
        """Served straight to a browser: an mp4 as octet-stream downloads
        instead of playing in the Desk."""
        assert content_type_for(key) == expected

    def test_the_url_is_the_browser_reachable_one(self) -> None:
        """Not the in-container endpoint, which does not resolve in a tab."""
        url = public_url("jobs/1/reel-wire.mp4")

        assert url.endswith("/jobs/1/reel-wire.mp4")
        assert "minio:9000" not in url
