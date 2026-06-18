"""Booking resource search provider (cross-entity search seam).

Contributes bookable resources to the core ``search_provider_registry`` so the
``/search`` bot can find them. The resource repository has no full-text search,
so this provider runs a simple case-insensitive name/description/slug filter
over ACTIVE resources (public, non-personal fields only). The public fe-user
detail route is ``/booking/<slug>``.
"""
from __future__ import annotations

from typing import List, Optional

from vbwd.services.search import SearchHit

ENTITY_TYPE = "booking_resource"
ENTITY_LABEL = "Booking"
DETAIL_URL_TEMPLATE = "/booking/{slug}"


class BookingResourceSearchProvider:
    """A ``SearchProvider`` for active bookable resources."""

    entity_type: str = ENTITY_TYPE
    entity_label: str = ENTITY_LABEL

    def search(self, query: str, *, limit: int = 5) -> List[SearchHit]:
        if not query or not query.strip():
            return []
        from sqlalchemy import or_
        from vbwd.extensions import db
        from plugins.booking.booking.models.resource import BookableResource

        pattern = f"%{query.strip()}%"
        resources = (
            db.session.query(BookableResource)
            .filter(
                BookableResource.is_active.is_(True),
                or_(
                    BookableResource.name.ilike(pattern),
                    BookableResource.description.ilike(pattern),
                    BookableResource.slug.ilike(pattern),
                ),
            )
            .order_by(BookableResource.sort_order, BookableResource.name)
            .limit(limit)
            .all()
        )
        return [self._to_hit(resource) for resource in resources]

    def get_detail(self, key: str) -> Optional[SearchHit]:
        from vbwd.extensions import db
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )

        repository = ResourceRepository(db.session)
        resource = repository.find_by_slug(key)
        if resource is None:
            resource = self._find_by_id(repository, key)
        if resource is None:
            return None
        return self._to_hit(resource)

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _find_by_id(repository, key: str):
        try:
            return repository.find_by_id(key)
        except Exception:  # noqa: BLE001 — a non-uuid key is simply "not found"
            return None

    def _to_hit(self, resource) -> SearchHit:
        return SearchHit(
            entity_type=self.entity_type,
            entity_label=self.entity_label,
            key=resource.slug,
            title=resource.name,
            snippet=self._snippet(resource.description),
            url=DETAIL_URL_TEMPLATE.format(slug=resource.slug),
            price=_format_price(resource.price),
        )

    @staticmethod
    def _snippet(description: Optional[str], *, max_length: int = 160) -> str:
        if not description:
            return ""
        text = description.strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip() + "…"


def _format_price(amount: Optional[float]) -> Optional[str]:
    """A best-effort display string ``"<amount> <currency>"`` (no client math)."""
    if amount is None:
        return None
    from vbwd.services.core_settings_store import get_default_currency

    # Reads the operating currency (file-backed; degrades to the schema default
    # on its own — never a call-site literal, never raises).
    currency = get_default_currency()
    return f"{float(amount):.2f} {currency}"
