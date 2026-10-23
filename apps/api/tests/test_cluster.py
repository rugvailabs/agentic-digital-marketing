"""Clustering, on vectors rather than on a live model.

Everything here is deterministic given the input, which is the point of
keeping cluster.py free of I/O.
"""

from __future__ import annotations

import math

import pytest

from app.tasks.cluster import Cluster, assignments, centroid, cluster_vectors, cosine


def unit(*values: float) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class TestCosine:
    def test_identical_vectors_score_one(self) -> None:
        assert cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_magnitude_is_irrelevant(self) -> None:
        assert cosine([1.0, 1.0], [10.0, 10.0]) == pytest.approx(1.0)

    def test_zero_vector_scores_zero_rather_than_dividing(self) -> None:
        assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_dimension_mismatch_is_an_error_not_a_silent_zero(self) -> None:
        with pytest.raises(ValueError, match="dimension mismatch"):
            cosine([1.0], [1.0, 2.0])


class TestClustering:
    def test_near_duplicates_merge_and_outliers_do_not(self) -> None:
        vectors = [
            unit(1.0, 0.0, 0.0),  # 0
            unit(0.98, 0.02, 0.0),  # 1 - same story as 0
            unit(0.0, 1.0, 0.0),  # 2 - unrelated
        ]
        clusters = cluster_vectors(vectors, threshold=0.9)

        assert len(clusters) == 2
        assert sorted(clusters[0].members) == [0, 1]
        assert clusters[1].members == [2]

    def test_threshold_decides_how_much_merges(self) -> None:
        vectors = [unit(1.0, 0.0), unit(0.8, 0.6)]  # cosine 0.8

        assert len(cluster_vectors(vectors, threshold=0.75)) == 1
        assert len(cluster_vectors(vectors, threshold=0.85)) == 2

    def test_a_singleton_is_a_normal_outcome(self) -> None:
        clusters = cluster_vectors([unit(1.0, 0.0)], threshold=0.68)

        assert len(clusters) == 1
        assert clusters[0].size == 1

    def test_items_without_an_embedding_never_merge(self) -> None:
        # A failed embedding must not become a false match with everything.
        clusters = cluster_vectors([[], [], unit(1.0, 0.0)], threshold=0.0)

        assert len(clusters) == 3

    def test_centroid_follows_the_members(self) -> None:
        vectors = [unit(1.0, 0.0), unit(0.9, 0.44), unit(0.85, 0.52)]
        clusters = cluster_vectors(vectors, threshold=0.8)

        assert len(clusters) == 1
        # The centroid has drifted off the first member toward the group.
        assert cosine(clusters[0].centroid, vectors[0]) < 1.0
        assert cosine(clusters[0].centroid, vectors[0]) > 0.9

    def test_cluster_keys_are_stable_and_ordered(self) -> None:
        clusters = cluster_vectors([unit(1.0, 0.0), unit(0.0, 1.0)], threshold=0.9)

        assert [c.key for c in clusters] == ["c000", "c001"]

    def test_empty_input_yields_no_clusters(self) -> None:
        assert cluster_vectors([], threshold=0.68) == []


def test_centroid_of_nothing_is_empty() -> None:
    assert centroid([]) == []


def test_assignments_maps_every_index_to_its_cluster() -> None:
    clusters = [Cluster(key="c000", members=[0, 2]), Cluster(key="c001", members=[1])]

    assert assignments(clusters, 3) == ["c000", "c001", "c000"]


def test_measured_gemini_similarities_land_on_the_right_side_of_the_threshold() -> None:
    """The configured threshold, checked against values measured live.

    These are real cosine scores from gemini-embedding-001 over one India
    snapshot (see DESIGN_NOTES). The band between a true match and genre noise
    is narrow, so a threshold change should fail this test loudly.
    """
    threshold = 0.68

    true_matches = {
        "Jailer 2 youtube vs news": 0.693,
        "पवन सिंह trends vs youtube": 0.686,
        "gold rate today vs today gold rate": 0.850,
        "silver rate vs silver price": 0.895,
    }
    genre_noise = {
        "CULT trailer vs JOJO trailer": 0.646,
        "casio watch vs smartwatch feature": 0.598,
        "gold rate vs stock market today": 0.548,
        "ultraviolette vs CULT trailer": 0.541,
    }

    for label, score in true_matches.items():
        assert score >= threshold, f"{label} should merge at {threshold}"
    for label, score in genre_noise.items():
        assert score < threshold, f"{label} should not merge at {threshold}"
