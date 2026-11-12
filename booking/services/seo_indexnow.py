"""IndexNow ping for booking resources (S154 D4) — cms stays optional.

Calls cms's stable ``ping_indexnow_urls`` seam through a lazy import (a silent
no-op when cms is absent or not enabled), mirroring the optional-dependency
pattern the booking sitemap provider already uses for the sitemap registry
(D3). The public path is built from the SAME ``public_resource_path`` helper
the sitemap provider uses (DRY — never recomputed), gated by the resource
type's own fe-admin "indexable" switch (D7) — the identical switch the
sitemap provider checks.

``notify_resource_changed`` covers one row (create/update/delete, including
the ``is_active`` toggle, which is just one more field of an update);
``notify_resources_changed`` batches several rows into ONE IndexNow POST for
the existing bulk-copy route (D4 batching).
"""
import logging
from typing import Iterable, List

from plugins.booking.booking.constants import public_resource_path
from plugins.booking.booking.services.plugin_config import (
    resources_indexing_enabled,
)

logger = logging.getLogger(__name__)


def _import_ping_indexnow_urls():
    """cms's stable IndexNow ping seam (raises ``ImportError`` without cms)."""
    from plugins.cms.src.services.seo_wiring import ping_indexnow_urls

    return ping_indexnow_urls


def _ping_many(paths: List[str]) -> None:
    """Best-effort: a missing cms or a failing ping never breaks the caller."""
    try:
        ping_indexnow_urls = _import_ping_indexnow_urls()
    except ImportError:
        return
    try:
        ping_indexnow_urls(paths)
    except Exception as exc:  # pragma: no cover - defensive, best-effort
        logger.warning("[booking.indexnow] ping failed for %s: %s", paths, exc)


def notify_resource_changed(slug: str) -> None:
    """Ping IndexNow of a changed resource's public URL (switch-gated, D7)."""
    if not slug or not resources_indexing_enabled():
        return
    _ping_many([public_resource_path(slug)])


def notify_resources_changed(slugs: Iterable[str]) -> None:
    """Ping IndexNow once for several changed resources (switch-gated, D7).

    For the existing bulk-copy route: one HTTP request in, one IndexNow POST
    out, never one per row.
    """
    if not resources_indexing_enabled():
        return
    paths = [public_resource_path(slug) for slug in (slugs or []) if slug]
    if not paths:
        return
    _ping_many(paths)
