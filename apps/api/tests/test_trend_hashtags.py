"""Which hashtags on a trend row are fit to publish.

One column, two writers. The curator rewrites it with handles it chose and
length-capped; the non-LLM merge fills it by camel-casing the whole source
headline, which gives #AIToolHelpedRajasthanRoyals — a tag nobody would post.
`curated_at` is what tells them apart, and reading the column without
checking it is how a source headline reaches a caption.
"""

from __future__ import annotations

from app.core.time import utcnow
from app.models import Trend


def trend(**kw) -> Trend:
    return Trend(
        region_id=1,
        topic_key="k",
        topic="AI tool that helped Rajasthan Royals",
        first_seen_at=utcnow(),
        last_seen_at=utcnow(),
        **kw,
    )


def test_a_curated_row_publishes_its_tags() -> None:
    row = trend(hashtags=["#Anthropic", "#IPO"], curated_at=utcnow())

    assert row.curator_hashtags == ["#Anthropic", "#IPO"]


def test_an_uncurated_row_publishes_nothing() -> None:
    """The real value observed on these rows, which is the entire headline as
    one word. Better to publish the writer's tags alone than this."""
    row = trend(hashtags=["#AIToolHelpedRajasthanRoyals"], curated_at=None)

    assert row.curator_hashtags == []


def test_a_row_with_no_tags_at_all_is_empty_not_none() -> None:
    """Callers join and slice this, so it is always a list."""
    assert trend(hashtags=[], curated_at=utcnow()).curator_hashtags == []
    assert trend(curated_at=utcnow()).curator_hashtags == []


def test_the_caller_cannot_mutate_the_row_through_it() -> None:
    row = trend(hashtags=["#IPO"], curated_at=utcnow())

    row.curator_hashtags.append("#royal")

    assert row.hashtags == ["#IPO"]
