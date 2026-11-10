"""BookingResourceSitemapProvider — the cms sitemap v2 contract (S154 P2).

The provider is cms-free: the ``SitemapEntry`` class is injected by the plugin
wiring root, so these tests run without cms (booking's isolated unit CI). The
repository is faked; SQL paging/visibility is covered by the integration test.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from plugins.booking.booking.sitemap_provider import (
    SITEMAP_PROVIDER_NAME,
    BookingResourceSitemapProvider,
)


@dataclass
class FakeSitemapEntry:
    loc: str
    lastmod: Optional[str] = None


class InMemoryPublicResourceRepository:
    """Honours the repository contract: count == length of the paged sequence."""

    def __init__(self, rows: List[Tuple[str, Optional[datetime]]]) -> None:
        self.rows = rows
        self.calls = 0

    def count_public_resources(self) -> int:
        self.calls += 1
        return len(self.rows)

    def list_public_resource_slugs(self, offset: int, limit: int):
        self.calls += 1
        return self.rows[offset : offset + limit]


UPDATED_AT = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)


def _provider(repository, enabled=True):
    return BookingResourceSitemapProvider(
        resource_repository_factory=lambda: repository,
        entry_factory=FakeSitemapEntry,
        is_indexing_enabled=lambda: enabled,
    )


def test_provider_name_is_the_stable_public_chunk_name():
    assert SITEMAP_PROVIDER_NAME == "booking-resources"
    assert _provider(InMemoryPublicResourceRepository([])).name == "booking-resources"


def test_count_is_the_public_resource_count():
    repository = InMemoryPublicResourceRepository(
        [("room-a", UPDATED_AT), ("room-b", None)]
    )

    assert _provider(repository).count() == 2


def test_page_maps_rows_to_booking_resource_urls_with_lastmod():
    repository = InMemoryPublicResourceRepository(
        [("room-a", UPDATED_AT), ("room-b", None)]
    )

    entries = list(_provider(repository).page(0, 10))

    assert entries == [
        FakeSitemapEntry(loc="/booking/room-a", lastmod=UPDATED_AT.isoformat()),
        FakeSitemapEntry(loc="/booking/room-b", lastmod=None),
    ]


def test_pages_walk_exactly_count_entries_in_repository_order():
    rows = [(f"resource-{index:03d}", UPDATED_AT) for index in range(7)]
    provider = _provider(InMemoryPublicResourceRepository(rows))
    page_size = 3

    walked = []
    for offset in range(0, provider.count(), page_size):
        walked.extend(provider.page(offset, page_size))

    assert len(walked) == provider.count()
    assert [entry.loc for entry in walked] == [f"/booking/{slug}" for slug, _ in rows]


def test_switch_off_counts_zero_and_pages_nothing_without_querying():
    repository = InMemoryPublicResourceRepository([("room-a", UPDATED_AT)])
    provider = _provider(repository, enabled=False)

    assert provider.count() == 0
    assert list(provider.page(0, 10)) == []
    assert repository.calls == 0


def test_default_switch_reads_seo_index_resources_from_booking_config(monkeypatch):
    from plugins.booking.booking.services import plugin_config

    monkeypatch.setattr(
        plugin_config, "booking_config", lambda: {"seo_index_resources": False}
    )

    assert plugin_config.resources_indexing_enabled() is False


def test_seo_index_resources_defaults_on():
    from plugins.booking import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["seo_index_resources"] is True
