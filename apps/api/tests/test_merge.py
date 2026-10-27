"""The merge is the whole of step 1's intelligence, so it is tested directly."""

from __future__ import annotations

import pytest

from app.sources.base import RawTrendItem
from app.tasks.merge import (
    VELOCITY_POINTS,
    SourceItems,
    camel_hashtag,
    clean_hashtags,
    display_topic,
    hashtags_for,
    merge,
    merge_hashtags,
    next_velocity,
    normalise_topic,
    rank_points,
)


def item(title: str, rank: int, **kw) -> RawTrendItem:
    return RawTrendItem(title=title, rank=rank, **kw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Asia  Cup   Final ", "asia cup final"),
        ("ENG vs SL", "eng vs sl"),
        ("Diwali, 2026!", "diwali 2026"),
        # Curly quote and em dash on purpose: real headlines are full of them.
        ("India’s win — at last", "india s win at last"),  # noqa: RUF001
        ("नया गाना", "नया गाना"),
        ("", ""),
    ],
)
def test_normalise_topic(raw: str, expected: str) -> None:
    assert normalise_topic(raw) == expected


def test_normalise_topic_only_folds_case_and_punctuation() -> None:
    # Stopwords survive: dropping them would merge distinct local stories.
    assert normalise_topic("Fire in Delhi") != normalise_topic("Fire in Mumbai")


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("asia cup final", "#AsiaCupFinal"),
        ("ENG vs SL", "#ENGSL"),
        ("the fall of the rupee", "#FallRupee"),
        ("नया गाना", "#नयागाना"),
        ("2026 budget", "#Budget"),
        ("!!!", None),
        ("", None),
    ],
)
def test_camel_hashtag(topic: str, expected: str | None) -> None:
    assert camel_hashtag(topic) == expected


def test_camel_hashtag_never_starts_with_a_digit() -> None:
    # No network accepts #2026, so it must be dropped rather than emitted.
    assert camel_hashtag("2026", keep_stopwords=True) is None


def test_hashtags_for_dedupes_and_caps() -> None:
    tags = hashtags_for("India vs England", "Sports")

    assert tags[0] == "#IndiaEngland"
    assert "#IndiaVsEngland" in tags  # stopword-keeping variant
    assert "#Sports" in tags
    assert len(tags) <= 3
    assert len(set(tags)) == len(tags)


def test_hashtags_for_single_word_topic_has_no_duplicates() -> None:
    assert hashtags_for("Diwali") == ["#Diwali"]


def test_rank_points_decays_linearly() -> None:
    assert rank_points(1, 10) == 1.0
    assert rank_points(10, 10) == pytest.approx(0.1)
    assert rank_points(5, 10) > rank_points(6, 10)
    assert rank_points(1, 0) == 0.0


def test_merge_dedupes_case_insensitively_and_unions_sources() -> None:
    merged = merge(
        [
            SourceItems("google_trends", 1.0, [item("Asia Cup Final", 1)]),
            SourceItems("google_news", 0.7, [item("asia cup FINAL", 1)]),
        ]
    )

    assert len(merged) == 1
    assert merged[0].sources == ["google_trends", "google_news"]
    # Display text comes from the highest-weighted source that saw it.
    assert merged[0].topic == "Asia Cup Final"
    assert merged[0].topic_key == "asia cup final"


def test_merge_scores_multi_source_topics_above_single_source_ones() -> None:
    merged = merge(
        [
            SourceItems("google_trends", 1.0, [item("Shared", 2), item("TrendsOnly", 1)]),
            SourceItems("google_news", 0.7, [item("Shared", 1)]),
        ]
    )

    by_topic = {m.topic: m for m in merged}
    # TrendsOnly is rank 1 of a stronger source, but Shared is corroborated.
    assert by_topic["Shared"].score > by_topic["TrendsOnly"].score
    assert [m.topic for m in merged] == ["Shared", "TrendsOnly"]


def test_merge_orders_by_score_then_key_for_determinism() -> None:
    first = merge([SourceItems("google_news", 0.7, [item("Beta", 1), item("Alpha", 1)])])
    second = merge([SourceItems("google_news", 0.7, [item("Alpha", 1), item("Beta", 1)])])

    assert [m.topic_key for m in first] == [m.topic_key for m in second] == ["alpha", "beta"]


def test_merge_takes_max_volume_and_first_category() -> None:
    merged = merge(
        [
            SourceItems("google_trends", 1.0, [item("Topic", 1, volume=200000, category="Sports")]),
            SourceItems("youtube", 0.6, [item("topic", 1, volume=4820193)]),
        ]
    )

    assert merged[0].volume == 4820193
    assert merged[0].category == "Sports"


def test_merge_keeps_evidence_for_the_desk_panel() -> None:
    merged = merge(
        [
            SourceItems(
                "google_news",
                0.7,
                [
                    item(
                        "Flyover opens",
                        1,
                        url="https://ex.ample/a",
                        extra={"publisher": "The Hindu"},
                    )
                ],
            )
        ]
    )

    evidence = merged[0].evidence[0]
    assert evidence["source"] == "google_news"
    assert evidence["rank"] == 1
    assert evidence["url"] == "https://ex.ample/a"
    assert evidence["publisher"] == "The Hindu"


