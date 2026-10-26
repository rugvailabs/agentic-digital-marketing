"""The Remotion adapter, with the renderer mocked.

Every failure here lands on a job row and then in front of a marketer, so the
tests are mostly about what the message says. "The renderer failed: 500" is
not something anyone can act on; "Could not reach the renderer at
http://renderer:3100. Is it running?" is.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.video import Beat, VideoBrief
from app.video.remotion import RemotionVideoProvider, VideoError

BASE = "http://renderer.test:3100"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def brief(size: str = "reel") -> VideoBrief:
    return VideoBrief(
        headline="Rafale Marine begins flight trials in Goa",
        beats=[Beat("Trials have begun", 3.0), Beat("Off the Goa coast", 2.0)],
        brand_name="Demo",
        primary_color="#1B2230",
        secondary_color="#D8322B",
        size=size,
        region_name="Goa",
    )


def provider() -> RemotionVideoProvider:
    return RemotionVideoProvider(base_url=BASE, timeout=5.0)


class TestConfiguration:
    def test_a_url_is_all_it_takes_to_be_configured(self) -> None:
        """Same meaning as the Gemini adapters: a key present does not promise
        the call works, it promises there is somewhere to send it."""
        assert provider().is_configured() is True

    def test_no_url_is_not_configured(self) -> None:
        assert RemotionVideoProvider(base_url="").is_configured() is False

    def test_a_trailing_slash_does_not_double_up(self) -> None:
        assert RemotionVideoProvider(base_url=f"{BASE}/").base_url == BASE

    async def test_rendering_without_a_renderer_says_so(self) -> None:
        with pytest.raises(VideoError, match="No renderer is configured"):
            await RemotionVideoProvider(base_url="").render(brief())


class TestRender:
    @respx.mock
    async def test_a_reel_comes_back_with_its_geometry(self) -> None:
        route = respx.post(f"{BASE}/render").mock(
            return_value=httpx.Response(
                200,
                content=MP4,
                headers={
                    "content-type": "video/mp4",
                    "x-duration-frames": "150",
                    "x-width": "1080",
                    "x-height": "1920",
                    "x-fps": "30",
                },
            )
        )

        video = await provider().render(brief())

        assert route.called
        assert video.mp4 == MP4
        assert (video.width, video.height) == (1080, 1920)
        assert video.duration_seconds == pytest.approx(5.0)
        # Muted on purpose: ffmpeg mixes the voice and the bed in later.
        assert video.has_audio is False

    @respx.mock
    async def test_the_size_picks_the_composition(self) -> None:
        route = respx.post(f"{BASE}/render").mock(return_value=httpx.Response(200, content=MP4))

        await provider().render(brief(size="square"))

        assert route.calls.last.request.read()
        import json

        assert json.loads(route.calls.last.request.content)["composition"] == "Square"

    @respx.mock
    async def test_the_props_sent_are_the_brief(self) -> None:
        import json

        route = respx.post(f"{BASE}/render").mock(return_value=httpx.Response(200, content=MP4))

        await provider().render(brief())

        props = json.loads(route.calls.last.request.content)["props"]
        assert props["headline"].startswith("Rafale")
        # 60 opening + 90 + 60 beats + 45 closing.
        assert props["durationInFrames"] == 255
        assert [b["frames"] for b in props["beats"]] == [90, 60]

    async def test_an_unknown_size_is_refused_before_the_call(self) -> None:
        with pytest.raises(VideoError, match="no composition"):
            await provider().render(brief(size="letterbox"))

    @respx.mock
    async def test_headers_are_trusted_over_the_brief(self) -> None:
        """The renderer is the authority on what it actually produced."""
        respx.post(f"{BASE}/render").mock(
            return_value=httpx.Response(
                200, content=MP4, headers={"x-duration-frames": "99", "x-fps": "30"}
            )
        )

        video = await provider().render(brief())

        assert video.duration_seconds == pytest.approx(3.3)

    @respx.mock
    async def test_missing_headers_fall_back_to_the_brief(self) -> None:
        respx.post(f"{BASE}/render").mock(return_value=httpx.Response(200, content=MP4))

        video = await provider().render(brief())

        assert video.duration_seconds == pytest.approx(8.5)


class TestFailuresAreLegible:
    @respx.mock
    async def test_the_renderers_own_message_is_passed_through(self) -> None:
        respx.post(f"{BASE}/render").mock(
            return_value=httpx.Response(500, json={"detail": "font file not found"})
        )

        with pytest.raises(VideoError, match="font file not found"):
            await provider().render(brief())

    @respx.mock
    async def test_a_body_with_no_detail_still_names_the_status(self) -> None:
        respx.post(f"{BASE}/render").mock(return_value=httpx.Response(502, content=b"nginx"))

        with pytest.raises(VideoError, match="HTTP 502"):
            await provider().render(brief())

    @respx.mock
    async def test_an_unreachable_renderer_names_the_address(self) -> None:
        respx.post(f"{BASE}/render").mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(VideoError, match="Is it running"):
            await provider().render(brief())

    @respx.mock
    async def test_a_timeout_suggests_what_to_do_about_it(self) -> None:
        respx.post(f"{BASE}/render").mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(VideoError, match="shorter script"):
            await provider().render(brief())

    @respx.mock
    async def test_an_empty_body_is_a_failure_not_a_zero_byte_reel(self) -> None:
        respx.post(f"{BASE}/render").mock(return_value=httpx.Response(200, content=b""))

        with pytest.raises(VideoError, match="empty video"):
            await provider().render(brief())


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """The cache is module state; without this the first health test decides
    the answer for every later one."""
    import app.video.remotion as remotion

    remotion._health_cache = None
    yield
    remotion._health_cache = None


class TestHealth:
    @respx.mock
    async def test_health_passes_the_service_answer_through(self) -> None:
        respx.get(f"{BASE}/health").mock(
            return_value=httpx.Response(200, json={"ok": True, "bundled": True})
        )

        assert await provider().health() == {"ok": True, "bundled": True}

    @respx.mock
    async def test_an_unreachable_renderer_is_not_ok(self) -> None:
        respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("refused"))

        result = await provider().health()

        assert result["ok"] is False
        assert "ConnectError" in str(result["error"])

    @respx.mock
    async def test_a_non_json_answer_is_not_ok(self) -> None:
        respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, content=b"hello"))

        assert (await provider().health())["ok"] is False

    async def test_health_without_a_url_says_which_setting_is_missing(self) -> None:
        result = await RemotionVideoProvider(base_url="").health()

        assert result["ok"] is False
        assert "RENDERER_URL" in str(result["error"])

    @respx.mock
    async def test_the_answer_is_cached(self) -> None:
        """/health is hit by the compose healthcheck every ten seconds and by
        every board load; asking the renderer each time means one slow service
        can time out the API's own health check."""
        route = respx.get(f"{BASE}/health").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        await provider().health()
        await provider().health()
        await provider().health()

        assert route.call_count == 1
