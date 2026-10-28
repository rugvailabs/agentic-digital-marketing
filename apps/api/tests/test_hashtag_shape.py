r"""No hashtag ships with a `=` in it, and none is only digits.

Written after four of them did. One caption published

    #DussehraSpecial #KarwaChauthComedy #FestiveShorts #me=1 #me=2 #me=3 #me=4

and nothing in the path had an opinion: `clean_hashtags` only split and
deduped, `grounded_hashtags` asks whether a tag is traceable to the copy
and an invented tag with a digit in it is not shaped like a bare search
term, so it had no reason to drop one. The missing rule was the dull one —
whether the string is a hashtag at all.

Every case here runs in Devanagari and Tamil as well as ASCII, because the
reason this file's rule is a Unicode category test and not `\w` is that
`\w` and `str.isalnum()` are False for combining marks. An ASCII-only
suite would pass against an implementation that deletes every Indic tag.
"""

from __future__ import annotations

import pytest

from app.core.hashtags import is_publishable_hashtag, literal_hashtags
from app.tasks.merge import clean_hashtags

#: The bug, and its neighbours.
MALFORMED = [
    "#me=1",
    "#me=2",
    "#t=30",
    "#utm_source=rss&utm_medium=x",
    "#oc=5",
    "#2026",
    "#1",
    "#___",
    "#",
    "#?q=weather",
    "#a/b",
]

#: Real tags, including the two scripts the ASCII tests kept missing.
WELL_FORMED = [
    "#DussehraSpecial",
    "#ComedyShorts",
    "#मौसम",
    "#मौसमअपडेट",
    "#மழை",
    "#வானிலை",
    "#Mumbai2026",
    "#INSVikrant",
]


@pytest.mark.parametrize("tag", MALFORMED)
def test_malformed_tags_are_not_publishable(tag: str) -> None:
    assert is_publishable_hashtag(tag) is False


@pytest.mark.parametrize("tag", WELL_FORMED)
def test_real_tags_survive(tag: str) -> None:
    assert is_publishable_hashtag(tag) is True


def test_indic_tags_keep_their_combining_marks() -> None:
    """The rule that makes this file necessary, stated as a test.

    मौसम is म + ौ + स + म: the ौ is category Mc, which `str.isalnum()`
    calls False. A check written as "every character alphanumeric" rejects
    the whole tag; one written as "at least one letter" keeps it, and keeps
    it whole.
    """
    for tag in ("#मौसम", "#மழை", "#கோவா", "#बारिश"):
        assert is_publishable_hashtag(tag) is True
        # And nothing downstream shortens it.
        assert clean_hashtags([tag], 5) == [tag]


def test_the_caption_that_shipped_is_cleaned() -> None:
    """The exact list off content_asset 166."""
    shipped = [
        "#DussehraSpecial",
        "#KarwaChauthComedy",
        "#FestiveShorts",
        "#me=1",
        "#me=2",
        "#me=3",
        "#ComedyShorts",
        "#me=4",
    ]
    assert clean_hashtags(shipped, 8) == [
        "#DussehraSpecial",
        "#KarwaChauthComedy",
        "#FestiveShorts",
        "#ComedyShorts",
    ]


def test_no_cleaned_hashtag_ever_carries_a_query_string() -> None:
    """The invariant, over every case in this file at once."""
    for tag in clean_hashtags(MALFORMED + WELL_FORMED, 50):
        body = tag.lstrip("#")
        assert "=" not in tag
        assert not body.isdigit()
        assert body


def test_a_url_fragment_in_a_description_is_not_a_tag() -> None:
    """The scraping path, which reads a YouTube description for typed tags.

    A description is mostly links, and `youtu.be/x?t=30&list=PL` carries a
    `=` through any reading that only looks for a `#`.
    """
    tags = literal_hashtags(
        "watch https://ex.com/a?utm_source=rss&oc=5 #மழை #DussehraSpecial"
    )
    assert "#மழை" in tags
    assert "#DussehraSpecial" in tags
    assert not any("=" in tag for tag in tags)
