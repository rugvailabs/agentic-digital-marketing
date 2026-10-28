"""Writer and renderer. Gemini mocked; Pillow runs for real."""

from __future__ import annotations

import io
import json

import httpx
import pytest
import respx
from PIL import Image, ImageDraw

from app.images import ImageBrief, PillowTemplateProvider, load_font, pillow, shaping_available
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
    async def test_the_curators_tags_are_published_alongside_the_writers(self, client) -> None:
        """The handles that make two posts about one story findable together,
        which the writer has no way to know it should reuse."""
        respx.route(GENERATE).mock(return_value=httpx.Response(200, json=envelope(WRITER_OUTPUT)))

        post = await write_post(
            GeminiProvider(client=client, api_key=KEY, model="m"),
            {**BRIEF, "curator_hashtags": ["#Goa", "#AIPolicy"]},
        )

        assert "#Goa" in post.hashtags
        assert "#AIPolicy" in post.hashtags
        assert "#TechHub" in post.hashtags

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
            ("सोने का भाव", "NotoSansDevanagari.ttf"),
            ("கோவா", "NotoSansTamil.ttf"),
            ("సోనా", "NotoSansTelugu.ttf"),
            ("সোনা", "NotoSansBengali.ttf"),
        ],
    )
    def test_the_script_picks_the_face(self, text: str, expected: str) -> None:
        assert font_file(text).name == expected

    def test_latin_sets_in_the_two_faces_claude_md_names(self) -> None:
        """Not Noto: a post has to look like the desk it came from, and the
        desk is Bricolage over Schibsted."""
        assert font_file("Goa AI policy", "display").name == "BricolageGrotesque.ttf"
        assert font_file("Goa AI policy", "ui").name == "SchibstedGrotesk.ttf"

    def test_an_indic_script_ignores_the_role(self) -> None:
        """Neither Latin face has a Devanagari glyph, so asking for display
        type in Hindi has to still produce readable Hindi."""
        assert font_file("सोने का भाव", "display").name == "NotoSansDevanagari.ttf"
        assert font_file("सोने का भाव", "ui").name == "NotoSansDevanagari.ttf"

    def test_an_unknown_role_falls_back_to_display(self) -> None:
        assert font_file("Goa", "handwriting").name == "BricolageGrotesque.ttf"

    def test_optical_size_tracks_the_drawn_size(self) -> None:
        """The opsz axis is why CLAUDE.md asks for this face. If it stayed at
        its default, a 200px token and 14px body type would share one cut."""
        big = load_font("Goa", 180, "ExtraBold", "display")
        small = load_font("Goa", 14, "ExtraBold", "display")

        axes = [a["name"] for a in big.get_variation_axes()]
        assert any(b"Optical" in a for a in axes if isinstance(a, bytes))
        # Same family, same weight, different cut: the glyphs measure
        # differently per point once opsz moves.
        assert big.getlength("Goa") / 180 != pytest.approx(small.getlength("Goa") / 14, abs=1e-4)

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
        blank = Image.open(io.BytesIO(PillowTemplateProvider().render(without_text).png)).convert(
            "RGB"
        )
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
            # Turmeric. White on it is 2.17:1 and ink is 7.33:1, which the
            # old 0.45 threshold got backwards.
            ("#E3A51D", "#1B2230"),
            ("zzz", "#FFFFFF"),
        ],
    )
    def test_text_colour_follows_luminance(self, background: str, expected: str) -> None:
        assert contrasting_ink(background) == expected

    @pytest.mark.parametrize(
        "background",
        ["#1B2230", "#D8322B", "#EEF1F6", "#E3A51D", "#1E7D5A", "#FFFFFF", "#2B1A12", "#808080"],
    )
    def test_the_chosen_ink_clears_the_contrast_floor(self, background: str) -> None:
        """CLAUDE.md asks for 4.5:1, and this is the function that decides
        whether a post meets it. The threshold is derived to make exactly
        this claim rather than chosen to look about right.

        #808080 is the one colour here that cannot: a mid grey is 4.03:1
        against ink and 3.95:1 against white, so the best available answer
        still fails. Named rather than quietly excluded.
        """
        ink = contrasting_ink(background)
        floor = 4.0 if background == "#808080" else 4.5

        assert _contrast(background, ink) >= floor


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


