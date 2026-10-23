"""The curator: embed raw items, cluster them, have Gemini name each cluster.

This is what closes the step-1 merge gap. The non-LLM merge deduped by
normalised title, so a Google Trends keyword ("eng vs sl") and a news headline
about the same match never met and every topic read as single-source. Here the
join happens in embedding space, so one topic carries every source that saw it.

Degrading is deliberate: if Gemini is unconfigured or fails, the clusters are
still written and each one falls back to its best member's title, so the board
is never worse than step 1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.llm import LLMError, LLMProvider, get_llm
from app.models import (
    PipelineStatus,
    Region,
    SafetyFlag,
    SourceName,
    Trend,
    TrendItem,
    TrendSnapshot,
)
from app.prompts import render_prompt
from app.tasks.cluster import assignments, cluster_vectors, cosine
from app.tasks.merge import (
    clean_hashtags,
    display_topic,
    hashtags_for,
    next_velocity,
    normalise_topic,
)

log = get_logger("curate")

PROMPT_ID = "curate_v2"

#: Short, mutually exclusive, and sized for a 420px ladder chip. "Other" is
#: last in the list and last in the prompt's order of preference.
CATEGORIES = [
    "Sports",
    "Politics",
    "Business",
    "Entertainment",
    "Technology",
    "Weather",
    "Civic",
    "Festival",
    "Education",
    "Health",
    "Crime",
    "Other",
]
FALLBACK_CATEGORY = "Other"

#: A curator hashtag is a handle, not a headline: CamelCase of one to three
#: words, at most this many characters including the "#".
MAX_HASHTAG_CHARS = 20

#: Response schema handed to Gemini. Keeping it strict is what makes the output
#: safe to write straight into the database.
CURATE_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "cluster_id": {"type": "STRING"},
            "title": {"type": "STRING"},
            "category": {"type": "STRING", "enum": CATEGORIES},
            "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
            "summary": {"type": "STRING"},
            "safety_flag": {"type": "STRING", "enum": ["none", "sensitive", "skip"]},
            "drop": {"type": "BOOLEAN"},
        },
        "required": [
            "cluster_id",
            "title",
            "category",
            "hashtags",
            "summary",
            "safety_flag",
            "drop",
        ],
    },
}

#: Source weights, mirrored from the adapters so scoring survives a failed call.
SOURCE_WEIGHT = {
    SourceName.google_trends: 1.0,
    SourceName.x: 0.8,
    SourceName.google_news: 0.7,
    SourceName.youtube: 0.6,
}


@dataclass(slots=True)
class RawRow:
    """One raw item pulled out of a snapshot, before clustering."""

    source: SourceName
    snapshot_id: int
    rank: int
    title: str
    url: str | None
    volume: int | None
    extra: dict[str, Any]

    @property
    def weight(self) -> float:
        return SOURCE_WEIGHT.get(self.source, 0.5)

    def rank_points(self, pool: int) -> float:
        if pool <= 0:
            return 0.0
        return max(0.0, (pool - self.rank + 1) / pool) * self.weight


async def latest_rows(session: AsyncSession, region: Region) -> tuple[str, list[RawRow]]:
    """Every item from the most recent ingest run for this region."""
    run_id = await session.scalar(
        select(TrendSnapshot.run_id)
        .where(TrendSnapshot.region_id == region.id)
        .order_by(TrendSnapshot.captured_at.desc())
        .limit(1)
    )
    if not run_id:
        return "", []

    snapshots = (
        await session.scalars(
            select(TrendSnapshot).where(
                TrendSnapshot.region_id == region.id, TrendSnapshot.run_id == run_id
            )
        )
    ).all()

    rows: list[RawRow] = []
    for snapshot in snapshots:
        for item in snapshot.items:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            rows.append(
                RawRow(
                    source=snapshot.source,
                    snapshot_id=snapshot.id,
                    rank=int(item.get("rank") or 0),
                    title=title,
                    url=item.get("url"),
                    volume=item.get("volume"),
                    extra=dict(item.get("extra") or {}),
                )
            )
    return str(run_id), rows


def describe_clusters(clusters: list, rows: list[RawRow]) -> str:
    """The cluster block pasted into the prompt."""
    blocks: list[str] = []
    for cluster in clusters:
        lines = [f"### {cluster.key}"]
        for index in cluster.members[:8]:
            row = rows[index]
            bits = [f"- [{row.source.value} #{row.rank}] {row.title}"]
            publisher = row.extra.get("publisher") or row.extra.get("channel")
            if publisher:
                bits.append(f"  publisher: {publisher}")
            related = row.extra.get("related")
            if related:
                bits.append(f"  related queries: {', '.join(map(str, related[:6]))}")
            lines.extend(bits)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def describe_with_llm(
    llm: LLMProvider, region: Region, clusters: list, rows: list[RawRow]
) -> dict[str, dict[str, Any]]:
    """Ask Gemini to name each cluster. Returns {cluster_key: fields}."""
    described: dict[str, dict[str, Any]] = {}
    batch_size = max(1, settings.curate_batch_size)

    for start in range(0, len(clusters), batch_size):
        batch = clusters[start : start + batch_size]
        prompt = render_prompt(
            PROMPT_ID,
            region_name=region.name,
            region_code=region.code,
            cluster_count=len(batch),
            clusters=describe_clusters(batch, rows),
        )
        result = await llm.generate_json(
            prompt_id=PROMPT_ID, prompt=prompt, schema=CURATE_SCHEMA, temperature=0.2
        )
        entries = result.data if isinstance(result.data, list) else []
        for entry in entries:
            key = str(entry.get("cluster_id") or "")
            if key:
                described[key] = entry
        if len(entries) < len(batch):
            # A short array means the model dropped clusters; those fall back
            # to their source title rather than vanishing from the board.
            log.warning(
                "partial batch",
                region=region.code,
                asked=len(batch),
                got=len(entries),
                model=result.call.model,
            )
        log.info(
            "clusters described",
            region=region.code,
            batch=len(batch),
            described=len(entries),
            total_tokens=result.call.total_tokens,
            latency_ms=result.call.latency_ms,
        )

    return described


def fallback_fields(cluster: Any, rows: list[RawRow]) -> dict[str, Any]:
    """What a cluster looks like with no model involved.

    Used when Gemini is unconfigured or the call failed. The board stays
    exactly as good as step 1 rather than going blank.
    """
    members = sorted(cluster.members, key=lambda i: (-rows[i].weight, rows[i].rank))
    best = rows[members[0]]
    return {
        "title": display_topic(best.title),
        "category": _clean_category(best.extra.get("category")),
        "hashtags": hashtags_for(best.title),
        "summary": None,
        "safety_flag": SafetyFlag.none.value,
    }


async def curate_region(session: AsyncSession, region: Region, llm: LLMProvider) -> dict[str, int]:
    """Re-curate one region's board from its latest snapshot."""
    run_id, rows = await latest_rows(session, region)
    if not rows:
        log.info("nothing to curate", region=region.code)
        return {"items": 0, "clusters": 0, "multi_source": 0, "carried": 0, "dropped": 0}

    vectors: list[list[float]] = []
    if llm.is_configured():
        try:
            embedded = await llm.embed(prompt_id="curate_embed", texts=[r.title for r in rows])
            vectors = embedded.vectors
        except LLMError as exc:
            log.warning("embedding failed, falling back to title match", error=str(exc)[:200])
    else:
        log.info("llm not configured, clustering by normalised title", region=region.code)

    if not vectors:
        # No embeddings: fall back to step 1's behaviour so clustering still
        # groups exact title matches rather than making every item a singleton.
        vectors = _title_match_vectors(rows)

    clusters = cluster_vectors(vectors, threshold=settings.cluster_similarity, prefix="c")
    keys = assignments(clusters, len(rows))

    described: dict[str, dict[str, Any]] = {}
    if llm.is_configured():
        try:
            described = await describe_with_llm(llm, region, clusters, rows)
        except LLMError as exc:
            log.warning(
                "curation failed, using source titles", region=region.code, error=str(exc)[:200]
            )

    stats = await _write(session, region, run_id, rows, clusters, keys, described, vectors)
    await session.commit()
    log.info("region curated", region=region.code, **stats)
    return stats


