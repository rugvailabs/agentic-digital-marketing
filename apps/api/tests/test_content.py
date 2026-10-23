"""Writer and renderer. Gemini mocked; Pillow runs for real."""

from __future__ import annotations

import io
import json

import httpx
import pytest
import respx
from PIL import Image

from app.images import ImageBrief, PillowTemplateProvider, shaping_available
from app.images.fonts import font_file, missing_fonts, script_of
from app.images.gemini_image import GeminiImageProvider
from app.images.pillow import TEMPLATES, _contrasting_ink
from app.llm import GeminiProvider
from app.tasks.content import WRITE_SCHEMA, Post, _strip_hashtags, write_post

GENERATE = respx.patterns.M(url__regex=r".*:generateContent")
KEY = "test-key"

WRITER_OUTPUT = {
    "hook": "Goa looks beyond tourism to AI",
    "caption": "The state has published its AI Policy 2026 and opened a hackathon.",
    "hashtags": ["#GoaAIPolicy", "#TechHub"],
    "image_headline": "Goa AI Policy 2026",
    "image_subline": "Hackathon opens next month",
    "alt_text": "A graphic announcing Goa's AI policy.",
}


def envelope(payload: dict) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        "usageMetadata": {"totalTokenCount": 900},
    }


BRIEF = {
    "brand_name": "TrendForge demo",
    "brand_voice": "Plain and confident.",
    "topic": "Goa unveils AI policy 2026",
    "summary": "Goa published an AI policy.",
    "known_hashtags": "#GoaAIPolicy",
    "evidence": "- [google_news] Goa unveils AI policy",
    "language": "english",
}


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


class TestWriter:
    @respx.mock
    async def test_a_recorded_response_becomes_a_post(self, client) -> None:
        respx.route(GENERATE).mock(return_value=httpx.Response(200, json=envelope(WRITER_OUTPUT)))

        post = await write_post(GeminiProvider(client=client, api_key=KEY, model="m"), BRIEF)

        assert post.hook == WRITER_OUTPUT["hook"]
        assert post.image_headline == "Goa AI Policy 2026"
        assert post.hashtags == ["#GoaAIPolicy", "#TechHub"]
        assert post.alt_text

    @respx.mock
    async def test_hashtags_returned_as_one_joined_string_are_split(self, client) -> None:
        # Observed live: the writer returned all eight tags as a single string.
        payload = {**WRITER_OUTPUT, "hashtags": ["#GoaAIPolicy','#TechHub','#AIInGoa"]}
        respx.route(GENERATE).mock(return_value=httpx.Response(200, json=envelope(payload)))

        post = await write_post(GeminiProvider(client=client, api_key=KEY, model="m"), BRIEF)

        assert post.hashtags == ["#GoaAIPolicy", "#TechHub", "#AIInGoa"]

    @respx.mock
    async def test_the_prompt_carries_language_brand_and_evidence(self, client) -> None:
        route = respx.route(GENERATE).mock(
            return_value=httpx.Response(200, json=envelope(WRITER_OUTPUT))
        )

        await write_post(
            GeminiProvider(client=client, api_key=KEY, model="m"), {**BRIEF, "language": "tamil"}
        )

        sent = json.loads(route.calls[0].request.read())
        prompt = sent["contents"][0]["parts"][0]["text"]
        assert "**tamil**" in prompt
        assert "TrendForge demo" in prompt
        assert "Goa unveils AI policy" in prompt
        assert sent["generationConfig"]["responseSchema"] == WRITE_SCHEMA

    @respx.mock
    async def test_an_empty_caption_is_an_error_not_an_empty_post(self, client) -> None:
        respx.route(GENERATE).mock(
            return_value=httpx.Response(200, json=envelope({**WRITER_OUTPUT, "caption": "   "}))
        )

        with pytest.raises(Exception, match="empty caption"):
            await write_post(GeminiProvider(client=client, api_key=KEY, model="m"), BRIEF)

    async def test_an_unconfigured_provider_says_so(self, client) -> None:
        with pytest.raises(Exception, match="not configured"):
            await write_post(GeminiProvider(client=client, api_key=""), BRIEF)

    def test_hashtags_inlined_in_the_caption_are_stripped(self) -> None:
        # They are a separate field; leaving them doubles them in the Desk.
        assert _strip_hashtags("Goa opens up. #GoaAIPolicy #TechHub") == "Goa opens up."
        assert _strip_hashtags("No tags here") == "No tags here"


class TestFonts:
    def test_every_script_claude_md_requires_is_bundled(self) -> None:
        assert missing_fonts() == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Goa AI policy", "NotoSans.ttf"),
            ("सोने का भाव", "NotoSansDevanagari.ttf"),
            ("கோவா", "NotoSansTamil.ttf"),
            ("సోనా", "NotoSansTelugu.ttf"),
            ("সোনা", "NotoSansBengali.ttf"),
        ],
    )
    def test_the_script_picks_the_face(self, text: str, expected: str) -> None:
        assert font_file(text).name == expected

    def test_a_latin_brand_name_inside_indic_text_does_not_change_the_script(self) -> None:
        assert script_of("TrendForge का भाव") == "DEVANAGARI"

    def test_complex_shaping_is_available(self) -> None:
        # Without libraqm, Devanagari renders with detached vowel signs.
        assert shaping_available() is True


