"""Writer and renderer. Gemini mocked; Pillow runs for real."""

from __future__ import annotations

import io
import json

import httpx
import pytest
import respx
from PIL import Image, ImageDraw

from app.images import ImageBrief, PillowTemplateProvider, load_font, shaping_available
from app.images.fonts import font_file, missing_fonts, script_of
from app.images.gemini_image import GeminiImageProvider
from app.images.pillow import (
    SUPERSAMPLE,
    TEMPLATE_LABELS,
    TEMPLATES,
    contrasting_ink,
    hashtag_line,
)
from app.llm import GeminiProvider
from app.tasks.content import (
    WRITE_SCHEMA,
    Post,
    _clean_token,
    _strip_hashtags,
    write_post,
)

GENERATE = respx.patterns.M(url__regex=r".*:generateContent")
KEY = "test-key"

WRITER_OUTPUT = {
    "hook": "Goa looks beyond tourism to AI",
    "caption": "The state has published its AI Policy 2026 and opened a hackathon.",
    "hashtags": ["#GoaAIPolicy", "#TechHub"],
    "image_headline": "Goa AI Policy 2026",
    "image_subline": "Hackathon opens next month",
    "display_token": "2026",
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
            display_token=kw.pop("display_token", "2026"),
            velocity=kw.pop("velocity", [0.0, 0.0, 12.0, 40.0, 88.0, 100.0]),
            region_name=kw.pop("region_name", "Goa"),
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

    def test_the_three_templates_are_visually_distinct(self) -> None:
        """Three names for one layout would be worse than one template."""
        renders = {
            t: PillowTemplateProvider().render(self.brief(template=t)).png for t in TEMPLATES
        }

        assert len(set(renders.values())) == len(TEMPLATES)

    def test_each_template_carries_a_full_label(self) -> None:
        # The Desk shows these; "Bold typ…" told a user nothing.
        for template in TEMPLATES:
            image = PillowTemplateProvider().render(self.brief(template=template))
            assert image.meta["label"] == TEMPLATE_LABELS[template]
            assert "…" not in image.meta["label"], "labels are words, not truncated slugs"

    @pytest.mark.parametrize("template", TEMPLATES)
    @pytest.mark.parametrize(
        ("language", "headline", "subline", "token"),
        [
            ("english", "Goa unveils AI policy 2026", "Hackathon opens next month", "2026"),
            ("hindi", "सोने का भाव आज चढ़ा", "निवेशकों की नज़र बाज़ार पर टिकी", "₹1.2L"),
            ("tamil", "கோவா செயற்கை நுண்ணறிவு கொள்கை", "புதிய அறிவிப்பு வெளியானது", "மழை"),
        ],
    )
    def test_no_text_crosses_the_safe_margin(
        self, template: str, language: str, headline: str, subline: str, token: str
    ) -> None:
        """Visual regression across every template and script we support.

        The same brief is rendered twice, once with text and once without, and
        the 4% edge strips must be pixel-identical. Comparing against a
        text-free render rather than counting colours is what lets this work
        on full-bleed templates, where the edge legitimately carries a colour
        block boundary of its own.

        Autofit has to cope with unbreakable Tamil words, Devanagari advance
        widths and a token set at poster scale, and the check is on pixels
        rather than on the measurements the layout code itself used.
        """
        with_text = self.brief(
            headline=headline,
            subline=subline,
            display_token=token,
            template=template,
            hashtags=["#GoaAIPolicy", "#TechHub", "#AIInGoa"],
        )
        without_text = self.brief(
            headline="",
            subline="",
            display_token="",
            template=template,
            hashtags=[],
            region_name="",
        )
        without_text.brand_name = ""

        inked = Image.open(io.BytesIO(PillowTemplateProvider().render(with_text).png)).convert(
            "RGB"
        )
        blank = Image.open(
            io.BytesIO(PillowTemplateProvider().render(without_text).png)
        ).convert("RGB")
        safe = int(inked.width * 0.04)

        for y in range(0, inked.height, 3):
            for x in (*range(safe), *range(inked.width - safe, inked.width)):
                assert inked.getpixel((x, y)) == blank.getpixel((x, y)), (
                    f"{language}/{template}: ink at ({x}, {y}), inside the {safe}px margin"
                )

        for x in range(0, inked.width, 3):
            for y in (*range(safe), *range(inked.height - safe, inked.height)):
                assert inked.getpixel((x, y)) == blank.getpixel((x, y)), (
                    f"{language}/{template}: ink at ({x}, {y}), inside the {safe}px margin"
                )

    def test_the_canvas_is_supersampled_then_downscaled(self) -> None:
        # 1x leaves 14px hashtags and Tamil conjuncts visibly soft.
        assert SUPERSAMPLE >= 2

    def test_an_unknown_template_falls_back_rather_than_failing(self) -> None:
        image = PillowTemplateProvider().render(self.brief(template="does-not-exist"))

        assert image.template == TEMPLATES[0]

    def test_wire_without_a_velocity_series_still_renders(self) -> None:
        # News-only topics have no series; the sparkline is simply absent.
        image = PillowTemplateProvider().render(self.brief(template="wire", velocity=[]))

        assert Image.open(io.BytesIO(image.png)).size == (1080, 1080)

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
        assert contrasting_ink(background) == expected


class TestHashtagLine:
    """The footer line must never overlap the brand name beside it."""

    def line(self, tags: list[str], width: int) -> str:
        canvas = Image.new("RGB", (1200, 100))
        draw = ImageDraw.Draw(canvas)
        font = load_font("#x", 28, "SemiBold")
        return hashtag_line(draw, tags, font, width)

    def test_at_most_three_tags(self) -> None:
        result = self.line([f"#Tag{i}" for i in range(8)], 1200)

        assert result.count("#") == 3

    def test_tags_that_do_not_fit_are_left_out(self) -> None:
        result = self.line(["#Short", "#AVeryMuchLongerHashtag"], 150)

        assert "#AVeryMuchLongerHashtag" not in result

    def test_a_single_oversized_tag_is_ellipsised_not_clipped(self) -> None:
        result = self.line(["#AnExtremelyLongHashtagIndeed"], 120)

        assert result.endswith("…")
        assert len(result) < len("#AnExtremelyLongHashtagIndeed")

    def test_no_tags_is_an_empty_line_not_a_stray_hash(self) -> None:
        assert self.line([], 500) == ""


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
        "display_token",
        "alt_text",
    }


