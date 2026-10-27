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
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import SessionLocal, engine
from app.llm import LLMError, LLMProvider, get_llm
from app.models import (
    ContentJob,
    PipelineStatus,
    Region,
    RegionKind,
    SafetyFlag,
    SourceName,
    Trend,
    TrendItem,
    TrendPlatform,
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

#: Weight given to this run's centroid when blending with the stored one.
CENTROID_ALPHA = 0.3

PROMPT_ID = "curate_v3"

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
            # Per-platform tags. Declared as named properties rather than a
            # free-form map: Gemini's responseSchema has no additionalProperties,
            # so an OBJECT with no properties comes back empty every time.
            # Google Trends and News are deliberately absent — nobody posts
            # there, so a hashtag for them has no audience.
            "platform_hashtags": {
                "type": "OBJECT",
                "properties": {
                    "youtube": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "reddit": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "x": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "instagram": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
            "why_trending": {"type": "STRING"},
            "relevance_to_region": {"type": "NUMBER"},
        },
        "required": [
            "cluster_id",
            "title",
            "category",
            "hashtags",
            "summary",
            "safety_flag",
            "drop",
            "why_trending",
            "relevance_to_region",
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
            region_kind=region.kind.value.replace("_", " "),
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
        return {
            "items": 0,
            "clusters": 0,
            "multi_source": 0,
            "carried": 0,
            "dropped": 0,
            "merged": 0,
            "stranded": 0,
        }

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


def item_key(source: str, url: str | None, title: str) -> str:
    """A stable name for one source item.

    The URL where there is one: the same article is the same article however
    often a model rewrites the headline above it. Trends keywords have no URL,
    so they fall back to a hash of the normalised keyword, which is equally
    stable because the keyword *is* the item.
    """
    if url and url.strip():
        return f"{source}:{url.strip()}"
    # sha1 names an item here; it is not hashing a secret.
    digest = hashlib.sha1(
        normalise_topic(title).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
    return f"{source}:h{digest}"


def member_key(row: RawRow) -> str:
    return item_key(row.source.value, row.url, row.title)


def cluster_member_keys(cluster: Any, rows: list[RawRow]) -> set[str]:
    return {member_key(rows[i]) for i in cluster.members}


def evidence_member_keys(row: Trend) -> set[str]:
    """Member keys for a row written before the column existed.

    Every curated row already records the items it was built from, in
    `evidence`, so the keys do not have to be backfilled by a migration or
    guessed at: they can be derived from the row itself, with the same function
    that names a live item. Without this, the first run after the change finds
    nothing to match against and the matching degrades to exact titles — which
    is the behaviour the whole mechanism replaces.
    """
    keys = set()
    for item in row.evidence or ():
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        title = str(item.get("title") or "")
        if not source or not (item.get("url") or title.strip()):
            continue
        keys.add(item_key(source, item.get("url"), title))
    return keys


def new_topic_id() -> str:
    """A durable id minted once per topic and carried forward on every match."""
    return uuid.uuid4().hex[:16]


def _usable(vector: list[float] | None) -> list[float] | None:
    """Vectors only count when they are real embeddings.

    The no-LLM path builds one-hot title vectors whose width is the number of
    distinct titles, so they are neither comparable across runs nor valid for
    a Vector(768) column.
    """
    if not vector or len(vector) != settings.gemini_embed_dim:
        return None
    return list(vector)


def blend_centroid(
    previous: list[float] | None, observed: list[float] | None, alpha: float = CENTROID_ALPHA
) -> list[float] | None:
    """Exponential moving average of a topic's centroid.

    A topic's meaning drifts as the story develops — the first day's headlines
    are not the third day's. Replacing the centroid each run snaps identity to
    whatever was published most recently; keeping the first one freezes it. An
    EMA lets it move at the speed the story moves.
    """
    if observed is None:
        return previous
    if previous is None or len(previous) != len(observed):
        return list(observed)
    return [
        alpha * now + (1 - alpha) * before for now, before in zip(observed, previous, strict=True)
    ]


@dataclass(slots=True)
class Match:
    """One existing row a cluster might be a continuation of."""

    row: Trend
    overlap: int
    cosine: float
    reason: str

    @property
    def sort_key(self) -> tuple[int, float]:
        return (self.overlap, self.cosine)


def find_matches(
    *,
    keys: set[str],
    centroid: list[float] | None,
    topic_key: str,
    rows: list[Trend],
    claimed: set[int],
    threshold: float,
    has_content: set[int],
) -> list[Match]:
    """Every unclaimed row this cluster could be a continuation of, best first.

    Three rules in order of how much they prove:

    1. **Shared source items.** If this cluster and that row both contain the
       same article, they are the same story — nothing a model writes can
       change that. This is the rule that makes identity durable.
    2. **Centroid.** For a run where membership churned completely but the
       story is the same.
    3. **Exact title.** The last resort, and the only one available to rows
       that predate member keys.

    A row carrying content outranks one that does not at equal evidence: the
    whole point is that a generated post keeps its topic.
    """
    # Guarded here rather than trusted from the caller: cosine() raises on a
    # width mismatch, and the no-LLM path builds one-hot title vectors as wide
    # as the run has distinct titles.
    centroid = _usable(centroid)
    matches: list[Match] = []

    for row in rows:
        if id(row) in claimed:
            continue

        overlap = len(keys & set(row.member_keys or ()))
        if overlap:
            matches.append(Match(row, overlap, 0.0, "member_keys"))

    if matches:
        matches.sort(key=lambda m: (m.sort_key, id(m.row) in has_content), reverse=True)
        return matches

    if centroid:
        scored: list[Match] = []
        for row in rows:
            if id(row) in claimed:
                continue
            vector = _usable(row.embedding)
            if vector is None:
                continue
            score = cosine(centroid, vector)
            if score >= threshold:
                scored.append(Match(row, 0, score, "centroid"))
        if scored:
            scored.sort(key=lambda m: (m.cosine, id(m.row) in has_content), reverse=True)
            return scored[:1]

    for row in rows:
        if id(row) not in claimed and row.topic_key == topic_key:
            return [Match(row, 0, 0.0, "title")]

    return []


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


def _history_strength(row: Trend) -> tuple[int, float]:
    """How much velocity history a row is carrying."""
    series = [float(v) for v in (row.velocity or [])]
    return (sum(1 for v in series if v > 0), max(series, default=0.0))


async def _absorb(
    session: AsyncSession, *, winner: Trend | None, loser: Trend, with_content: set[int]
) -> None:
    """Fold a duplicate row into the row that won the match.

    Content jobs move first: a post must never be left pointing at a row that
    is about to disappear. The winner takes the union of both member key sets
    — that is what stops the two drifting apart again — the earlier
    first_seen_at, and whichever velocity history is longer, because the
    sparkline should show the story's life rather than the fork's.
    """
    if winner is None or winner is loser:
        return

    moved_jobs = loser.id in with_content
    if moved_jobs:
        await session.execute(
            update(ContentJob).where(ContentJob.trend_id == loser.id).values(trend_id=winner.id)
        )
        with_content.discard(loser.id)
        with_content.add(winner.id)

    winner.member_keys = sorted(set(winner.member_keys or ()) | set(loser.member_keys or ()))
    earlier = loser.first_seen_at and (
        not winner.first_seen_at or loser.first_seen_at < winner.first_seen_at
    )
    if earlier:
        winner.first_seen_at = loser.first_seen_at
    if _history_strength(loser) > _history_strength(winner):
        winner.velocity = list(loser.velocity or [])

    log.info(
        "merged duplicate topic",
        kept=winner.topic_key[:60],
        absorbed=loser.topic_key[:60],
        moved_jobs=moved_jobs,
    )
    await session.delete(loser)
    # Flushed here, not left pending: SQLAlchemy orders deletes after updates
    # within one flush, so a winner that is about to be reworded into the
    # title the loser still holds would hit uq_trends_region_id_topic_key
    # before the delete that frees it. Which is not hypothetical — a merge
    # usually happens precisely because the two rows describe one story under
    # near-identical titles.
    await session.flush()


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

    # Rows carrying a generated post are the ones identity exists to protect,
    # so they are tracked by id and never dropped, merged away or duplicated.
    with_content = set(
        (
            await session.scalars(
                select(ContentJob.trend_id).where(
                    ContentJob.trend_id.in_([t.id for t in existing_rows if t.id])
                )
            )
        ).all()
    )
    has_content = {id(t) for t in existing_rows if t.id in with_content}

    # Rows from before member_keys existed start empty, which would leave them
    # matchable by title alone on this one run — long enough to fork every
    # topic on the board. Seeding from their own evidence costs nothing and
    # makes the change retroactive.
    seeded = 0
    for prior in existing_rows:
        if not prior.member_keys:
            derived = evidence_member_keys(prior)
            if derived:
                prior.member_keys = sorted(derived)
                seeded += 1
    if seeded:
        log.info("seeded member keys from evidence", region=region.code, rows=seeded)

    scored: list[tuple[float, Any, dict[str, Any]]] = []
    pool = len(rows)
    dropped = 0
    irrelevant = 0
    for cluster in clusters:
        fields = described.get(cluster.key) or fallback_fields(cluster, rows)
        if fields.get("drop") or not str(fields.get("title") or "").strip():
            # The curator judged this a bare search keyword with no evidence
            # behind it — "weather", "news". A dropped cluster beats a board
            # row that says nothing.
            dropped += 1
            continue

        relevance = _clean_relevance(fields.get("relevance_to_region"))
        if not keeps_region_relevance(region.kind, relevance):
            # A national story that merely surfaced in this region's trends.
            # Kept out rather than ranked low: a state board of national
            # cricket and Bollywood is the failure this number exists for.
            irrelevant += 1
            continue

        score = sum(rows[i].rank_points(pool) for i in cluster.members) * 100
        scored.append((round(score, 2), cluster, fields))
    scored.sort(key=lambda s: (-s[0], s[1].key))

    seen: set[str] = set()
    claimed: set[int] = set()
    #: id(row) -> (row, {platform: tags}). Applied after the flush, when the
    #: rows have ids to key trend_sources on.
    authored_tags: dict[int, tuple[Trend, dict[SourceName, list[str]]]] = {}
    multi_source = 0
    carried = 0
    merged = 0
    stranded = 0

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

        # Not `keys` — that is the per-item cluster assignment parameter.
        cluster_keys = cluster_member_keys(cluster, rows)
        centroid = _usable(cluster.centroid)
        matches = find_matches(
            keys=cluster_keys,
            centroid=centroid,
            topic_key=topic_key,
            rows=existing_rows,
            claimed=claimed,
            threshold=settings.topic_match_similarity,
            has_content=has_content,
        )
        row = matches[0].row if matches else None

        # Several rows sharing source items with this cluster means earlier
        # runs forked one story. Fold them into the winner now rather than
        # leaving the board to show the same thing three times.
        duplicates = [m.row for m in matches[1:] if m.reason == "member_keys"]
        for loser in duplicates:
            await _absorb(session, winner=row, loser=loser, with_content=with_content)
            existing_rows.remove(loser)
            by_key.pop(loser.topic_key, None)
            has_content.discard(id(loser))
            if row is not None and row.id in with_content:
                # The winner may have taken on the loser's post, which later
                # clusters in this run need to know when they break a tie.
                has_content.add(id(row))
            merged += 1

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
                matched_on=matches[0].reason if matches else "new",
                overlap=matches[0].overlap if matches else 0,
            )

        claimed.add(id(row))
        if row not in existing_rows:
            existing_rows.append(row)
        by_key.pop(row.topic_key, None)
        row.topic_key = topic_key
        by_key[topic_key] = row

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
        authored_tags[id(row)] = (row, platform_hashtags_of(fields))
        row.why_trending = _one_line(fields.get("why_trending"))
        row.relevance_to_region = _clean_relevance(fields.get("relevance_to_region"))
        row.safety_flag = _clean_flag(fields.get("safety_flag"))
        row.cluster_id = row.cluster_id or new_topic_id()
        # Unioned, never replaced: a run that happens to see only two of a
        # topic's five articles must not forget the other three.
        row.member_keys = sorted(set(row.member_keys or ()) | cluster_keys)
        # Blended, not overwritten, so identity drifts with the story.
        row.embedding = blend_centroid(_usable(row.embedding), centroid)
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
                    cluster_id=row.cluster_id,
                    embedding=_usable(vectors[index]) if vectors else None,
                )
            )

    authored = await _apply_platform_hashtags(session, authored_tags)

    for row in existing_rows:
        if id(row) in claimed:
            continue
        if row.id in with_content:
            # Never silently: a topic carrying a post that finds no match this
            # run keeps its row and drops to rank 0, and says so. Recreating it
            # as a parallel row is the failure this whole mechanism exists to
            # prevent.
            stranded += 1
            log.warning(
                "topic with content found no match",
                region=region.code,
                topic=row.topic_key[:60],
                member_keys=len(row.member_keys or ()),
            )
        if row.rank != 0:
            row.rank = 0
            row.velocity = next_velocity(row.velocity, 0.0)

    return {
        "items": len(rows),
        "clusters": len(clusters),
        "multi_source": multi_source,
        "carried": carried,
        "dropped": dropped,
        "irrelevant": irrelevant,
        "authored_platform_tags": authored,
        "merged": merged,
        "stranded": stranded,
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


#: Below this a story is not about the region, it merely surfaced there.
#: Applied to states, union territories and cities, never to the country —
#: on India's own board a national story genuinely is local.
RELEVANCE_FLOOR = 0.3


def keeps_region_relevance(kind: RegionKind, relevance: float | None) -> bool:
    """Whether a topic is local enough for this region's board.

    A separate function because it is the one piece of v3 that decides what a
    user sees, and it has two cases that are easy to get backwards.

    The country keeps everything: on India's own board a national story is
    local, so the floor would be throwing away the best rows.

    An unscored topic is kept. `None` means the curator did not answer — the
    fallback path when the LLM is unconfigured or over budget, or a model that
    skipped the field — and treating that as 0.0 would empty every state board
    the moment Gemini was unavailable. The degrade-gracefully rule in this
    module's docstring is the whole point: the board must never be worse than
    step 1.
    """
    if kind is RegionKind.country or relevance is None:
        return True
    return relevance >= RELEVANCE_FLOOR


async def _apply_platform_hashtags(
    session: AsyncSession,
    authored: dict[int, tuple[Trend, dict[SourceName, list[str]]]],
) -> int:
    """Overwrite `trend_sources.hashtags` where the curator wrote tags for a
    platform. Returns the number of rows updated.

    The curator wins over the adapter for the same reason it wins on the
    topic's own hashtags: the adapter scrapes whatever was in a title, and the
    curator chose tags for this story on this platform. Where it said nothing
    the scraped tags stay.

    Updates only. A platform the curator named but which has no row did not
    report this story, and inventing a row for it would mean inventing a rank
    and a volume. In practice that is Instagram, which has no row until a user
    opens the topic and `measure()` creates one — so its tags land on the next
    curate rather than this one, and the Desk reads a missing row as "not
    measured yet".
    """
    updated = 0
    for row, by_platform in authored.values():
        if not by_platform or row.id is None:
            continue
        for platform, tags in by_platform.items():
            result = await session.execute(
                update(TrendPlatform)
                .where(TrendPlatform.trend_id == row.id, TrendPlatform.platform == platform)
                .values(hashtags=tags)
            )
            # CursorResult carries rowcount; the base Result protocol does not,
            # which is all mypy can see through session.execute().
            updated += int(getattr(result, "rowcount", 0) or 0)
    return updated


def _one_line(raw: Any, limit: int = 160) -> str | None:
    """Collapse to a single line. None where the model said nothing."""
    text = " ".join(str(raw or "").split())
    return text[:limit] or None


def _clean_relevance(raw: Any) -> float | None:
    """0-1, or None when the model gave nothing usable.

    None rather than a default, because every default is a lie here: 0.0
    would drop the row and 1.0 would keep it, and neither is a judgement the
    curator made. A null is read downstream as "not scored".
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN, which float() accepts from "nan"
        return None
    return round(min(1.0, max(0.0, value)), 2)


def platform_hashtags_of(fields: dict[str, Any]) -> dict[SourceName, list[str]]:
    """The curator's per-platform tags, keyed by platform.

    Only platforms it actually answered for, and only tags that survive the
    same length cap as the topic's own. An empty list is dropped rather than
    stored: it would overwrite the adapter's scraped tags with nothing.
    """
    raw = fields.get("platform_hashtags")
    if not isinstance(raw, dict):
        return {}

    out: dict[SourceName, list[str]] = {}
    for key, value in raw.items():
        try:
            platform = SourceName(str(key))
        except ValueError:
            continue
        tags = [t for t in clean_hashtags(value, 5) if len(t) <= MAX_HASHTAG_CHARS]
        if tags:
            out[platform] = tags
    return out


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
        "merged": 0,
        "stranded": 0,
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
            for key in (
                "items",
                "clusters",
                "multi_source",
                "carried",
                "dropped",
                "merged",
                "stranded",
            ):
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
