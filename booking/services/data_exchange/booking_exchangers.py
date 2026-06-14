"""Booking entity exchangers for the S46 data-exchange seam (S46.6).

Exposes booking reservations through the core ``EntityExchanger`` contract so
they appear on the generic Settings → Import/Export page and the per-list
controls — coexisting with the existing booking admin export/import services
(which produce CSV *reports* keyed on resource/category, a different shape).

Entity:

* ``bookings`` (``Booking``, natural key ``id``) — import+export.

  Natural key note (flagged): the ``Booking`` model has **no** human booking
  reference column — its only stable identifier is the UUID ``id``. So this
  exchanger is a same-instance backup/restore (export → wipe → import by ``id``
  reproduces the row, including its ``resource_id`` / ``user_id`` /
  ``invoice_id`` FKs, which remain valid on the same instance). Cross-instance
  portability would require a real booking reference; out of scope for v1.

Design notes:

* **Reused perms** — the plugin already ships ``booking.bookings.view`` /
  ``booking.bookings.manage``; the exchanger maps ``export_permission`` /
  ``import_permission`` onto those (single source of truth).
* **PII** — the customer's name/email/phone/company are resolved on the fly from
  the ``User`` / ``UserDetails`` rows (not stored on the booking), so the
  exported row carries no customer PII columns. The free-text ``notes`` /
  ``admin_notes`` may hold customer-entered text, so they are declared
  ``pii_fields`` and redacted unless the caller holds the PII permission.
* **DRY** — reuses :class:`BaseModelExchanger`; only the narrow
  ``_SessionModelRepository`` adapter is added (mirrors core / CMS).
* **No core change** — registration happens in ``BookingPlugin.on_enable``
  through the shared ``db.session``; core imports no ``plugins.*`` module.

Engineering requirements (binding, restated): TDD-first; DevOps-first; SOLID
(one exchanger, narrow port); DI (session injected); DRY; Liskov; clean code;
no overengineering. Quality guard: ``bin/pre-commit-check.sh --plugin booking
--full``.
"""
from decimal import Decimal
from typing import Any, List, Optional

from vbwd.services.data_exchange.base_model_exchanger import BaseModelExchanger
from vbwd.services.data_exchange.port import (
    CLUSTER_SALES,
    EntityExchanger,
    ImportResult,
)
from vbwd.services.data_exchange.registry import data_exchange_registry

# Existing booking permissions (single source — BookingPlugin.admin_permissions).
PERM_BOOKINGS_VIEW = "booking.bookings.view"
PERM_BOOKINGS_MANAGE = "booking.bookings.manage"
PERM_RESOURCES_VIEW = "booking.resources.view"
PERM_RESOURCES_MANAGE = "booking.resources.manage"


class _SessionModelRepository:
    """Narrow model repo satisfying the ``BaseModelExchanger`` contract.

    Mirrors core's / CMS's adapter: the booking repository exposes domain
    finders rather than the four flat methods the base exchanger needs (ISP).
    """

    def __init__(self, session: Any, model_class: type, natural_key: str) -> None:
        self._session = session
        self._model_class = model_class
        self._natural_key = natural_key

    def find_all(self) -> List[Any]:
        return self._session.query(self._model_class).all()

    def find_by_natural_key(self, value: Any) -> Optional[Any]:
        column = getattr(self._model_class, self._natural_key)
        return self._session.query(self._model_class).filter(column == value).first()

    def add(self, instance: Any) -> None:
        self._session.add(instance)

    def delete_all(self) -> None:
        self._session.query(self._model_class).delete()