class TestDisplayToken:
    """The Split template sets this at roughly 200px, so length is a hard rule."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026", "2026"),
            ("₹1.2L", "₹1.2L"),
            ("ENG 212/4", "ENG 212/4"),
            ("மழை", "மழை"),
            ("  AI  ", "AI"),
        ],
    )
    def test_short_tokens_pass_through(self, raw: str, expected: str) -> None:
        assert _clean_token(raw, "some topic") == expected

    def test_a_sentence_falls_back_to_a_word_rather_than_truncating(self) -> None:
        # Truncation would put a fragment on a poster at 200px.
        assert _clean_token("Goa unveils its AI policy for 2026", "topic") == "Goa"

    def test_an_empty_token_falls_back_to_the_topic(self) -> None:
        assert _clean_token("", "Weather forecast") == "Weather"

    def test_a_token_with_no_short_word_anywhere_is_empty(self) -> None:
        assert _clean_token("Supercalifragilistic", "Supercalifragilistic") == ""

    @respx.mock
    async def test_the_writer_returns_a_token(self, client) -> None:
        payload = {**WRITER_OUTPUT, "display_token": "2026"}
        respx.route(GENERATE).mock(return_value=httpx.Response(200, json=envelope(payload)))

        post = await write_post(GeminiProvider(client=client, api_key=KEY, model="m"), BRIEF)

        assert post.display_token == "2026"
        assert post.as_dict()["display_token"] == "2026"