def topic_identity(cluster: Any, rows: list[RawRow]) -> str:
    """A stable id for the story a cluster is about.

    Derived from the *source* title of the cluster's most trusted member, not
    from the curated title. The curated title is written fresh by the model
    every run — "Rafale Marine trials underway in Goa" one cycle, "Rafale
    Marine fighter begins flight trials in Goa" the next — so keying a topic on
    it spawns a second row and strands the first one's content jobs. The
    underlying headline does not move.
    """
    members = sorted(cluster.members, key=lambda i: (-rows[i].weight, rows[i].rank))
    anchor = normalise_topic(rows[members[0]].title) if members else cluster.key
    # sha1 is a shortener here, not a security primitive: this names a topic.
    return hashlib.sha1(anchor.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _usable(vector: list[float] | None) -> list[float] | None:
    """Vectors only count when they are real embeddings.

    The no-LLM path builds one-hot title vectors whose width is the number of
    distinct titles, so they are neither comparable across runs nor valid for
    a Vector(768) column.
    """
    if not vector or len(vector) != settings.gemini_embed_dim:
        return None
    return list(vector)


def match_existing(
    *,
    identity: str,
    topic_key: str,
    centroid: list[float] | None,
    by_identity: dict[str, Trend],
    by_key: dict[str, Trend],
    with_vectors: list[tuple[Trend, list[float]]],
    claimed: set[int],
    threshold: float,
) -> Trend | None:
    """The row this cluster is a continuation of, if any.

    Three rules, strongest first: the same story identity, then a centroid that
    is all but the same vector, then an identical title. Each candidate must be
    unclaimed — two clusters in one run must never collide on one row.
    """
    candidate = by_identity.get(identity)
    if candidate is not None and id(candidate) not in claimed:
        return candidate

    if centroid:
        best: Trend | None = None
        best_score = threshold
        for row, vector in with_vectors:
            if id(row) in claimed:
                continue
            score = cosine(centroid, vector)
            if score >= best_score:
                best, best_score = row, score
        if best is not None:
            return best

    candidate = by_key.get(topic_key)
    if candidate is not None and id(candidate) not in claimed:
        return candidate

    return None


def _title_match_vectors(rows: list[RawRow]) -> list[list[float]]:
    """One-hot vectors over normalised titles: identical titles cluster, nothing
    else does. Keeps the no-LLM path equivalent to the step-1 merge."""
    keys: dict[str, int] = {}
    for row in rows:
        keys.setdefault(normalise_topic(row.title), len(keys))
    width = max(1, len(keys))
    vectors = []
    for row in rows:
        vec = [0.0] * width
        vec[keys[normalise_topic(row.title)]] = 1.0
        vectors.append(vec)
    return vectors


async def _write(
    session: AsyncSession,
    region: Region,
    run_id: str,
    rows: list[RawRow],
    clusters: list,
    keys: list[str],
    described: dict[str, dict[str, Any]],
    vectors: list[list[float]],
) -> dict[str, int]:
    now = utcnow()

    # trend_items is a projection of the latest run, so replace it wholesale
    # rather than trying to reconcile row by row.
    await session.execute(delete(TrendItem).where(TrendItem.region_id == region.id))

    existing_rows = list(
        (await session.scalars(select(Trend).where(Trend.region_id == region.id))).all()
    )
    by_key = {t.topic_key: t for t in existing_rows}
    by_identity = {t.cluster_id: t for t in existing_rows if t.cluster_id}
    with_vectors = [
        (t, vector) for t in existing_rows if (vector := _usable(t.embedding)) is not None
    ]

    scored: list[tuple[float, Any, dict[str, Any]]] = []
    pool = len(rows)
    dropped = 0
    for cluster in clusters:
        fields = described.get(cluster.key) or fallback_fields(cluster, rows)
        if fields.get("drop") or not str(fields.get("title") or "").strip():
            # The curator judged this a bare search keyword with no evidence
            # behind it — "weather", "news". A dropped cluster beats a board
            # row that says nothing.
            dropped += 1
            continue
        score = sum(rows[i].rank_points(pool) for i in cluster.members) * 100
        scored.append((round(score, 2), cluster, fields))
    scored.sort(key=lambda s: (-s[0], s[1].key))

    seen: set[str] = set()
    claimed: set[int] = set()
    multi_source = 0
    carried = 0

    for position, (score, cluster, fields) in enumerate(scored, start=1):
        members = cluster.members
        sources: list[str] = []
        for index in members:
            value = rows[index].source.value
            if value not in sources:
                sources.append(value)
        if len(sources) > 1:
            multi_source += 1

        # display_topic is a no-op on anything already containing a capital,
        # so it enforces the prompt's casing rule without overriding a title
        # the model deliberately cased ("ENG vs SL"). The model does not always
        # apply the rule itself.
        title = display_topic(str(fields.get("title") or "").strip() or rows[members[0]].title)
        topic_key = normalise_topic(title) or cluster.key
        if topic_key in seen:
            # Two clusters named identically: keep them apart rather than
            # violating the (region, topic_key) unique constraint.
            topic_key = f"{topic_key} {cluster.key}"
        seen.add(topic_key)

        identity = topic_identity(cluster, rows)
        centroid = _usable(cluster.centroid)
        row = match_existing(
            identity=identity,
            topic_key=topic_key,
            centroid=centroid,
            by_identity=by_identity,
            by_key=by_key,
            with_vectors=with_vectors,
            claimed=claimed,
            threshold=settings.topic_match_similarity,
        )

        # (region, topic_key) is unique, so taking a key another row still
        # physically holds would fail on flush. If that row is free, it is the
        # better match anyway — an identical title is the strongest evidence
        # two rows are one topic. If it is already claimed this run, the two
        # clusters genuinely collide and have to stay apart.
        holder = by_key.get(topic_key)
        if holder is not None and holder is not row:
            if id(holder) not in claimed:
                row = holder
            else:
                topic_key = f"{topic_key} {cluster.key}"
                seen.add(topic_key)

        if row is None:
            row = Trend(
                region_id=region.id,
                topic_key=topic_key,
                first_seen_at=now,
            )
            session.add(row)
        elif row.topic_key != topic_key:
            # The model reworded it. Same row, new title — which is the whole
            # point: content jobs hang off trend_id and must not be stranded.
            carried += 1
            log.info(
                "topic renamed",
                region=region.code,
                was=row.topic_key[:60],
                now=topic_key[:60],
                matched_on="identity" if by_identity.get(identity) is row else "centroid",
            )

        claimed.add(id(row))
        by_key.pop(row.topic_key, None)
        row.topic_key = topic_key
        by_key[topic_key] = row
        by_identity[identity] = row

        row.topic = title
        row.category = _clean_category(fields.get("category"))
        row.rank = position
        row.score = score
        row.volume = max((rows[i].volume or 0) for i in members)
        row.velocity = next_velocity(row.velocity, score)
        row.hashtags = _clean_hashtags(fields.get("hashtags"), title)
        row.sources = sources
        row.evidence = [
            {
                "source": rows[i].source.value,
                "rank": rows[i].rank,
                "title": rows[i].title,
                "url": rows[i].url,
                **{
                    k: v
                    for k, v in rows[i].extra.items()
                    if k in {"publisher", "published", "channel", "thumbnail"}
                },
            }
            for i in members[:12]
        ]
        row.summary = fields.get("summary")
        row.safety_flag = _clean_flag(fields.get("safety_flag"))
        # The stable story id, not the within-run position, so the next run can
        # find this row again.
        row.cluster_id = identity
        row.embedding = centroid
        row.status = PipelineStatus.curated
        row.curated_at = now
        row.last_seen_at = now

        await session.flush()

        for index in members:
            raw = rows[index]
            session.add(
                TrendItem(
                    trend_id=row.id,
                    region_id=region.id,
                    snapshot_id=raw.snapshot_id,
                    source=raw.source,
                    run_id=run_id,
                    rank=raw.rank,
                    title=raw.title,
                    url=raw.url,
                    volume=raw.volume,
                    extra=raw.extra,
                    cluster_id=identity,
                    embedding=_usable(vectors[index]) if vectors else None,
                )
            )

    for row in existing_rows:
        if id(row) not in claimed and row.rank != 0:
            row.rank = 0
            row.velocity = next_velocity(row.velocity, 0.0)

    return {
        "items": len(rows),
        "clusters": len(clusters),
        "multi_source": multi_source,
        "carried": carried,
        "dropped": dropped,
    }


def _clean_hashtags(raw: Any, title: str) -> list[str]:
    """Curator hashtags are handles, not headlines.

    The model occasionally camel-cases the entire title —
    #RafaleMarineFighterBeginsFlightTrials — which is unusable on any network
    and dwarfs the Desk heading. Anything over MAX_HASHTAG_CHARS is dropped
    rather than truncated, because a truncated hashtag is a different word.
    """
    tags = [t for t in clean_hashtags(raw, 12) if len(t) <= MAX_HASHTAG_CHARS]
    if not tags:
        # Nothing usable: build short ones from the title instead of leaving a
        # topic tagless.
        tags = [t for t in hashtags_for(title) if len(t) <= MAX_HASHTAG_CHARS]
    return tags[:6]


def _clean_category(raw: Any) -> str:
    """Every topic carries a category; an unrecognised one becomes Other."""
    value = str(raw or "").strip()
    return value if value in CATEGORIES else FALLBACK_CATEGORY


def _clean_flag(raw: Any) -> str:
    try:
        return SafetyFlag(str(raw)).value
    except ValueError:
        # An unexpected value is treated as the cautious option, not as none.
        return SafetyFlag.sensitive.value


async def run_curate(region_codes: list[str] | None = None, sessions: Any = None) -> dict[str, Any]:
    """Curate the named regions, or the configured default set."""
    codes = region_codes or settings.curate_region_list
    llm = get_llm()
    factory = sessions or SessionLocal
    totals = {
        "regions": 0,
        "items": 0,
        "clusters": 0,
        "multi_source": 0,
        "carried": 0,
        "dropped": 0,
    }

    async with factory() as session:
        regions = (
            await session.scalars(
                select(Region).where(Region.code.in_(codes)).order_by(Region.sort_order)
            )
        ).all()
        for region in regions:
            stats = await curate_region(session, region, llm)
            totals["regions"] += 1
            for key in ("items", "clusters", "multi_source", "carried", "dropped"):
                totals[key] += stats[key]

    log.info("curate finished", **totals, llm_configured=llm.is_configured())
    return totals


async def _main(codes: list[str]) -> None:
    result = await run_curate(codes or None)
    print(json.dumps(result, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    import sys

    asyncio.run(_main(sys.argv[1:]))
