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
from typing import Any, List, Optional

from vbwd.services.data_exchange.base_model_exchanger import BaseModelExchanger
from vbwd.services.data_exchange.port import (
    CLUSTER_SALES,
    EntityExchanger,
)
from vbwd.services.data_exchange.registry import data_exchange_registry

# Existing booking permissions (single source — BookingPlugin.admin_permissions).
PERM_BOOKINGS_VIEW = "booking.bookings.view"
PERM_BOOKINGS_MANAGE = "booking.bookings.manage"


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


def build_booking_exchangers(session: Any) -> List[EntityExchanger]:
    """Construct the booking exchangers bound to ``session``."""
    from plugins.booking.booking.models.booking import Booking

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
            view_permission=PERM_BOOKINGS_VIEW,
            manage_permission=PERM_BOOKINGS_MANAGE,
        ),
    ]


def register_booking_exchangers(session: Any) -> None:
    """Register the booking exchangers into the registry (idempotent).

    Called from ``BookingPlugin.on_enable``. Re-registering replaces by key, so
    a repeat enable (per-test app) is clear-safe.
    """
    for exchanger in build_booking_exchangers(session):
        data_exchange_registry.register(exchanger)
