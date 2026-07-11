"""Repository for BookableResource."""
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import or_

from vbwd.services.tags_and_custom_fields import (
    resolve_tags_and_custom_fields,
    UnknownEntityTypeError,
)
from plugins.booking.booking.models.resource import BookableResource

# The generic entity-type key booking registers (in ``on_enable``) so its
# resources are taggable through the core tags port. Tag reads/filters go through
# that port only — this module never imports the tags implementation (agnostic).
_BOOKING_RESOURCE_ENTITY_TYPE = "booking_resource"


class ResourceRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self, active_only=True):
        query = self.session.query(BookableResource)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookableResource.sort_order).all()

    def find_by_id(self, resource_id):
        return self.session.get(BookableResource, resource_id)

    def find_by_vendor_id(self, vendor_id):
        return (
            self.session.query(BookableResource)
            .filter_by(vendor_id=vendor_id)
            .order_by(BookableResource.sort_order)
            .all()
        )

    def find_by_slug(self, slug):
        return self.session.query(BookableResource).filter_by(slug=slug).first()

    def find_by_category(self, category_slug, active_only=True):
        query = self.session.query(BookableResource).join(BookableResource.categories)
        from plugins.booking.booking.models.resource_category import (
            BookableResourceCategory,
        )

        query = query.filter(BookableResourceCategory.slug == category_slug)
        if active_only:
            query = query.filter(BookableResource.is_active.is_(True))
        return query.order_by(BookableResource.sort_order).all()

    # ── Catalogue list (S131 — catalogue-list wire contract) ──────────────
    #
    # NOTE: the pre-contract ``find_by_type`` was removed here — it filtered on a
    # non-existent ``resource_type`` column (a latent ``InvalidRequestError``).
    # The ``type`` facet now filters on the linked custom schema's slug via
    # ``_active_query`` (the ``resource_type`` an item actually exposes).

    def _active_query(
        self,
        query: Optional[str],
        category_slug: Optional[str],
        resource_type_slug: Optional[str],
    ):
        """Active-resource query with search + category/type facets applied.

        ``category`` and ``type`` are booking's historically MUTUALLY EXCLUSIVE
        facets: when both are given ``category`` wins (matching the pre-contract
        route's ``if category ... elif type`` precedence). ``type`` filters on the
        linked custom schema's slug (the ``resource_type`` an item exposes). Tags
        are NOT filtered here — they are core-owned and resolved via the port.
        """
        active_query = self.session.query(BookableResource).filter(
            BookableResource.is_active.is_(True)
        )
        if category_slug:
            from plugins.booking.booking.models.resource_category import (
                BookableResourceCategory,
            )

            active_query = active_query.join(BookableResource.categories).filter(
                BookableResourceCategory.slug == category_slug
            )
        elif resource_type_slug:
            from plugins.booking.booking.models.custom_schema import (
                BookingCustomSchema,
            )

            active_query = active_query.join(BookableResource.custom_schema).filter(
                BookingCustomSchema.slug == resource_type_slug
            )
        if query:
            pattern = f"%{query}%"
            active_query = active_query.filter(
                or_(
                    BookableResource.name.ilike(pattern),
                    BookableResource.description.ilike(pattern),
                )
            )
        return active_query.order_by(BookableResource.sort_order, BookableResource.name)

    def list_catalogue(
        self,
        page: int = 1,
        per_page: int = 20,
        query: Optional[str] = None,
        category_slug: Optional[str] = None,
        resource_type_slug: Optional[str] = None,
        tag_slugs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Active resources for the catalogue list, with the EFFECTIVE total.

        Returns ``{"items": [BookableResource], "total": int}`` where ``total``
        counts the rows matching the combined search / category / type / tag
        filter (not the whole active catalogue), so the caller can build a
        correct pagination envelope. Mirrors shop's ``list_catalogue``.
        """
        active_query = self._active_query(query, category_slug, resource_type_slug)
        if tag_slugs:
            matched = self._filter_by_tags(active_query.all(), tag_slugs)
            return self._paginate_list(matched, page, per_page)
        total = active_query.count()
        items = active_query.offset((page - 1) * per_page).limit(per_page).all()
        return {"items": items, "total": total}

    def list_catalogue_candidates(
        self,
        query: Optional[str] = None,
        category_slug: Optional[str] = None,
        resource_type_slug: Optional[str] = None,
        tag_slugs: Optional[List[str]] = None,
    ) -> List[BookableResource]:
        """The FULL filtered candidate set (no pagination) for post-SQL filters.

        The availability facet is computed in Python (real bookable slots), so the
        route must materialise every candidate that passes the SQL + tag filters
        before applying the window and slicing the page.
        """
        candidates = self._active_query(query, category_slug, resource_type_slug).all()
        if tag_slugs:
            return self._filter_by_tags(candidates, tag_slugs)
        return candidates

    @staticmethod
    def _paginate_list(
        items: List[BookableResource], page: int, per_page: int
    ) -> Dict[str, Any]:
        """Slice an in-memory filtered list into ``{items, total}`` (DRY)."""
        total = len(items)
        start = (page - 1) * per_page
        return {"items": items[start : start + per_page], "total": total}

    def _filter_by_tags(
        self, candidates: List[BookableResource], tag_slugs: List[str]
    ) -> List[BookableResource]:
        """Keep resources carrying EVERY requested tag slug (AND semantics).

        Tags cannot be filtered in SQL without a core change (the tag rows are
        core-owned, resolved only through the port), so the candidates are matched
        in Python. Mirrors shop's tag filter.
        """
        tags_by_id = self.list_resource_tags([resource.id for resource in candidates])
        required = set(tag_slugs)
        return [
            resource
            for resource in candidates
            if required.issubset(set(tags_by_id.get(resource.id, [])))
        ]

    def list_resource_tags(self, resource_ids: List[UUID]) -> Dict[UUID, List[str]]:
        """Tag slugs for many resources in ONE query via the core tags port.

        Degrades to an empty map when the tags port has no provider or the
        ``booking_resource`` entity type is unregistered (plugin loaded without
        ``on_enable`` having run): a tag filter then yields no matches and list
        items fall back to empty tags — never a 500. Mirrors shop.
        """
        if not resource_ids:
            return {}
        provider = resolve_tags_and_custom_fields()
        if provider is None:
            return {}
        try:
            return provider.get_tags_bulk(
                _BOOKING_RESOURCE_ENTITY_TYPE, list(resource_ids)
            )
        except UnknownEntityTypeError:
            return {}

    def list_used_resource_tags(self) -> List[Dict[str, Any]]:
        """Tags carried by at least one ACTIVE resource (tag-filter options).

        The filter only offers tags that can actually match a resource, so a
        globally-defined tag no active resource carries is dropped. Degrades to
        ``[]`` when there are no active/tagged resources or the port is
        unavailable — never a 500. Mirrors shop's ``list_used_product_tags``.
        """
        active_ids = [
            row[0]
            for row in self.session.query(BookableResource.id)
            .filter(BookableResource.is_active.is_(True))
            .all()
        ]
        if not active_ids:
            return []
        tags_by_id = self.list_resource_tags(active_ids)
        used_slugs = {slug for slugs in tags_by_id.values() for slug in slugs}
        if not used_slugs:
            return []
        provider = resolve_tags_and_custom_fields()
        if provider is None:
            return []
        try:
            catalog = provider.list_applicable_tags(_BOOKING_RESOURCE_ENTITY_TYPE)
        except UnknownEntityTypeError:
            return []
        return [tag for tag in catalog if tag.get("slug") in used_slugs]

    def save(self, resource):
        self.session.add(resource)
        self.session.flush()
        return resource

    def delete(self, resource):
        self.session.delete(resource)
        self.session.flush()
