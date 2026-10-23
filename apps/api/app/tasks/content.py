"""The content studio: write a caption, render the images, store them.

One job moves queued -> writing -> rendering -> ready, or stops at failed with
a message a user can act on. The status is on the row rather than inferred, so
the Desk can poll a single endpoint and a crashed worker leaves evidence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.images import ImageBrief, PillowTemplateProvider, put_png
from app.images.base import SIZES
from app.images.gemini_image import GeminiImageProvider
from app.images.pillow import TEMPLATES
from app.llm import LLMError, LLMProvider, get_llm
from app.models import (
    AssetKind,
    ContentAsset,
    ContentJob,
    JobStatus,
    SafetyFlag,
    Trend,
    TrendItem,
)
from app.prompts import render_prompt
from app.tasks.merge import clean_hashtags

log = get_logger("content")

PROMPT_ID = "write_post_v2"
HASHTAG_COUNT = 8

WRITE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "hook": {"type": "STRING"},
        "caption": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "image_headline": {"type": "STRING"},
        "image_subline": {"type": "STRING"},
        "display_token": {"type": "STRING"},
        "alt_text": {"type": "STRING"},
    },
    "required": [
        "hook",
        "caption",
        "hashtags",
        "image_headline",
        "image_subline",
        "display_token",
        "alt_text",
    ],
}


class ContentError(RuntimeError):
    """A failure worth showing the user verbatim."""


@dataclass(slots=True)
class Post:
    hook: str
    caption: str
    hashtags: list[str]
    image_headline: str
    image_subline: str
    alt_text: str
    #: One short, arresting string set very large by the Split template.
    display_token: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "image_headline": self.image_headline,
            "image_subline": self.image_subline,
            "display_token": self.display_token,
            "alt_text": self.alt_text,
        }


#: The Split template sets this at ~200px; anything longer is unreadable.
MAX_TOKEN_CHARS = 12


def _clean_token(raw: Any, topic: str) -> str:
    """One short string for the Split template's colour block.

    A model that returns a sentence gets its first word instead — truncating
    mid-word would put a fragment on a poster at 200px.
    """
    text = " ".join(str(raw or "").split())
    if text and len(text) <= MAX_TOKEN_CHARS:
        return text
    for word in (*text.split(), *topic.split()):
        if len(word) <= MAX_TOKEN_CHARS:
            return word
    return ""


def _strip_hashtags(caption: str) -> str:
    """Hashtags are a separate field. A model that inlines them anyway would
    otherwise double them up under the caption box in the Desk."""
    cleaned = re.sub(r"(?:(?<=\s)|^)#\S+", "", caption)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


async def build_brief(session: AsyncSession, job: ContentJob) -> dict[str, Any]:
    """Everything the writer prompt needs about this topic."""
    trend = await session.get(Trend, job.trend_id)
    if trend is None:
        raise ContentError(f"topic {job.trend_id} no longer exists")
    if trend.safety_flag == SafetyFlag.skip.value:
        # The curator marked this disaster/death/communal/election-result.
        raise ContentError(
            "This topic is flagged as one we do not market against, so the "
            "studio will not generate for it."
        )

    items = (
        await session.scalars(
            select(TrendItem).where(TrendItem.trend_id == trend.id).order_by(TrendItem.rank)
        )
    ).all()
    evidence = "\n".join(f"- [{i.source.value}] {i.title}" for i in items[:8]) or "- (none)"

    return {
        "trend": trend,
        "brand_name": job.brand.name,
        "brand_voice": job.brand.voice_prompt or "Plain, confident, no hype.",
        "topic": trend.topic,
        "summary": trend.summary or "No summary available; work from the headlines below.",
        "known_hashtags": ", ".join(trend.hashtags) or "(none)",
        "evidence": evidence,
        "language": job.language.value,
    }


async def write_post(llm: LLMProvider, brief: dict[str, Any]) -> Post:
    if not llm.is_configured():
        raise ContentError("Gemini is not configured, so captions cannot be written.")

    prompt = render_prompt(
        PROMPT_ID,
        brand_name=brief["brand_name"],
        brand_voice=brief["brand_voice"],
        topic=brief["topic"],
        summary=brief["summary"],
        known_hashtags=brief["known_hashtags"],
        evidence=brief["evidence"],
        language=brief["language"],
    )

    try:
        result = await llm.generate_json(
            prompt_id=PROMPT_ID, prompt=prompt, schema=WRITE_SCHEMA, temperature=0.7
        )
    except LLMError as exc:
        raise ContentError(f"The writer call failed: {exc}") from exc

    data = result.data if isinstance(result.data, dict) else {}
    caption = _strip_hashtags(str(data.get("caption") or ""))
    if not caption:
        raise ContentError("The writer returned an empty caption.")

    return Post(
        hook=str(data.get("hook") or "").strip(),
        caption=caption,
        hashtags=clean_hashtags(data.get("hashtags"), HASHTAG_COUNT),
        image_headline=str(data.get("image_headline") or brief["topic"]).strip(),
        image_subline=str(data.get("image_subline") or "").strip(),
        display_token=_clean_token(data.get("display_token"), brief["topic"]),
        alt_text=str(data.get("alt_text") or "").strip(),
    )


def render_assets(job: ContentJob, post: Post) -> list[tuple[str, str, bytes, dict[str, Any]]]:
    """Render every requested size in all three templates.

    Three templates rather than one: the marketer picks, and rendering is
    cheap and local. Gemini backgrounds are tried first only when configured,
    and any failure falls back to the flat template with a log line.
    """
    pillow = PillowTemplateProvider()
    gemini = GeminiImageProvider()
    sizes = [s for s in job.formats if s in SIZES] or ["square"]
    out: list[tuple[str, str, bytes, dict[str, Any]]] = []

    for size in sizes:
        for template in TEMPLATES:
            brief = ImageBrief(
                headline=post.image_headline,
                subline=post.image_subline,
                hashtags=post.hashtags,
                brand_name=job.brand.name,
                primary_color=job.brand.primary_color,
                secondary_color=job.brand.secondary_color,
                alt_text=post.alt_text,
                logo_url=job.brand.logo_url,
                size=size,
                template=template,
            )
            if gemini.is_configured():
                try:
                    image = gemini.render(brief)
                    out.append((size, image.template, image.png, image.meta))
                    continue
                except Exception as exc:
                    log.warning(
                        "gemini image failed, using flat template",
                        job_id=job.id,
                        template=template,
                        error=f"{type(exc).__name__}: {exc}"[:200],
                    )

            image = pillow.render(brief)
            out.append(
                (
                    size,
                    image.template,
                    image.png,
                    {**image.meta, "width": image.width, "height": image.height},
                )
            )

    return out


async def run_job(job_id: int) -> dict[str, Any]:
    """Drive one job to completion. Never raises: failure lands on the row."""
    llm = get_llm()

    async with SessionLocal() as session:
        job = await session.get(ContentJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}

        job.status = JobStatus.writing
        job.error = None
        job.started_at = utcnow()
        await session.commit()

        try:
            brief = await build_brief(session, job)
            post = await write_post(llm, brief)

            # Replace any previous output, but keep a caption a human edited.
            for asset in list(job.assets):
                if not (asset.kind is AssetKind.caption and asset.edited):
                    await session.delete(asset)

            session.add(
                ContentAsset(
                    job_id=job.id,
                    kind=AssetKind.caption,
                    variant=job.language.value,
                    meta_json=post.as_dict(),
                )
            )

            job.status = JobStatus.rendering
            await session.commit()

            for size, template, png, meta in render_assets(job, post):
                key = f"jobs/{job.id}/{size}-{template}.png"
                url = put_png(key, png)
                session.add(
                    ContentAsset(
                        job_id=job.id,
                        kind=AssetKind.image,
                        variant=f"{size}:{template}",
                        url=url,
                        meta_json={**meta, "size": size, "template": template},
                    )
                )

            job.status = JobStatus.ready
            job.finished_at = utcnow()
            await session.commit()
            log.info("job ready", job_id=job.id, language=job.language.value)
            return {"job_id": job.id, "status": job.status.value}

        except Exception as exc:
            await session.rollback()
            job = await session.get(ContentJob, job_id)
            if job is not None:
                job.status = JobStatus.failed
                # Verbatim: the Desk shows this and offers "Try again".
                job.error = (
                    str(exc)
                    if isinstance(exc, ContentError)
                    else (f"{type(exc).__name__}: {exc}")[:500]
                )
                job.finished_at = utcnow()
                await session.commit()
            log.warning("job failed", job_id=job_id, error=f"{type(exc).__name__}: {exc}"[:300])
            return {"job_id": job_id, "status": "failed"}


async def _main(job_ids: list[str]) -> None:
    for raw in job_ids:
        print(json.dumps(await run_job(int(raw)), indent=2))
    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    import sys

    asyncio.run(_main(sys.argv[1:]))
