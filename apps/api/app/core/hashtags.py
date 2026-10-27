"""Hashtag text handling, shared by the source adapters and the merge.

Here rather than in `app.tasks.merge` because of a real cycle. `merge` imports
RawTrendItem from `app.sources.base`, and importing anything under
`app.sources` runs that package's `__init__`, which imports every adapter. So
as soon as an adapter imported a hashtag helper from `app.tasks.merge`,
importing `merge` first died on a partially initialised module:

    app.tasks.merge -> app.sources.base -> app.sources/__init__
                    -> app.sources.reddit -> app.tasks.merge  (partial)

It passed the entire suite, because every test path happened to import
`app.sources` before `app.tasks.merge`. The implied layering rule: an adapter
never imports from `app.tasks`. These are pure text functions with no model,
task or network dependency, so this is where they belonged anyway.
"""

from __future__ import annotations

import re
import unicodedata

#: Words that carry no topic meaning and never belong in a hashtag.
_STOPWORD_TEXT = (
    "a an the and or but of for to in on at by with from as is are was were be been "
    "will would can could should may might do does did this that these those it its "
    "his her their our your my if then than so no not vs v"
)
HASHTAG_STOPWORDS = frozenset(_STOPWORD_TEXT.split())

#: Hashtags longer than this read as spam and get truncated out of existence.
MAX_HASHTAG_WORDS = 5
MAX_HASHTAGS = 3

_WS = re.compile(r"\s+", flags=re.UNICODE)

#: Combining marks: Devanagari/Tamil/Telugu matras are Mn or Mc, and Python's
#: `\w` does not match them. A naive [^\w\s] strip therefore deletes the vowel
#: signs out of Indic text — नया गाना becomes नय गन — so punctuation is
#: removed by category instead of by regex class.
_MARK_CATEGORIES = frozenset({"Mn", "Mc", "Me"})

#: A hashtag somebody actually typed. The second alternative takes any run of
#: non-space, non-# characters, which is what keeps #मौसम whole: an ASCII
#: `\w+` would capture it as #मसम, dropping the matra.
_TYPED_TAG = re.compile(r"#([A-Za-z0-9_]+|[^\s#]+)")


def _is_kept(ch: str) -> bool:
    return ch.isalnum() or ch.isspace() or unicodedata.category(ch) in _MARK_CATEGORIES


def _strip_punctuation(text: str) -> str:
    return "".join(ch if _is_kept(ch) else " " for ch in text)


def camel_hashtag(text: str, *, keep_stopwords: bool = False) -> str | None:
    """`asia cup final` -> `#AsiaCupFinal`.

    Scripts without case (Devanagari, Tamil, …) simply lose their spaces, which
    is what Indian social copy does anyway: #नयागाना.
    """
    cleaned = _strip_punctuation(unicodedata.normalize("NFKC", text or ""))
    words = [w for w in _WS.split(cleaned) if w]
    if not keep_stopwords:
        significant = [w for w in words if w.casefold() not in HASHTAG_STOPWORDS]
        words = significant or words

    # No network accepts a hashtag that starts with a digit, so lead-in numbers
    # are dropped rather than invalidating the whole tag: "2026 budget" is
    # #Budget, not nothing.
    while words and not words[0][:1].isalpha():
        words = words[1:]
    words = words[:MAX_HASHTAG_WORDS]
    if not words:
        return None

    tag = "".join(w[:1].upper() + w[1:] for w in words)
    tag = "".join(ch for ch in tag if ch.isalnum() or unicodedata.category(ch) in _MARK_CATEGORIES)
    return f"#{tag}" if tag else None


def literal_hashtags(*texts: str, limit: int = 8) -> list[str]:
    """Hashtags written into the given text, deduped case-insensitively.

    Shared by Reddit and YouTube because both want the same reading of what
    counts as typed: a YouTube description is where creators put their real
    tags, and a Reddit title occasionally carries one.
    """
    out: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for body in _TYPED_TAG.findall(text or ""):
            tag = f"#{body}".rstrip(".,!?:;)")
            key = tag.lower()
            if len(tag) > 1 and key not in seen:
                seen.add(key)
                out.append(tag)
            if len(out) >= limit:
                return out
    return out
