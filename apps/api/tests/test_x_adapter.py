"""The source registry, and XAdapter's region coverage against real seeds.

Its fetch behaviour moved to test_x_trends.py when the stub became real. What
stays here is what needs the seeded region fixtures — which regions have a
WOEID to pull, directly or through their cities — and the registry's own
shape.
"""

from __future__ import annotations

from app.models import SourceName
from app.sources import all_sources, configured_source_names, source_weights
from app.sources.base import TrendSource
from app.sources.x import XAdapter


def test_supports_regions_that_have_woeids(india, maharashtra, mumbai, ladakh) -> None:
    adapter = XAdapter(bearer_token="token")
    assert adapter.supports(india)  # own WOEID
    assert adapter.supports(mumbai)  # own WOEID
    assert not adapter.supports(maharashtra)  # rolls up from cities, none loaded here
    assert not adapter.supports(ladakh)


def test_registry_exposes_every_source_and_its_weight() -> None:
    sources = all_sources()

    assert [s.name for s in sources] == [
        SourceName.google_trends,
        SourceName.google_news,
        SourceName.youtube,
        SourceName.reddit,
        SourceName.x,
        SourceName.instagram,
    ]
    assert all(isinstance(s, TrendSource) for s in sources)

    # Keyless sources work on a clean checkout; youtube, reddit and x all
    # need credentials, so a clean checkout has exactly the two.
    assert set(configured_source_names()) >= {"google_trends", "google_news"}
    assert source_weights()["google_trends"] > source_weights()["google_news"]