class TestPillowTemplates:
    def brief(self, **kw) -> ImageBrief:
        return ImageBrief(
            headline=kw.pop("headline", "Goa AI Policy 2026"),
            subline=kw.pop("subline", "Hackathon opens next month"),
            hashtags=kw.pop("hashtags", ["#GoaAIPolicy", "#TechHub"]),
            brand_name="TrendForge demo",
            primary_color="#1B2230",
            secondary_color="#D8322B",
            alt_text="alt",
            **kw,
        )

    @pytest.mark.parametrize("template", TEMPLATES)
    @pytest.mark.parametrize(
        ("size", "dims"), [("square", (1080, 1080)), ("portrait", (1080, 1350))]
    )
    def test_every_template_renders_at_both_sizes(self, template, size, dims) -> None:
        image = PillowTemplateProvider().render(self.brief(size=size, template=template))

        assert (image.width, image.height) == dims
        assert Image.open(io.BytesIO(image.png)).size == dims
        assert image.template == template

    @pytest.mark.parametrize(
        "headline",
        [
            "सोने का भाव आज चढ़ा",
            "கோவா செயற்கை நுண்ணறிவு",
            "সোনার দাম বাড়ল আজ",
            "A very long English headline that has to wrap onto several lines",
            "Supercalifragilisticexpialidocious",
        ],
    )
    def test_text_never_overflows_the_margin(self, headline: str) -> None:
        """Autofit has to cope with unbreakable words and Indic advance widths."""
        image = PillowTemplateProvider().render(self.brief(headline=headline))
        canvas = Image.open(io.BytesIO(image.png)).convert("RGB")

        # The 4%-wide strip down each edge must stay the background colour.
        edge = int(canvas.width * 0.04)
        background = canvas.getpixel((2, 2))
        for y in range(0, canvas.height, 7):
            assert canvas.getpixel((canvas.width - 2, y)) == background
            assert canvas.getpixel((edge // 2, y)) == background

    def test_an_unknown_template_falls_back_rather_than_failing(self) -> None:
        image = PillowTemplateProvider().render(self.brief(template="does-not-exist"))

        assert image.template == TEMPLATES[0]

    def test_the_provider_needs_no_configuration(self) -> None:
        assert PillowTemplateProvider().is_configured() is True

    @pytest.mark.parametrize(
        ("background", "expected"),
        [
            ("#1B2230", "#FFFFFF"),
            ("#EEF1F6", "#1B2230"),
            ("#D8322B", "#FFFFFF"),
            ("zzz", "#FFFFFF"),
        ],
    )
    def test_text_colour_follows_luminance(self, background: str, expected: str) -> None:
        assert _contrasting_ink(background) == expected


class TestGeminiImageProvider:
    def test_it_stays_off_without_a_model_id(self) -> None:
        # The tier answers 429 on every image model, so this is the shipped state.
        assert GeminiImageProvider(api_key=KEY, model="").is_configured() is False
        assert GeminiImageProvider(api_key="", model="some-model").is_configured() is False
        assert GeminiImageProvider(api_key=KEY, model="some-model").is_configured() is True

    def test_an_unconfigured_provider_refuses_rather_than_calling(self) -> None:
        with pytest.raises(RuntimeError, match="not configured"):
            GeminiImageProvider(api_key=KEY, model="").render(
                ImageBrief(
                    headline="x",
                    subline="y",
                    hashtags=[],
                    brand_name="b",
                    primary_color="#000000",
                    secondary_color="#ffffff",
                )
            )

    def test_the_background_prompt_forbids_text(self) -> None:
        """Model-drawn letterforms are wrong, Indic especially, and Pillow
        draws the headline on top anyway."""
        prompt = GeminiImageProvider(api_key=KEY, model="m").background_prompt(
            ImageBrief(
                headline="Goa AI Policy",
                subline="s",
                hashtags=[],
                brand_name="b",
                primary_color="#1B2230",
                secondary_color="#D8322B",
            )
        )

        assert "No text" in prompt
        assert "no letters" in prompt
        assert "#1B2230" in prompt


def test_post_round_trips_through_its_dict_form() -> None:
    post = Post(
        hook="h",
        caption="c",
        hashtags=["#a"],
        image_headline="ih",
        image_subline="is",
        alt_text="alt",
    )

    assert post.as_dict()["hashtags"] == ["#a"]
    assert set(post.as_dict()) == {
        "hook",
        "caption",
        "hashtags",
        "image_headline",
        "image_subline",
        "alt_text",
    }
