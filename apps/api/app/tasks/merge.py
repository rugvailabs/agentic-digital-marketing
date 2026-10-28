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

from app.core.hashtags import (
    _WS,
    MAX_HASHTAGS,
    _strip_punctuation,
    # Re-exported: tests and callers import camel_hashtag from here, and the
    # move to app.core.hashtags was about breaking an import cycle, not about
    # relocating the public name.
    camel_hashtag,
    is_publishable_hashtag,
)
from app.core.logging import get_logger
from app.sources.base import RawTrendItem

#: How many points the sparkline carries: current score + previous 5 snapshots.
VELOCITY_POINTS = 6


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


def clean_hashtags(raw: object, limit: int) -> list[str]:
    """Normalise whatever the model called a hashtag list.

    Gemini sometimes returns all of them as one string —
    `["#A','#B','#C"]` — so items are split on quotes, commas and whitespace
    before being tidied. Splitting on whitespace too is the safer default:
    three short tags beat one unusable one, and the prompt already asks for
    no spaces inside a tag.
    """
    tags: list[str] = []
    dropped: list[str] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if item is None:
            # str(None) would otherwise become the tag "#None".
            continue
        for part in re.split(r"[\s,;'\"]+", str(item)):
            token = part.strip().lstrip("#")
            if not token:
                continue
            tag = f"#{token}"
            # The shape check, which lives in core.hashtags with the rest of
            # the text handling. Without it `#me=1` reached a published
            # caption: it is not a bare search term and not ungrounded, so
            # every filter downstream of here had a reason to keep it.
            if not is_publishable_hashtag(tag):
                dropped.append(tag)
                continue
            if tag not in tags:
                tags.append(tag)
    if dropped:
        # Logged for the same reason the grounding filter logs: a filter
        # that deletes output silently is one you discover months later.
        log.info("dropped malformed hashtags", tags=dropped)
    return tags[:limit]


#: Splits a hashtag into words. The ASCII alternatives handle CamelCase;
#: the last one takes any run of non-ASCII characters whole.
#:
#: It has to be an explicit ASCII range and not `\w`, for the third time in this
#: codebase. Python's `\w` follows `str.isalnum()`, which is False for every
#: combining mark — Devanagari matras, Tamil vowel signs, nuktas, viramas are
#: category Mn/Mc/Me, not letters. A `\w`-based pattern cut #மழை down to
#: "மழ", a different word, and the same mistake has already been made in
#: `normalise_topic` and in the voiceover's `_speakable`.
#:
#: A tag with no tokens would also be ungrounded by construction: measured
#: against the posts already generated, an ASCII-only pattern silently
#: deleted every Tamil-script hashtag in the corpus.
_HASHTAG_TOKEN = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+|[^\x00-\x7F]+")

#: Same reason, for the text a tag is grounded against.
_CONTEXT_WORD = re.compile(r"[A-Za-z]+|\d+|[^\x00-\x7F]+")

#: Letters shared before two words count as the same root: "investments"
#: against "investors", "startups" against "startup".
_ROOT_CHARS = 6

log = get_logger("tasks.hashtags")


def hashtag_tokens(tag: str) -> list[str]:
    """The words inside a hashtag, lowercased. #PinkCity -> [pink, city]."""
    return [part.lower() for part in _HASHTAG_TOKEN.findall(tag.lstrip("#")) if part]


def _context_words(context: str) -> set[str]:
    return {word.lower() for word in _CONTEXT_WORD.findall(context or "")}


def _is_grounded(tag: str, words: set[str]) -> bool:
    for token in hashtag_tokens(tag):
        if token in words:
            return True
        if len(token) >= _ROOT_CHARS and any(
            word[:_ROOT_CHARS] == token[:_ROOT_CHARS] and len(word) >= _ROOT_CHARS for word in words
        ):
            return True
    return False


def _is_bare_search_term(tag: str) -> bool:
    """One lowercase ASCII word — what a trending query looks like, not a
    hashtag. The prompt asks for CamelCase and the writer obliges, so the
    tags that come back like this are the ones it did not really compose."""
    body = tag.lstrip("#")
    return len(hashtag_tokens(tag)) == 1 and body.isascii() and body.isalpha() and body.islower()


def grounded_hashtags(tags: list[str], context: str) -> list[str]:
    """Drop tags that are neither composed nor traceable to the content.

    Narrow on purpose, and the narrowness is measured rather than guessed.
    Against the 131 hashtags on the posts already generated:

        require every token grounded        drops 47-49%
        require any token grounded          drops 20-27%
        ... or be multi-word                drops  8%
        ... or not be a bare search term    drops  0.8%  (one tag: #royal)

    The looser rules take #TamilNadu, #Aviation, #MaritimeSecurity and
    #INSVikrant with them, because a good hashtag is deliberately broader
    than the sentence it sits under — that is what makes it reach. So only
    the last rule ships: a tag has to be both ungrounded *and* shaped like a
    raw query to be dropped.

    This does not catch an ungrounded tag that happens to be capitalised.
    Tightening it costs an eighth of the real tags, which is the worse trade.
    """
    words = _context_words(context)
    kept, dropped = [], []
    for tag in tags:
        if _is_bare_search_term(tag) and not _is_grounded(tag, words):
            dropped.append(tag)
        else:
            kept.append(tag)
    if dropped:
        # Logged, never silent. A filter that quietly deletes output is how
        # you find out months later that half the tags were missing.
        log.info("dropped ungrounded hashtags", tags=dropped)
    return kept


def merge_hashtags(
    writer: list[str], curator: list[str], limit: int, *, context: str = ""
) -> list[str]:
    """What a post or reel publishes: the writer's tags and the curator's.

    The curator's survive the cap and the writer's surplus is what gets
    dropped. They are the topic's canonical handles — the thing that makes
    two posts about one story findable together — and the writer invents a
    fresh set per caption, so the writer is the one with tags to spare.

    Raw trend tags are not an input here and must not become one. They are
    the source headline camel-cased into a single word, and they reached a
    published caption once by being handed to the writer as prior art.

    `context` is whatever the tag can legitimately be traced to — the caption
    just written, the topic, its summary and region. The writer's tags are
    grounded against it; the curator's are not, because the curator chose
    them for this topic and is the authority on it.
    """
    if context:
        writer = grounded_hashtags(writer, context)

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
    #: Per-platform aggregates for `trend_sources`, one entry per source that
    #: contributed. Carried here because `trend_items` rows are a curator
    #: artefact: the merge never writes them, so for the 52 uncurated regions
    #: this is the only place the per-platform numbers exist.
    platforms: list[dict[str, Any]] = field(default_factory=list)


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
                    # Keyed by source name so repeated contributions from one
                    # platform aggregate instead of appending.
                    "platforms": {},
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

            # Same aggregation sync_platforms does over trend_items: best
            # rank wins and brings its url, volume is the largest reported
            # rather than a sum, and hashtags are that platform's own.
            platform = bucket["platforms"].setdefault(
                contribution.source,
                {
                    "platform": contribution.source,
                    "rank": item.rank or None,
                    "volume": int(item.volume or 0),
                    "hashtags": [],
                    "url": item.url,
                },
            )
            if item.rank and (platform["rank"] is None or item.rank < platform["rank"]):
                platform["rank"], platform["url"] = item.rank, item.url
            platform["volume"] = max(platform["volume"], int(item.volume or 0))
            for tag in item.extra.get("hashtags") or []:
                tag = str(tag)
                if tag.strip() and tag.lower() not in {t.lower() for t in platform["hashtags"]}:
                    platform["hashtags"].append(tag)

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
            platforms=list(b["platforms"].values()),
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
