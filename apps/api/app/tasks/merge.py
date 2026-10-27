"""Non-LLM merge: raw per-source items -> one ranked board per region.

Deliberately boring and deterministic. No model is involved in step 1, so the
board is reproducible from the snapshots alone and every number on screen can
be explained from this file.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.sources.base import RawTrendItem

#: How many points the sparkline carries: current score + previous 5 snapshots.
VELOCITY_POINTS = 6

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


def _is_kept(ch: str) -> bool:
    return ch.isalnum() or ch.isspace() or unicodedata.category(ch) in _MARK_CATEGORIES


def _strip_punctuation(text: str) -> str:
    return "".join(ch if _is_kept(ch) else " " for ch in text)


def normalise_topic(title: str) -> str:
    """Collapse a headline to a dedupe key.

    Only case, punctuation and whitespace are normalised — stopwords are kept,
    because dropping them merges genuinely different topics ("India vs England"
    and "England vs India" are the same story, but "fire in Delhi" and "fire in
    Mumbai" are not, and aggressive stripping starts to blur that line).
    """
    text = unicodedata.normalize("NFKC", title or "").casefold()
    return _WS.sub(" ", _strip_punctuation(text)).strip()


def display_topic(title: str) -> str:
    """Sentence-case a topic for the board.

    Google Trends returns keywords fully lowercased ("eng vs sl"), which reads
    as broken next to news headlines. CLAUDE.md asks for sentence case, so only
    the first letter is raised — title-casing every word would mangle the
    acronyms these topics are mostly made of. Mixed-case text is left alone,
    and scripts without case are unaffected.
    """
    text = (title or "").strip()
    if not text or any(ch.isupper() for ch in text):
        return text
    return text[:1].upper() + text[1:]


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


def clean_hashtags(raw: object, limit: int) -> list[str]:
    """Normalise whatever the model called a hashtag list.

    Gemini sometimes returns all of them as one string —
    `["#A','#B','#C"]` — so items are split on quotes, commas and whitespace
    before being tidied. Splitting on whitespace too is the safer default:
    three short tags beat one unusable one, and the prompt already asks for
    no spaces inside a tag.
    """
    tags: list[str] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if item is None:
            # str(None) would otherwise become the tag "#None".
            continue
        for part in re.split(r"[\s,;'\"]+", str(item)):
            token = part.strip().lstrip("#")
            if not token:
                continue
            tag = f"#{token}"
            if tag not in tags:
                tags.append(tag)
    return tags[:limit]


def merge_hashtags(writer: list[str], curator: list[str], limit: int) -> list[str]:
    """What a post or reel publishes: the writer's tags and the curator's.

    The curator's survive the cap and the writer's surplus is what gets
    dropped. They are the topic's canonical handles — the thing that makes
    two posts about one story findable together — and the writer invents a
    fresh set per caption, so the writer is the one with tags to spare.

    Raw trend tags are not an input here and must not become one. They are
    the source headline camel-cased into a single word, and they reached a
    published caption once by being handed to the writer as prior art.
    """
    kept: list[str] = []
    seen: set[str] = set()

    def take(tags: list[str], room: int) -> None:
        for tag in tags:
            # Case-insensitively, so #AIIPO and #AiIpo are not both published.
            key = tag.lower()
            if key in seen or len(kept) >= room:
                continue
            seen.add(key)
            kept.append(tag)

    take(curator, limit)
    take(writer, limit)
    return kept


def hashtags_for(topic: str, category: str | None = None) -> list[str]:
    """Primary camel-cased tag, then cheap variants, deduped and capped."""
    tags: list[str] = []
    for candidate in (
        camel_hashtag(topic),
        camel_hashtag(topic, keep_stopwords=True),
        camel_hashtag(category) if category else None,
    ):
        if candidate and candidate not in tags:
            tags.append(candidate)
    return tags[:MAX_HASHTAGS]


def rank_points(rank: int, pool: int) -> float:
    """1.0 for rank 1, decaying linearly to ~0 for the last item in the pool.

    Linear rather than 1/rank: sources publish different list lengths, and a
    reciprocal curve makes everything below rank 5 indistinguishable, which
    loses the long tail that state boards are mostly made of.
    """
    if pool <= 0:
        return 0.0
    return max(0.0, (pool - rank + 1) / pool)


@dataclass(slots=True)
class SourceItems:
    """One source's contribution to one region."""

    source: str
    weight: float
    items: list[RawTrendItem]


@dataclass(slots=True)
class MergedTopic:
    topic: str
    topic_key: str
    score: float
    volume: int
    category: str | None
    sources: list[str]
    hashtags: list[str]
    evidence: list[dict[str, Any]] = field(default_factory=list)


def merge(contributions: list[SourceItems], *, limit: int | None = None) -> list[MergedTopic]:
    """Dedupe by normalised title and score by weighted source rank.

    Returned in descending score order; the caller assigns `rank` from the
    position so ties break deterministically on first appearance.
    """
    buckets: dict[str, dict[str, Any]] = {}

    for contribution in contributions:
        pool = len(contribution.items)
        for item in contribution.items:
            key = normalise_topic(item.title)
            if not key:
                continue

            points = rank_points(item.rank, pool) * contribution.weight
            bucket = buckets.setdefault(
                key,
                {
                    "score": 0.0,
                    "best_weight": -1.0,
                    "topic": item.title.strip(),
                    "category": None,
                    "volume": 0,
                    "sources": [],
                    "evidence": [],
                },
            )

            bucket["score"] += points
            # Display text comes from the most trusted source that saw it; on a
            # tie the earlier rank wins, which is the first one recorded.
            if contribution.weight > bucket["best_weight"]:
                bucket["best_weight"] = contribution.weight
                bucket["topic"] = item.title.strip()
            if bucket["category"] is None and item.category:
                bucket["category"] = item.category
            if item.volume:
                bucket["volume"] = max(bucket["volume"], item.volume)
            if contribution.source not in bucket["sources"]:
                bucket["sources"].append(contribution.source)
            bucket["evidence"].append(
                {
                    "source": contribution.source,
                    "rank": item.rank,
                    "title": item.title.strip(),
                    "url": item.url,
                    **{k: v for k, v in item.extra.items() if k in _EVIDENCE_KEYS},
                }
            )

    merged = [
        MergedTopic(
            topic=display_topic(b["topic"]),
            topic_key=key,
            # Scaled to a readable 0-100-ish range; it is an ordering signal,
            # not a measurement, so the exact scale carries no meaning.
            score=round(b["score"] * 100, 2),
            volume=int(b["volume"]),
            category=b["category"],
            sources=list(b["sources"]),
            hashtags=hashtags_for(b["topic"], b["category"]),
            evidence=b["evidence"][:12],
        )
        for key, b in buckets.items()
    ]
    merged.sort(key=lambda m: (-m.score, m.topic_key))
    return merged[:limit] if limit else merged


_EVIDENCE_KEYS = frozenset(
    {"publisher", "published", "channel", "thumbnail", "volume_growth_pct", "related"}
)


def next_velocity(previous: list[float] | None, current_score: float) -> list[float]:
    """Exactly VELOCITY_POINTS scores, oldest first.

    Left-padded with zeros for a topic we have not seen before, so a new entry
    draws as a spike from nothing — which is what it is.
    """
    history = [float(v) for v in (previous or [])][-(VELOCITY_POINTS - 1) :]
    series = [*history, float(current_score)]
    if len(series) < VELOCITY_POINTS:
        series = [0.0] * (VELOCITY_POINTS - len(series)) + series
    return [round(v, 2) for v in series[-VELOCITY_POINTS:]]