class _PermissionMappedModelExchanger(BaseModelExchanger):
    """A ``BaseModelExchanger`` whose perms map onto existing booking perms.

    Selector matching (including the UUID ``id`` natural key) is handled by the
    base ``_select_rows``, which stringifies both sides and matches primary id
    OR natural key — so no selection override is needed here.
    """

    def __init__(
        self,
        *,
        view_permission: str,
        manage_permission: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._view_permission = view_permission
        self._manage_permission = manage_permission

    @property
    def export_permission(self) -> str:
        return self._view_permission

    @property
    def import_permission(self) -> str:
        return self._manage_permission


class _BookingCategoryExchanger(_PermissionMappedModelExchanger):
    """``booking_categories`` carrying the self-referential parent by slug.

    ``BaseModelExchanger.fk_natural_key_map`` is export-only, so the
    self-referential ``parent_id`` cannot round-trip through it: a slug must be
    resolved back to the (possibly different) local id on import. This thin
    subclass exports ``parent_slug`` instead of ``parent_id`` and resolves it on
    row-apply, skipping with an error row if the parent slug is unknown — never
    crashing the whole import (Liskov: the base import contract is preserved).
    """

    def _serialise_row(self, row: Any, *, include_pii: bool) -> dict:
        result = super()._serialise_row(row, include_pii=include_pii)
        parent = getattr(row, "parent", None)
        result["parent_slug"] = parent.slug if parent is not None else None
        return result

    def _import_row(
        self, row: dict, index: int, result: ImportResult, *, dry_run: bool
    ) -> None:
        parent_slug = row.get("parent_slug")
        scalar_row = {key: value for key, value in row.items() if key != "parent_slug"}
        parent_id = None
        if parent_slug:
            parent = self._repository.find_by_natural_key(parent_slug)
            if parent is None:
                result.errors.append(
                    {
                        "row": index,
                        "reason": f"unknown parent_slug '{parent_slug}'",
                    }
                )
                return
            parent_id = parent.id
        scalar_row["parent_id"] = parent_id
        super()._import_row(scalar_row, index, result, dry_run=dry_run)


class _BookingResourceExchanger(_PermissionMappedModelExchanger):
    """``booking_resources`` carrying the resource↔category M2M by slug.

    Exports ``category_slugs`` (the resource's category slugs) alongside the
    scalar/JSON fields and resolves them back to local category ids on import.
    A ``price`` Decimal is serialised as a string (mirroring the model's
    ``to_dict``). An unknown category slug records an error row and skips that
    resource without crashing the import (Liskov).
    """

    def _serialise_row(self, row: Any, *, include_pii: bool) -> dict:
        result = super()._serialise_row(row, include_pii=include_pii)
        if isinstance(result.get("price"), Decimal):
            result["price"] = str(result["price"])
        result["category_slugs"] = [category.slug for category in row.categories]
        return result

    def _import_row(
        self, row: dict, index: int, result: ImportResult, *, dry_run: bool
    ) -> None:
        category_slugs = row.get("category_slugs") or []
        categories = []
        for category_slug in category_slugs:
            category = self._category_repository.find_by_natural_key(category_slug)
            if category is None:
                result.errors.append(
                    {
                        "row": index,
                        "reason": f"unknown category_slug '{category_slug}'",
                    }
                )
                return
            categories.append(category)

        scalar_row = {
            key: value for key, value in row.items() if key != "category_slugs"
        }
        if "price" in scalar_row and scalar_row["price"] is not None:
            scalar_row["price"] = Decimal(str(scalar_row["price"]))

        before = result.created + result.updated
        super()._import_row(scalar_row, index, result, dry_run=dry_run)
        if dry_run or (result.created + result.updated) == before:
            return
        instance = self._repository.find_by_natural_key(scalar_row[self.natural_key])
        if instance is not None:
            instance.categories = categories

    def __init__(self, *, category_repository: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._category_repository = category_repository


def build_booking_exchangers(session: Any) -> List[EntityExchanger]:
    """Construct the booking exchangers bound to ``session``."""
    from plugins.booking.booking.models.booking import Booking
    from plugins.booking.booking.models.resource import BookableResource
    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )

    category_repository = _SessionModelRepository(
        session, BookableResourceCategory, "slug"
    )

    return [
        _PermissionMappedModelExchanger(
            entity_key="bookings",
            label="Bookings",
            cluster=CLUSTER_SALES,
            natural_key="id",
            model_class=Booking,
            repository=_SessionModelRepository(session, Booking, "id"),
            session=session,
            public_fields=[
                "id",
                "resource_id",
                "user_id",
                "invoice_id",
                "start_at",
                "end_at",
                "status",
                "quantity",
                "custom_fields",
                "notes",
                "admin_notes",
            ],
            pii_fields=frozenset({"notes", "admin_notes"}),
            supported_formats=frozenset({"json", "csv"}),
            view_permission=PERM_BOOKINGS_VIEW,
            manage_permission=PERM_BOOKINGS_MANAGE,
        ),
        _BookingCategoryExchanger(
            entity_key="booking_categories",
            label="Booking Categories",
            cluster=CLUSTER_SALES,
            natural_key="slug",
            model_class=BookableResourceCategory,
            repository=category_repository,
            session=session,
            public_fields=[
                "name",
                "slug",
                "description",
                "image_url",
                "config",
                "sort_order",
                "is_active",
            ],
            view_permission=PERM_RESOURCES_VIEW,
            manage_permission=PERM_RESOURCES_MANAGE,
        ),
        _BookingResourceExchanger(
            entity_key="booking_resources",
            label="Booking Resources",
            cluster=CLUSTER_SALES,
            natural_key="slug",
            model_class=BookableResource,
            repository=_SessionModelRepository(session, BookableResource, "slug"),
            category_repository=category_repository,
            session=session,
            public_fields=[
                "name",
                "slug",
                "description",
                "capacity",
                "slot_duration_minutes",
                "price",
                "price_unit",
                "availability",
                "custom_fields_schema",
                "image_url",
                "config",
                "is_active",
                "sort_order",
            ],
            view_permission=PERM_RESOURCES_VIEW,
            manage_permission=PERM_RESOURCES_MANAGE,
        ),
    ]


def register_booking_exchangers(session: Any) -> None:
    """Register the booking exchangers into the registry (idempotent).

    Called from ``BookingPlugin.on_enable``. Re-registering replaces by key, so
    a repeat enable (per-test app) is clear-safe.
    """
    for exchanger in build_booking_exchangers(session):
        data_exchange_registry.register(exchanger)
