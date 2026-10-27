"""Curator v3: why trending, relevance to region, per-platform hashtags.

The relevance floor is the part with teeth — it decides what reaches a state
board — so most of these are about the cases where it must *not* fire.
"""

from __future__ import annotations

import pytest

from app.models import RegionKind, SourceName
from app.prompts import render_prompt
from app.tasks.curate import (
    CURATE_SCHEMA,
    PROMPT_ID,
    RELEVANCE_FLOOR,
    _clean_relevance,
    _one_line,
    keeps_region_relevance,
    platform_hashtags_of,
)


class TestPromptAndSchema:
    def test_the_prompt_is_v3_and_renders(self) -> None:
        assert PROMPT_ID == "curate_v3"

        prompt = render_prompt(
            PROMPT_ID,
            region_name="Tamil Nadu",
            region_code="IN-TN",
            region_kind="state",
            cluster_count=2,
            clusters="### c1\n- [reddit #2] Something happened",
        )

        assert "Tamil Nadu" in prompt
        assert "relevance_to_region" in prompt
        assert "why_trending" in prompt
        assert "platform_hashtags" in prompt

    def test_the_schema_requires_the_new_fields(self) -> None:
        required = CURATE_SCHEMA["items"]["required"]

        assert "why_trending" in required
        assert "relevance_to_region" in required

    def test_platform_hashtags_names_its_platforms_explicitly(self) -> None:
        """Gemini's responseSchema has no additionalProperties, so a map with
        no declared properties comes back empty every time."""
        properties = CURATE_SCHEMA["items"]["properties"]["platform_hashtags"]["properties"]

        assert set(properties) == {"youtube", "reddit", "x", "instagram"}

    def test_the_posting_platforms_are_the_only_ones_asked_for(self) -> None:
        """Nobody posts to Google Trends or Google News, so a hashtag for
        them has no audience."""
        properties = CURATE_SCHEMA["items"]["properties"]["platform_hashtags"]["properties"]

        assert "google_trends" not in properties
        assert "google_news" not in properties


class TestRelevance:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (1, 1.0),
            (0.42, 0.42),
            ("0.7", 0.7),
            (1.8, 1.0),
            (-3, 0.0),
        ],
    )
    def test_it_is_clamped_to_the_range(self, raw: object, expected: float) -> None:
        assert _clean_relevance(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "high", {}, [], "nan"])
    def test_nothing_usable_becomes_none_not_a_default(self, raw: object) -> None:
        """Every default is a lie here: 0.0 drops the row and 1.0 keeps it,
        and neither is a judgement the curator made."""
        assert _clean_relevance(raw) is None

    def test_the_floor_is_the_documented_value(self) -> None:
        assert RELEVANCE_FLOOR == 0.3


class TestWhyTrending:
    def test_it_collapses_to_one_line(self) -> None:
        assert _one_line("  Won by three\n  wickets  ") == "Won by three wickets"

    def test_nothing_becomes_none(self) -> None:
        assert _one_line("") is None
        assert _one_line(None) is None
        assert _one_line("   ") is None

    def test_it_is_capped(self) -> None:
        assert len(_one_line("word " * 100) or "") <= 160


class TestPlatformHashtags:
    def test_each_platform_keeps_its_own_list(self) -> None:
        out = platform_hashtags_of(
            {
                "platform_hashtags": {
                    "reddit": ["#Cricket"],
                    "instagram": ["#cricketreels", "#teamindia"],
                }
            }
        )

        assert out == {
            SourceName.reddit: ["#Cricket"],
            SourceName.instagram: ["#cricketreels", "#teamindia"],
        }

    def test_an_unknown_platform_is_ignored(self) -> None:
        """A hallucinated key must not become a row for a platform that does
        not exist."""
        out = platform_hashtags_of({"platform_hashtags": {"tiktok": ["#fyp"]}})

        assert out == {}

    def test_an_empty_list_is_dropped_rather_than_stored(self) -> None:
        """Storing it would overwrite the adapter's scraped tags with nothing,
        which is worse than leaving them."""
        out = platform_hashtags_of({"platform_hashtags": {"reddit": [], "x": ["#INDvNZ"]}})

        assert out == {SourceName.x: ["#INDvNZ"]}

    def test_overlong_tags_are_dropped(self) -> None:
        """Same cap as the topic's own: a camel-cased headline is unusable on
        any network."""
        out = platform_hashtags_of(
            {
                "platform_hashtags": {
                    "youtube": ["#AbhishekSharmaFastestT20CenturyHighlights", "#INDvNZ"]
                }
            }
        )

        assert out == {SourceName.youtube: ["#INDvNZ"]}

    def test_a_joined_string_is_split(self) -> None:
        """Observed from the writer on the post prompt, so it is worth
        handling here too."""
        out = platform_hashtags_of({"platform_hashtags": {"x": ["#INDvNZ','#Cricket"]}})

        assert out == {SourceName.x: ["#INDvNZ", "#Cricket"]}

    @pytest.mark.parametrize("raw", [None, "nope", [], 7])
    def test_a_non_map_is_survived(self, raw: object) -> None:
        assert platform_hashtags_of({"platform_hashtags": raw}) == {}

    def test_an_absent_key_is_survived(self) -> None:
        assert platform_hashtags_of({}) == {}

    def test_indic_tags_survive_intact(self) -> None:
        """CLAUDE.md requires these publish, and the matra-stripping bug has
        appeared four times in this codebase."""
        out = platform_hashtags_of({"platform_hashtags": {"instagram": ["#மழை", "#मौसम"]}})

        assert out == {SourceName.instagram: ["#மழை", "#मौसम"]}


class TestRelevanceFloor:
    """What reaches a board. Two cases are easy to get backwards."""

    def test_a_local_story_is_kept_on_a_state_board(self) -> None:
        assert keeps_region_relevance(RegionKind.state, 1.0) is True
        assert keeps_region_relevance(RegionKind.state, 0.6) is True

    def test_a_story_that_merely_surfaced_there_is_not(self) -> None:
        assert keeps_region_relevance(RegionKind.state, 0.1) is False
        assert keeps_region_relevance(RegionKind.state, 0.0) is False

    def test_the_boundary_is_inclusive(self) -> None:
        assert keeps_region_relevance(RegionKind.state, RELEVANCE_FLOOR) is True

    def test_the_country_keeps_everything(self) -> None:
        """On India's own board a national story is local, so the floor would
        be discarding the best rows."""
        assert keeps_region_relevance(RegionKind.country, 0.0) is True

    def test_union_territories_and_cities_get_the_floor_too(self) -> None:
        assert keeps_region_relevance(RegionKind.union_territory, 0.1) is False
        assert keeps_region_relevance(RegionKind.city, 0.1) is False

    def test_an_unscored_topic_is_kept(self) -> None:
        """None means the curator did not answer — the fallback path when the
        LLM is unconfigured or over budget. Reading that as 0.0 would empty
        every state board the moment Gemini was unavailable, and the board is
        supposed to degrade to step 1, not to nothing."""
        assert keeps_region_relevance(RegionKind.state, None) is True
