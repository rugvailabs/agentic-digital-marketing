"""The reel pipeline: script -> voice -> frames -> mix -> store.

One job moves queued -> writing -> voicing -> rendering -> ready, or stops at
failed with a message a user can act on. The status is on the row rather than
inferred, so the Desk can poll one endpoint and a crashed worker leaves
evidence.

`voicing` sits before `rendering` because the voiceover is what decides how
many frames there are. Narrate first, measure, then render exactly that long —
the other order leaves you choosing between a clipped last word and a held
frame, and both read as a broken render.

Nothing here returns a silent reel. If the narration fails, the job fails and
says why: a silent video looks finished, which is the worst way for this to go
wrong.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.images.fonts import script_of
from app.llm import get_llm
from app.models import (
    AssetKind,
    ContentAsset,
    ContentJob,
    JobKind,
    JobStatus,
    Trend,
)
from app.storage import put_bytes
from app.tasks.content import ContentError, build_brief
from app.tts.edge import EdgeTTSProvider, TTSError
from app.video import SIZES, VideoError
from app.video.ffmpeg import FFmpegError
from app.video.music import pick as pick_bed
from app.video.mux import mux
from app.video.remotion import RemotionVideoProvider
from app.video.script import ReelScript, ScriptError, write_script
from app.video.timing import brief_from, narrate

log = get_logger("video.job")

#: Reel sizes we render. A request for a post size falls back to the reel.
REEL_SIZES = ("reel",)


async def reel_brief(session: AsyncSession, job: ContentJob) -> dict[str, Any]:
    """The writer's brief, plus what the composition needs about the topic."""
    brief = await build_brief(session, job)
    trend: Trend | None = brief.get("trend")
    region = trend.region if trend and trend.region else None
    brief["region_name"] = region.name if region else ""
    brief["velocity"] = [float(v) for v in (trend.velocity or [])] if trend else []
    # Curator tags only: `derive_script` publishes these as written, so the
    # raw column would put a camel-cased source headline on a reel.
    brief["hashtags"] = trend.curator_hashtags if trend else []
    return brief


async def run_reel(job_id: int, sessions: Any = None) -> dict[str, Any]:
    """Drive one reel to completion. Never raises: failure lands on the row."""
    factory = sessions or SessionLocal
    llm = get_llm()
    tts = EdgeTTSProvider()
    renderer = RemotionVideoProvider()

    async with factory() as session:
        job = await session.get(ContentJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        if job.kind is not JobKind.reel:
            return {"job_id": job_id, "status": "not a reel"}

        job.status = JobStatus.writing
        job.error = None
        job.started_at = utcnow()
        await session.commit()

        try:
            if not tts.is_configured():
                raise ContentError(
                    "Voiceover is switched off (TTS_ENABLED), so a reel cannot be narrated."
                )
            if not renderer.is_configured():
                raise ContentError("No renderer is configured, so reels cannot be rendered.")

            brief = await reel_brief(session, job)
            script = await write_script(llm, brief)

            # Replace any previous output. Nothing here is hand-editable yet,
            # so there is no equivalent of the caption's `edited` guard.
            for asset in list(job.assets):
                await session.delete(asset)
            session.add(
                ContentAsset(
                    job_id=job.id,
                    kind=AssetKind.script,
                    variant=job.language.value,
                    meta_json=script.as_dict(),
                )
            )
            await session.commit()

            job.status = JobStatus.voicing
            await session.commit()

            narration = await narrate(tts, script, job.language)
            voice_url = await _store_voice(job, narration)

            job.status = JobStatus.rendering
            await session.commit()

            size = next((f for f in job.formats if f in SIZES), "reel")
            video_brief = brief_from(
                script,
                narration,
                brand_name=job.brand.name,
                primary_color=job.brand.primary_color,
                secondary_color=job.brand.secondary_color,
                size=size,
                region_name=brief["region_name"],
                velocity=brief["velocity"],
                script_name=script_of(f"{script.headline} {script.segments[0].say}"),
                logo_url=job.brand.logo_url,
            )
            rendered = await renderer.render(video_brief)

            bed = pick_bed(seed=f"job-{job.id}")
            mixed = await mux(rendered.mp4, narration, bed=bed)

            key = f"jobs/{job.id}/{size}-{video_brief.template}.mp4"
            url = put_bytes(key, mixed.mp4, "video/mp4")
            poster_url = (
                put_bytes(f"jobs/{job.id}/{size}-poster.jpg", mixed.poster, "image/jpeg")
                if mixed.poster
                else None
            )
            session.add(
                ContentAsset(
                    job_id=job.id,
                    kind=AssetKind.video,
                    variant=f"{size}:{video_brief.template}",
                    url=url,
                    meta_json={
                        "size": size,
                        "template": video_brief.template,
                        "width": rendered.width,
                        "height": rendered.height,
                        "fps": rendered.fps,
                        "duration_seconds": round(mixed.duration_seconds, 2),
                        "audio_codec": mixed.audio_codec,
                        "audio_channels": mixed.audio_channels,
                        "has_music": mixed.has_music,
                        "voice": narration.voice,
                        "poster_url": poster_url,
                        "alt_text": script.alt_text,
                        "label": "Reel" if size == "reel" else "Square video",
                    },
                )
            )

            job.status = JobStatus.ready
            job.finished_at = utcnow()
            await session.commit()
            log.info(
                "reel ready",
                job_id=job.id,
                seconds=round(mixed.duration_seconds, 2),
                voice=narration.voice,
                music=mixed.has_music,
            )
            return {
                "job_id": job.id,
                "status": job.status.value,
                "seconds": round(mixed.duration_seconds, 2),
                "audio": mixed.audio_codec,
                "voice_url": voice_url,
            }

        except Exception as exc:
            await session.rollback()
            await _fail(factory, job_id, exc)
            return {"job_id": job_id, "status": "failed"}


async def _store_voice(job: ContentJob, narration: Any) -> str:
    """Keep the narration as its own asset.

    Two reasons: a user can listen to it without the video, and a re-render
    that only changes the look does not have to call the voice service again.
    """
    from app.video.ffmpeg import FFmpegError as _FFmpegError  # noqa: F401  (re-raised below)

    joined = b"".join(card.speech.audio for card in narration.cards)
    key = f"jobs/{job.id}/voice.mp3"
    return put_bytes(key, joined, "audio/mpeg")


#: Failures a user can act on, shown verbatim. Anything else is a bug and is
#: shown with its type so it can be found in the logs.
LEGIBLE = (ContentError, ScriptError, TTSError, VideoError, FFmpegError, ValueError)


async def _fail(factory: Any, job_id: int, exc: Exception) -> None:
    async with factory() as session:
        job = await session.get(ContentJob, job_id)
        if job is None:
            return
        job.status = JobStatus.failed
        job.error = str(exc) if isinstance(exc, LEGIBLE) else f"{type(exc).__name__}: {exc}"[:500]
        job.finished_at = utcnow()
        await session.commit()
    log.warning("reel failed", job_id=job_id, error=f"{type(exc).__name__}: {exc}"[:300])


def describe(script: ReelScript) -> str:
    """One line for a log or a CLI. Not used by the pipeline."""
    beats = len(script.beats)
    return f"{script.headline[:48]!r} in {beats} beats{' (derived)' if script.derived else ''}"
