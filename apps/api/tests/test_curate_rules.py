"""Curator output rules: categories, hashtag shape, and dropped keywords.

These are the parts a model gets wrong often enough that the code has to
enforce them, so they are tested against the code rather than the prompt.
"""

from __future__ import annotations

import pytest

from app.tasks.curate import (
    CATEGORIES,
    FALLBACK_CATEGORY,
    MAX_HASHTAG_CHARS,
    _clean_category,
    _clean_hashtags,
)
from app.tasks.merge import display_topic


class TestCategory:
    def test_the_enum_is_the_one_the_prompt_offers(self) -> None:
        assert CATEGORIES[-1] == FALLBACK_CATEGORY, "Other is the last resort"
        assert {"Weather", "Civic", "Festival", "Crime"} <= set(CATEGORIES)

    @pytest.mark.parametrize("value", CATEGORIES)
    def test_every_listed_category_survives(self, value: str) -> None:
        assert _clean_category(value) == value

    @pytest.mark.parametrize("value", [None, "", "Lifestyle", "Autos and Vehicles", "  "])
    def test_anything_else_becomes_other_rather_than_null(self, value) -> None:
        # Every topic must carry a category; the ladder chip has no empty state.
        assert _clean_category(value) == FALLBACK_CATEGORY


class TestHashtags:
    def test_short_handles_pass_through(self) -> None:
        tags = _clean_hashtags(["#RafaleMarine", "#INSVikrant"], "Rafale Marine trials")

        assert tags == ["#RafaleMarine", "#INSVikrant"]

    def test_a_camel_cased_headline_is_rejected_not_truncated(self) -> None:
        """Truncating would invent a different word; dropping is honest."""
        tags = _clean_hashtags(
            ["#RafaleMarineFighterBeginsFlightTrials", "#Goa"], "Rafale Marine trials"
        )

        assert tags == ["#Goa"]
        assert all(len(t) <= MAX_HASHTAG_CHARS for t in tags)

    def test_a_topic_is_never_left_tagless(self) -> None:
        # Everything the model sent was unusable, so build from the title.
        tags = _clean_hashtags(["#" + "x" * 40], "Goa weather forecast")

        assert tags
        assert all(len(t) <= MAX_HASHTAG_CHARS for t in tags)

    def test_at_most_six(self) -> None:
        tags = _clean_hashtags([f"#Tag{i}" for i in range(12)], "t")

        assert len(tags) == 6

    def test_indic_handles_are_kept(self) -> None:
        tags = _clean_hashtags(["#नयागाना", "#கோவா"], "नया गाना")

        assert tags == ["#नयागाना", "#கோவா"]


class TestTitleCasing:
    """The prompt asks for it; the code enforces it."""

    def test_an_all_lowercase_title_gains_a_capital(self) -> None:
        assert display_topic("zimbabwe vs afghanistan") == "Zimbabwe vs afghanistan"

    def test_a_deliberately_cased_title_is_untouched(self) -> None:
        # "ENG vs SL" is how the source wrote it and how it must stay.
        assert display_topic("ENG vs SL standings") == "ENG vs SL standings"
        assert display_topic("Gold rate today in India") == "Gold rate today in India"

    def test_indic_scripts_are_unaffected(self) -> None:
        assert display_topic("नेहा बोरा") == "नेहा बोरा"
