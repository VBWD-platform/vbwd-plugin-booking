"""Bookable resources as a cms sitemap provider (registry v2, S154 P2).

Implements the duck-typed cms contract — ``name``, ``count()``,
``page(offset, limit)`` — over PUBLIC resources at ``/booking/<slug>``, with
``lastmod`` from ``updated_at``. Paging happens in SQL (the repository's
``COUNT`` + ``ORDER BY id OFFSET/LIMIT``); no full load, no per-row query.

This module never imports cms: the plugin wiring root injects cms's
``SitemapEntry`` class as ``entry_factory`` (cms is an OPTIONAL dependency, D3),
so booking's source stays cms-free and its isolated unit CI needs no cms.
The ``seo_index_resources`` switch is read on every call (admin changes apply
without restart); OFF means count 0 and empty pages.
"""
from typing import Any, Callable, List

from plugins.booking.booking.constants import public_resource_path
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
)
from plugins.booking.booking.services.plugin_config import (
    resources_indexing_enabled,
)

# Part of the public chunk URL ``/sitemap-booking-resources-<n>.xml`` — never rename.
SITEMAP_PROVIDER_NAME = "booking-resources"


class BookingResourceSitemapProvider:
    """Sitemap entries for the bookable resources the public catalogue shows."""

    name = SITEMAP_PROVIDER_NAME

    def __init__(
        self,
        resource_repository_factory: Callable[[], ResourceRepository],
        entry_factory: Callable[..., Any],
        is_indexing_enabled: Callable[[], bool] = resources_indexing_enabled,
    ) -> None:
        self._resource_repository_factory = resource_repository_factory
        self._entry_factory = entry_factory
        self._is_indexing_enabled = is_indexing_enabled

    def count(self) -> int:
        if not self._is_indexing_enabled():
            return 0
        return self._resource_repository_factory().count_public_resources()

    def page(self, offset: int, limit: int) -> List[Any]:
        if not self._is_indexing_enabled():
            return []
        rows = self._resource_repository_factory().list_public_resource_slugs(
            offset, limit
        )
        return [
            self._entry_factory(
                loc=public_resource_path(slug),
                lastmod=updated_at.isoformat() if updated_at else None,
            )
            for slug, updated_at in rows
        ]
