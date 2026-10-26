"""The reel script: what is on each card, and what is said over it.

Both halves come from one model call, because they have to agree — a card
saying "₹2 crore" while the voice says something else is worse than either
alone. The spoken half is written in spoken form ("two crore rupees"), since
it goes straight to a text-to-speech voice that reads exactly what it is
given.

If the model is unavailable or over budget, the script is derived from the
topic instead. It is plainer, and it is a reel rather than a failure.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.llm import LLMError, LLMProvider
from app.prompts import render_prompt
from app.tasks.merge import clean_hashtags

log = get_logger("video.script")

PROMPT_ID = "write_reel_v1"

#: Three cards is the shape the prompt asks for. Two is thin, five is a reel
#: nobody finishes.
MIN_BEATS = 2
MAX_BEATS = 4
MAX_BEAT_WORDS = 8
MAX_DETAIL_WORDS = 12
#: Past this the card holds too long and the voice runs over the cut.
MAX_SAY_WORDS = 28

REEL_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING"},
        "intro_say": {"type": "STRING"},
        "beats": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "text": {"type": "STRING"},
                    "detail": {"type": "STRING"},
                    "say": {"type": "STRING"},
                },
                "required": ["text", "detail", "say"],
            },
        },
        "outro_say": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "alt_text": {"type": "STRING"},
        "drop": {"type": "BOOLEAN"},
    },
    "required": ["headline", "intro_say", "beats", "outro_say", "hashtags", "alt_text"],
}


class ScriptError(RuntimeError):
    """A failure worth showing the user verbatim."""


@dataclass(slots=True)
class Segment:
    """One card: what it shows, and what is said over it."""

    #: "title" | "beat" | "outro"
    kind: str
    say: str
    text: str = ""
    detail: str = ""


@dataclass(slots=True)
class ReelScript:
    headline: str
    segments: list[Segment]
    hashtags: list[str] = field(default_factory=list)
    alt_text: str = ""
    #: True when the script was derived rather than written, so the Desk can
    #: say so instead of implying a model wrote it.
    derived: bool = False

    @property
    def beats(self) -> list[Segment]:
        return [s for s in self.segments if s.kind == "beat"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "hashtags": self.hashtags,
            "alt_text": self.alt_text,
            "derived": self.derived,
            "segments": [
                {"kind": s.kind, "say": s.say, "text": s.text, "detail": s.detail}
                for s in self.segments
            ],
        }


def _words(value: Any, limit: int) -> str:
    """Collapse whitespace and cut to `limit` words."""
    parts = str(value or "").split()
    return " ".join(parts[:limit])


def _speakable(value: Any, limit: int = MAX_SAY_WORDS) -> str:
    """Strip what a voice should never be handed.

    A hashtag read aloud is "hash Goa A I", a URL is a minute of letters, and
    an emoji is either silence or the word "fire". The model is told not to
    put them in a spoken field; this is what happens when it does anyway.
    """
    text = str(value or "")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(?:(?<=\s)|^)[#@]\S+", "", text)
    text = re.sub(r"[*_`~|]+", "", text)
    text = "".join(ch for ch in text if _readable(ch))
    return _words(text, limit)


#: Sentence punctuation the voice phrases against. The curly apostrophe is
#: deliberate: it is what a model writes in "India's", and dropping it would
#: hand the voice "India s".
SPEAKABLE_PUNCTUATION = ".,!?'’-:;()"  # noqa: RUF001

#: Combining marks: Devanagari matras, Tamil vowel signs, nuktas, viramas.
#:
#: These have to be named explicitly because `str.isalnum()` is False for
#: every one of them — they are category Mn/Mc/Me, not letters. Filtering on
#: isalnum alone turns "लोग यह जानना चाहते हैं" into "लग यह जनन चहत ह", which
#: is not a spelling mistake but a different set of words, and it goes
#: straight to the voice and into the burned-in captions. The same mistake
#: was made once before, in normalise_topic.
MARK_CATEGORIES = frozenset({"Mn", "Mc", "Me"})


def _readable(ch: str) -> bool:
    """Whether a character survives into something that will be spoken."""
    if ch.isalnum() or ch.isspace() or ch in SPEAKABLE_PUNCTUATION:
        return True
    return unicodedata.category(ch) in MARK_CATEGORIES


async def write_script(llm: LLMProvider, brief: dict[str, Any]) -> ReelScript:
    """Ask the model for a script, or derive one if it cannot answer."""
    if llm.is_configured():
        try:
            return await _from_model(llm, brief)
        except ScriptError:
            raise
        except LLMError as exc:
            # Budget or outage. A plainer reel beats no reel, and the log
            # says which one this was.
            log.warning("reel script fell back to the topic", error=str(exc)[:200])
    else:
        log.info("no model configured, deriving the reel script from the topic")

    return derive_script(brief)


async def _from_model(llm: LLMProvider, brief: dict[str, Any]) -> ReelScript:
    prompt = render_prompt(
        PROMPT_ID,
        brand_name=brief["brand_name"],
        brand_voice=brief["brand_voice"],
        topic=brief["topic"],
        summary=brief["summary"],
        region_name=brief.get("region_name") or "India",
        evidence=brief["evidence"],
        language=brief["language"],
    )
    result = await llm.generate_json(
        prompt_id=PROMPT_ID, prompt=prompt, schema=REEL_SCHEMA, temperature=0.6
    )
    data = result.data if isinstance(result.data, dict) else {}

    if data.get("drop"):
        raise ScriptError(
            "The writer judged this topic one we do not market against, so no reel was made."
        )

    beats: list[Segment] = []
    for raw in data.get("beats") or []:
        if not isinstance(raw, dict):
            continue
        text = _words(raw.get("text"), MAX_BEAT_WORDS)
        say = _speakable(raw.get("say"))
        if not text or not say:
            continue
        beats.append(
            Segment(
                kind="beat",
                text=text,
                detail=_words(raw.get("detail"), MAX_DETAIL_WORDS),
                say=say,
            )
        )

    headline = _words(data.get("headline"), 14) or brief["topic"]
    intro = _speakable(data.get("intro_say"))
    outro = _speakable(data.get("outro_say"))

    if len(beats) < MIN_BEATS or not intro:
        log.warning("reel script came back thin, deriving instead", beats=len(beats))
        return derive_script(brief)

    return ReelScript(
        headline=headline,
        segments=[
            Segment(kind="title", say=intro),
            *beats[:MAX_BEATS],
            *([Segment(kind="outro", say=outro)] if outro else []),
        ],
        hashtags=clean_hashtags(data.get("hashtags"), 5),
        alt_text=str(data.get("alt_text") or "").strip(),
    )


def derive_script(brief: dict[str, Any]) -> ReelScript:
    """A script from the topic alone, for when the model cannot answer.

    Plain rather than clever: the summary is split into sentences and each one
    becomes a card, said as written. It will not win anyone an award, and it
    is a reel with a voice on it.
    """
    topic = str(brief.get("topic") or "").strip() or "Trending now"
    summary = str(brief.get("summary") or "").strip()
    region = str(brief.get("region_name") or "").strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary) if len(s.strip()) > 12]
    if not sentences:
        sentences = [topic]

    beats: list[Segment] = []
    for sentence in sentences[:MAX_BEATS]:
        beats.append(
            Segment(
                kind="beat",
                # The card gets the opening words, the voice gets the whole
                # sentence — the same split the model is asked to make.
                text=_words(sentence, 6),
                detail="",
                say=_speakable(sentence),
            )
        )
    if not beats:
        beats = [Segment(kind="beat", text=_words(topic, 6), say=_speakable(topic))]

    where = f" in {region}" if region else ""
    return ReelScript(
        headline=topic,
        segments=[
            Segment(kind="title", say=_speakable(f"Here is what is trending{where} today.")),
            *beats,
            Segment(kind="outro", say=_speakable(topic)),
        ],
        hashtags=list(brief.get("hashtags") or [])[:5],
        alt_text=topic,
        derived=True,
    )