class TestFooterIsNeverOverrun:
    """Nothing a template draws may reach the footer.

    Caught for real when the Latin face changed to a narrower one: a headline
    that had taken two lines took three, the Split template sized it against
    the whole band below the colour block, and the subline was pushed straight
    through the hashtag line. The templates are autofit, so the only durable
    check is on the pixels.
    """

    LONG_HEADLINE = (
        "Goa unveils AI policy 2026 and launches a state-level hackathon "
        "with a two crore prize pool for student teams"
    )
    LONG_SUBLINE = (
        "Applications open until 30 November, and the winning team gets a "
        "year of incubation at the Porvorim campus alongside the prize."
    )

    def brief(self, template: str, size: str) -> ImageBrief:
        return ImageBrief(
            headline=self.LONG_HEADLINE,
            subline=self.LONG_SUBLINE,
            hashtags=["#GoaAI", "#AIPolicy", "#Hackathon"],
            brand_name="BitnBin",
            primary_color="#1B2230",
            secondary_color="#D8322B",
            display_token="AI hub",
            region_name="Goa",
            velocity=[10.0, 22.0, 18.0, 44.0, 61.0, 90.0],
            template=template,
            size=size,
        )

    @pytest.mark.parametrize("template", TEMPLATES)
    @pytest.mark.parametrize("size", ["square", "portrait"])
    def test_the_gap_above_the_footer_text_stays_clear(self, template: str, size: str) -> None:
        provider = PillowTemplateProvider()
        rendered = provider.render(self.brief(template, size))
        image = Image.open(io.BytesIO(rendered.png)).convert("RGB")
        w, h = image.size

        # The band between the footer rule and the footer text. The rule may
        # live on its top row, so start below it.
        top = PillowTemplateProvider._footer_top(h) + 3
        bottom = PillowTemplateProvider._baseline(h) - 4
        assert bottom > top

        # Sampled against the template's own ground rather than a fixed
        # colour: Poster is full-bleed brand colour and Wire is paper, so
        # "clear" means "the same as the margin beside it".
        ground = image.getpixel((2, (top + bottom) // 2))
        margin = int(w * 0.08)

        intruders = [
            (x, y)
            for y in range(top, bottom)
            for x in range(margin, w - margin, 3)
            if image.getpixel((x, y)) != ground
        ]
        assert not intruders, (
            f"{template}/{size}: {len(intruders)} pixels of content in the "
            f"footer gap, first at {intruders[0]}"
        )


#: A colour no template and no brand in these tests draws, so counting it
#: counts the logo. The first attempt reused the brand's secondary, and the
#: Split template's colour block answered for it.
LOGO_INK = (0, 158, 255)


class TestBrandLogo:
    """The logo slot in the footer.

    Pillow runs for real here, as everywhere else in this file; only the
    storage read is stubbed, because reading an object back from MinIO to
    prove a paste happened is testing MinIO.
    """

    @pytest.fixture
    def logo_png(self) -> bytes:
        """A wide mark with transparent padding around it, which is what an
        exported logo normally looks like."""
        image = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((0, 90, 400, 210), fill=(*LOGO_INK, 255))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    @pytest.fixture
    def stored(self, monkeypatch: pytest.MonkeyPatch, logo_png: bytes):
        """Patched on the module under test, which is the name it resolves."""

        def reader(key: str) -> bytes:
            if key == "brands/1/logo.png":
                return logo_png
            raise KeyError(key)

        monkeypatch.setattr(pillow.storage, "get_bytes", reader)
        return reader

    def brief(self, **kw) -> ImageBrief:
        return ImageBrief(
            headline="India seal the series in Chennai",
            subline="Three wickets in the last over.",
            hashtags=["#INDvAUS", "#Chennai"],
            brand_name="Madras Filter Coffee",
            primary_color="#2B1A12",
            secondary_color="#E3A51D",
            velocity=[10.0, 14.0, 22.0, 30.0, 61.0, 88.0],
            region_name="Tamil Nadu",
            **kw,
        )

    def rendered(self, **kw) -> Image.Image:
        png = PillowTemplateProvider().render(self.brief(**kw)).png
        return Image.open(io.BytesIO(png)).convert("RGB")

    @pytest.mark.parametrize("template", TEMPLATES)
    def test_a_logo_changes_what_is_drawn(self, stored, template: str) -> None:
        with_logo = self.rendered(template=template, logo_key="brands/1/logo.png")
        without = self.rendered(template=template)

        assert list(with_logo.getdata()) != list(without.getdata())

    @pytest.mark.parametrize("template", TEMPLATES)
    @pytest.mark.parametrize("size", ["square", "portrait"])
    def test_it_never_crosses_the_footer_rule(self, stored, template: str, size: str) -> None:
        """The invariant the rest of the footer already keeps. A logo is
        sized from a file nobody here controls, so it is the most likely
        thing in the footer to grow through the rule."""
        image = self.rendered(template=template, size=size, logo_key="brands/1/logo.png")
        w, h = image.size
        provider = PillowTemplateProvider

        # The logo is the only thing drawn in the right third of the footer,
        # so any of its colour above the rule is an overrun.
        above = [
            (x, y)
            for y in range(0, provider._footer_top(h) + 1)
            for x in range(int(w * 0.6), w, 2)
            if _close(image.getpixel((x, y)), LOGO_INK)
        ]

        assert not above, f"{template}/{size}: logo above the footer rule at {above[0]}"

    @pytest.mark.parametrize("size", ["square", "portrait"])
    def test_it_stays_inside_the_right_margin(self, stored, size: str) -> None:
        image = self.rendered(template="wire", size=size, logo_key="brands/1/logo.png")
        w, h = image.size
        margin = int(w * 0.08)

        outside = [
            (x, y)
            for y in range(PillowTemplateProvider._footer_top(h), h)
            for x in range(w - margin + 2, w)
            if _close(image.getpixel((x, y)), LOGO_INK)
        ]

        assert not outside, f"{size}: logo past the margin at {outside[0]}"

    def test_the_wordmark_is_replaced_rather_than_joined(self, stored) -> None:
        """Two marks for one brand in a 30px band is clutter, so the name
        goes when a logo arrives. The footer's right side is the logo's."""
        with_logo = self.rendered(template="wire", logo_key="brands/1/logo.png")
        without = self.rendered(template="wire")
        w, h = with_logo.size
        band = range(PillowTemplateProvider._baseline(h), h - int(h * 0.04))
        right = range(int(w * 0.72), w - int(w * 0.08))

        ink = (27, 34, 48)
        named = sum(1 for y in band for x in right if _close(without.getpixel((x, y)), ink))
        logoed = sum(1 for y in band for x in right if _close(with_logo.getpixel((x, y)), ink))

        assert named > 0, "the wordmark should be there without a logo"
        assert logoed == 0, "the wordmark is still drawn under the logo"

    def test_transparent_padding_is_trimmed(self, stored, monkeypatch) -> None:
        """Otherwise the box is filled by the file rather than by the mark,
        and two brands get different logo sizes for a reason neither chose."""
        padded = Image.new("RGBA", (900, 1200), (0, 0, 0, 0))
        ImageDraw.Draw(padded).rectangle((0, 540, 400, 660), fill=(*LOGO_INK, 255))
        buffer = io.BytesIO()
        padded.save(buffer, "PNG")
        monkeypatch.setattr(pillow.storage, "get_bytes", lambda key: buffer.getvalue())

        image = self.rendered(template="wire", logo_key="brands/1/logo.png")
        w, h = image.size
        drawn = sum(
            1
            for y in range(PillowTemplateProvider._footer_top(h), h)
            for x in range(int(w * 0.6), w)
            if _close(image.getpixel((x, y)), LOGO_INK)
        )

        # Untrimmed, the mark is 10% of a 1200px-tall file scaled into a
        # 59px box — a handful of pixels. Trimmed, it fills the box.
        assert drawn > 1500, f"only {drawn} px of logo: the padding was not trimmed"

    def test_a_missing_object_falls_back_to_the_name(self, stored) -> None:
        """A post that renders without a logo is a much smaller problem than
        a post that does not render."""
        image = self.rendered(template="wire", logo_key="brands/1/gone.png")
        without = self.rendered(template="wire")

        assert list(image.getdata()) == list(without.getdata())

    def test_bytes_that_are_not_an_image_fall_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pillow.storage, "get_bytes", lambda key: b"not a png")

        image = self.rendered(template="wire", logo_key="brands/1/logo.png")
        without = self.rendered(template="wire")

        assert list(image.getdata()) == list(without.getdata())

    def test_a_truncated_png_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, logo_png: bytes
    ) -> None:
        """Image.open is lazy, so a header-only file opens cleanly and
        raises on first pixel access. The guard has to cover the load."""
        monkeypatch.setattr(pillow.storage, "get_bytes", lambda key: logo_png[:120])

        image = self.rendered(template="wire", logo_key="brands/1/logo.png")
        without = self.rendered(template="wire")

        assert list(image.getdata()) == list(without.getdata())

    def test_no_key_does_not_touch_storage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The common case: most briefs have no logo, and none of them
        should cost a storage round trip."""

        def boom(key: str) -> bytes:
            raise AssertionError(f"storage was read for {key}")

        monkeypatch.setattr(pillow.storage, "get_bytes", boom)

        assert self.rendered(template="wire").size == (1080, 1080)


def _close(pixel: tuple[int, int, int], target: tuple[int, int, int], within: int = 18) -> bool:
    """Lanczos downscaling leaves edge pixels between the two colours, so
    every colour check here is a neighbourhood rather than an equality."""
    return all(abs(a - b) <= within for a, b in zip(pixel, target, strict=True))


def _contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, written out here rather than imported.

    `contrasting_ink` computes luminance too, and a test that reuses the
    implementation's own maths to check the implementation proves only that
    it is self-consistent.
    """

    def luminance(hex_color: str) -> float:
        value = hex_color.lstrip("#")
        r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))

        def channel(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)