def test_merge_skips_blank_titles_and_applies_limit() -> None:
    merged = merge(
        [SourceItems("google_news", 0.7, [item("  ", 1), item("A", 2), item("B", 3)])],
        limit=1,
    )

    assert len(merged) == 1
    assert merged[0].topic in {"A", "B"}


def test_merge_of_nothing_is_empty() -> None:
    assert merge([]) == []
    assert merge([SourceItems("google_news", 0.7, [])]) == []


def test_next_velocity_pads_new_topics_to_six_points() -> None:
    series = next_velocity(None, 42.0)

    assert len(series) == VELOCITY_POINTS
    assert series == [0.0, 0.0, 0.0, 0.0, 0.0, 42.0]


def test_next_velocity_keeps_a_rolling_window_of_the_previous_five() -> None:
    series = next_velocity([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 7.0)

    assert series == [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert len(series) == VELOCITY_POINTS


def test_next_velocity_records_a_drop_off_as_zero() -> None:
    assert next_velocity([10.0, 9.0], 0.0)[-1] == 0.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Google Trends hands back fully lowercased keywords.
        ("eng vs sl", "Eng vs sl"),
        ("gold rate today", "Gold rate today"),
        # Anything with existing capitals is left alone: acronyms survive.
        ("ENG vs SL", "ENG vs SL"),
        (
            "Cabinet Secretary had copied acknowledgement",
            "Cabinet Secretary had copied acknowledgement",
        ),
        # Devanagari has no case; must pass through byte-identical.
        ("नेहा बोरा", "नेहा बोरा"),
        ("  padded  ", "Padded"),
        ("", ""),
    ],
)
def test_display_topic(raw: str, expected: str) -> None:
    assert display_topic(raw) == expected


def test_merge_emits_sentence_cased_display_text_but_keeps_the_raw_key() -> None:
    merged = merge([SourceItems("google_trends", 1.0, [item("eng vs sl", 1)])])

    assert merged[0].topic == "Eng vs sl"
    # The dedupe key stays lowercase so casing changes can never split a topic.
    assert merged[0].topic_key == "eng vs sl"


class TestCleanHashtags:
    """Gemini's hashtag arrays arrive in several shapes, not all of them lists."""

    def test_a_normal_list_passes_through(self) -> None:
        assert clean_hashtags(["#Goa", "#AI"], 8) == ["#Goa", "#AI"]

    def test_the_whole_list_arriving_as_one_joined_string_is_split(self) -> None:
        # Observed live: the writer returned all eight tags as a single string.
        mangled = ["#GoaAIPolicy','#TechHub','#AIInGoa','#GoaTech"]

        assert clean_hashtags(mangled, 8) == [
            "#GoaAIPolicy",
            "#TechHub",
            "#AIInGoa",
            "#GoaTech",
        ]

    def test_missing_hashes_are_added_and_duplicates_dropped(self) -> None:
        assert clean_hashtags(["Goa", "#Goa", "AI"], 8) == ["#Goa", "#AI"]

    def test_indic_tags_survive_intact(self) -> None:
        assert clean_hashtags(["#नयागाना", "#கோவா"], 8) == ["#नयागाना", "#கோவா"]

    def test_the_limit_is_honoured(self) -> None:
        assert len(clean_hashtags([f"#t{i}" for i in range(20)], 8)) == 8

    def test_junk_yields_nothing_rather_than_empty_hashes(self) -> None:
        assert clean_hashtags(["", "#", "  ", None], 8) == []
        assert clean_hashtags(None, 8) == []
        assert clean_hashtags("not a list", 8) == []


class TestMergeHashtags:
    """What a post publishes: the writer's tags and the curator's, and never
    the raw trend column."""

    def test_both_sets_are_published(self) -> None:
        tags = merge_hashtags(["#AINews", "#Startups"], ["#Anthropic", "#IPO"], 8)

        assert set(tags) == {"#AINews", "#Startups", "#Anthropic", "#IPO"}

    def test_the_curators_tags_survive_the_cap(self) -> None:
        """The writer invents a fresh set per caption and the curator's are
        the topic's canonical handles, so the writer is the one with tags to
        spare. Dropping the handles would make two posts about one story
        stop matching each other."""
        writer = [f"#W{i}" for i in range(8)]

        tags = merge_hashtags(writer, ["#Anthropic", "#IPO"], 5)

        assert len(tags) == 5
        assert "#Anthropic" in tags
        assert "#IPO" in tags

    def test_duplicates_are_dropped_case_insensitively(self) -> None:
        """#AiIpo and #AIIPO are one tag on every network that matters."""
        tags = merge_hashtags(["#aiipo", "#Tech"], ["#AIIPO"], 8)

        assert len(tags) == 2
        assert "#Tech" in tags

    def test_a_writer_with_nothing_still_publishes_the_handles(self) -> None:
        assert merge_hashtags([], ["#Anthropic"], 8) == ["#Anthropic"]

    def test_an_uncurated_topic_contributes_nothing(self) -> None:
        """`curator_hashtags` is empty for an uncurated row, so the merge has
        only the writer's tags to work with — which is the point. The raw
        column holds the source headline as one word."""
        assert merge_hashtags(["#AINews"], [], 8) == ["#AINews"]

    def test_the_limit_is_honoured_by_the_curator_too(self) -> None:
        tags = merge_hashtags([], [f"#C{i}" for i in range(9)], 4)

        assert len(tags) == 4
