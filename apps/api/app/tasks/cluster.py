"""Greedy agglomerative clustering over embedding vectors.

Pure functions, no I/O: everything here is deterministic given the vectors, so
the clustering can be tested on a fixture without a model or a database.

Greedy single-pass rather than k-means or HDBSCAN: the input is 50-100 short
titles per region, the cluster count is unknown in advance, and the ordering is
meaningful (sources arrive in rank order, so the strongest item seeds its
cluster). It is O(n·k) and finishes in microseconds at this size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Vector = list[float]


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector rather than dividing."""
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = na = nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def centroid(vectors: list[Vector]) -> Vector:
    if not vectors:
        return []
    width = len(vectors[0])
    out = [0.0] * width
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    return [x / len(vectors) for x in out]


@dataclass(slots=True)
class Cluster:
    """A group of raw items judged to be the same story."""

    key: str
    members: list[int] = field(default_factory=list)
    centroid: Vector = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)


def cluster_vectors(
    vectors: list[Vector],
    *,
    threshold: float,
    prefix: str = "c",
) -> list[Cluster]:
    """Group indices whose vectors exceed `threshold` cosine similarity.

    An item joins the single best-matching cluster above the threshold, and the
    centroid is recomputed as it grows — so a cluster drifts toward its members
    rather than staying anchored to whichever item happened to arrive first.
    Items that match nothing become their own cluster; a singleton is a normal
    outcome, not a failure.
    """
    clusters: list[Cluster] = []

    for index, vector in enumerate(vectors):
        if not vector:
            # No embedding (the call failed for this item): never merge on
            # missing data, give it its own cluster.
            clusters.append(Cluster(key=f"{prefix}{len(clusters):03d}", members=[index]))
            continue

        best: Cluster | None = None
        best_score = threshold
        for candidate in clusters:
            if not candidate.centroid:
                continue
            score = cosine(vector, candidate.centroid)
            if score >= best_score:
                best, best_score = candidate, score

        if best is None:
            clusters.append(
                Cluster(key=f"{prefix}{len(clusters):03d}", members=[index], centroid=list(vector))
            )
        else:
            best.members.append(index)
            best.centroid = centroid([vector, best.centroid])

    return clusters


def assignments(clusters: list[Cluster], total: int) -> list[str]:
    """Cluster key per input index, for writing back onto rows."""
    out = [""] * total
    for cluster in clusters:
        for member in cluster.members:
            out[member] = cluster.key
    return out
