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

S89.1 (load-test bulk seed) for ``bookings`` — now shipped (Slice B):

``bookings`` does not fit the slug-prefix seam the flat shop/subscription
catalog rows use, for two structural reasons. Both are handled with plugin-side
overrides only — **no core change**:

* ``Booking``'s natural key is the **UUID ``id``**, not a settable slug. The base
  ``bulk_seed`` writes ``loadtest-bookings-<i>`` into the natural-key column and
  matches the ``loadtest-`` prefix for idempotency + ``--reset``; a UUID column
  cannot hold that string. :class:`_BookingsExchanger` overrides
  ``_loadtest_natural_key`` to emit a **deterministic UUID5** (fixed namespace +
  ``loadtest-bookings-<index>``) so the same index always maps to the same id —
  idempotency + ``--reset`` work by id, recomputable for any count.
* A ``Booking`` also requires a non-null ``user_id`` FK into the core
  ``vbwd_user`` table plus a valid ``resource_id`` and time slot. The seed
  provisions **one shared ``loadtest-`` ``BookableResource``** through the
  booking resource repository (no raw SQL) and **reuses an existing user** read
  from the core ``User`` table (the plugin already reads ``vbwd_user`` to
  resolve booking customers — it never *creates* a core user). Load-test
  bookings are identified by their FK to that one resource (a stable, queryable
  marker on a column the model already has), so ``--reset`` drops exactly those
  reservations + the resource when unreferenced, never touching real rows.

Engineering requirements (binding, restated): TDD-first; DevOps-first; SOLID
(one exchanger, narrow port); DI (session injected); DRY; Liskov; clean code;
no overengineering. Quality guard: ``bin/pre-commit-check.sh --plugin booking
--full``.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, List, Optional, Set

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

    # ── heavy-load scale hooks (S89.1) ────────────────────────────────────
    # The base exchanger calls these via ``getattr`` when present so a 100k
    # export/reset is O(batches), not O(N²). Absent → full ``find_all`` scans.
    # These speed the slug-keyed ``booking_resources`` / ``booking_categories``
    # entities. ``bookings`` is UUID-keyed and overrides the load-test
    # identification directly (see :class:`_BookingsExchanger`), so these prefix
    # helpers stay UUID-safe (return empty / 0) for it as a defensive fallback.

    def iter_rows(self, batch_size: int) -> Any:
        """Yield rows in ``yield_per`` pages (bounded memory)."""
        return (
            self._session.query(self._model_class)
            .yield_per(batch_size)
            .enable_eagerloads(False)
        )

    def bulk_add(self, instances: List[Any]) -> None:
        """Insert a batch through the unit of work (one flush per batch).

        Uses ``add_all`` + ``flush`` rather than ``bulk_save_objects`` so any
        relationship-carrying rows (a resource's category M2M) persist; still a
        single flush per batch (O(batches)). The caller commits.
        """
        self._session.add_all(instances)
        self._session.flush()

    def find_natural_keys_with_prefix(self, prefix: str) -> List[Any]:
        """Return natural-key values starting with ``prefix`` (slug-keyed entities).

        For the UUID-keyed ``bookings`` entity the natural key is ``id``, which
        carries no ``loadtest-`` prefix, so this returns nothing there;
        ``bookings`` seed identification is overridden in :class:`_BookingsExchanger`.
        """
        column = getattr(self._model_class, self._natural_key)
        try:
            rows = self._session.query(column).filter(column.like(f"{prefix}%")).all()
        except Exception:
            # A non-text natural key (UUID ``id``) cannot match a string prefix;
            # treat it as "no load-test rows" rather than crashing the caller.
            return []
        return [row[0] for row in rows]

    def delete_natural_keys_with_prefix(self, prefix: str) -> int:
        """Delete every row whose natural key starts with ``prefix``. Returns count.

        Scoped to this model + the ``loadtest-`` prefix, so it never touches
        real/demo data. ``synchronize_session=False`` keeps it one statement
        (the caller commits). A non-text natural key matches nothing (returns 0).
        """
        column = getattr(self._model_class, self._natural_key)
        try:
            return (
                self._session.query(self._model_class)
                .filter(column.like(f"{prefix}%"))
                .delete(synchronize_session=False)
            )
        except Exception:
            return 0


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


class BookingSeedError(Exception):
    """Raised when a ``bookings`` load-test seed cannot satisfy a required FK.

    The only non-synthesisable prerequisite is the ``user_id`` FK: the seed
    reuses an existing core user and never creates one (the agnosticism rule —
    user provisioning is a core concern). If the instance has no user at all,
    the seed stops with this error rather than inventing a core row.
    """


class _BookingsExchanger(_PermissionMappedModelExchanger):
    """``bookings`` load-test seed over the UUID ``id`` natural key (S89.1 Slice B).

    Overrides the seed seam so ``bulk_seed`` produces valid, round-trippable
    reservations without a settable slug:

    * ``_loadtest_natural_key`` → a deterministic UUID5 per index (stable id ⇒
      idempotency + ``--reset`` by id, recomputable for any count).
    * ``_seed_row`` → a valid reservation: the deterministic id, the one shared
      ``loadtest-`` resource, a reused existing user, and a deterministic slot
      ``base + index·slot_duration`` (no overlap → passes reservation rules).
    * load-test rows are identified by their FK to the one ``loadtest-``
      resource (a queryable marker the model already has — no new column), so
      ``_existing_loadtest_keys`` / ``_reset_loadtest_rows`` scope to exactly
      those reservations and never touch real bookings.

    Liskov: the base ``bulk_seed`` contract (idempotent, batched, reset-clean)
    is preserved — only how a load-test row is built + identified changes.
    """

    # Fixed namespace so a given index always maps to the same booking id across
    # processes/runs (idempotency must survive a fresh exchanger / new request).
    _LOADTEST_UUID_NAMESPACE = uuid.UUID("6f1d0c2e-9b3a-4d5e-8a7c-000000000089")

    # One shared load-test resource every seeded reservation references.
    _SEED_RESOURCE_SLUG = "loadtest-bookings-resource"
    _SEED_RESOURCE_NAME = "Load-test bookings resource"
    _SEED_RESOURCE_PRICE = 10.0
    _SEED_RESOURCE_CAPACITY = 1000000

    # A fixed base instant + a fixed slot length; consecutive indices occupy
    # consecutive non-overlapping slots so capacity is never the limiter.
    _SEED_SLOT_BASE = datetime(2030, 1, 1, 0, 0, 0)
    _SEED_SLOT_MINUTES = 30

    # Caches of the one shared resource + the reused user id (``None`` until the
    # first row resolves them). Declared so mypy sees the attributes. Caching
    # keeps a 100k seed at one resource lookup + one user lookup, not O(N).
    _seed_resource: Optional[Any]
    _seed_user_id: Optional[Any]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._seed_resource = None
        self._seed_user_id = None

    # ── seed overrides ─────────────────────────────────────────────────────

    def _loadtest_natural_key(self, index: int) -> str:
        return str(
            uuid.uuid5(self._LOADTEST_UUID_NAMESPACE, f"loadtest-bookings-{index}")
        )

    def _seed_row(self, index: int, natural_value: str) -> dict:
        resource = self._ensure_seed_resource()
        user_id = self._resolve_seed_user_id()
        start_at = self._SEED_SLOT_BASE + timedelta(
            minutes=self._SEED_SLOT_MINUTES * index
        )
        end_at = start_at + timedelta(minutes=self._SEED_SLOT_MINUTES)
        return {
            "id": natural_value,
            "resource_id": resource.id,
            "user_id": user_id,
            "start_at": start_at,
            "end_at": end_at,
            "status": "confirmed",
            "quantity": 1,
        }

    def _existing_loadtest_keys(self) -> Set[str]:
        """Booking ids already attached to the one shared load-test resource.

        No resource yet ⇒ no load-test bookings ⇒ empty set (this never creates
        the resource — that is the lazy job of ``_seed_row``).
        """
        from plugins.booking.booking.models.booking import Booking

        resource = self._find_seed_resource()
        if resource is None:
            return set()
        rows = (
            self._session.query(Booking.id)
            .filter(Booking.resource_id == resource.id)
            .all()
        )
        return {str(row[0]) for row in rows}

    def _reset_loadtest_rows(self) -> int:
        """Drop the load-test reservations, then the resource if now unreferenced.

        Scoped to the one shared ``loadtest-`` resource so a real booking + real
        resource are never touched. The cached resource is cleared so the next
        seed re-creates it cleanly.
        """
        from plugins.booking.booking.models.booking import Booking

        resource = self._find_seed_resource()
        if resource is None:
            self._seed_resource = None
            return 0
        deleted = (
            self._session.query(Booking)
            .filter(Booking.resource_id == resource.id)
            .delete(synchronize_session=False)
        )
        self._drop_seed_resource_if_unreferenced(resource.id)
        self._seed_resource = None
        return deleted

    # ── prerequisites ──────────────────────────────────────────────────────

    def _ensure_seed_resource(self) -> Any:
        """Return the one shared ``loadtest-`` resource, creating it once.

        Created through the booking ``ResourceRepository`` (no raw SQL) and
        cached so a large seed shares one resource + a single lookup. Idempotent:
        an existing resource (this run or a prior seed) is reused.
        """
        if self._seed_resource is not None:
            return self._seed_resource
        from plugins.booking.booking.models.resource import BookableResource
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )

        repository = ResourceRepository(self._session)
        resource = repository.find_by_slug(self._SEED_RESOURCE_SLUG)
        if resource is None:
            resource = BookableResource(
                name=self._SEED_RESOURCE_NAME,
                slug=self._SEED_RESOURCE_SLUG,
                description="Shared resource for load-test bookings (S89.1).",
                capacity=self._SEED_RESOURCE_CAPACITY,
                slot_duration_minutes=self._SEED_SLOT_MINUTES,
                price=self._SEED_RESOURCE_PRICE,
                availability={},
            )
            repository.save(resource)
        self._seed_resource = resource
        return resource

    def _find_seed_resource(self) -> Any:
        from plugins.booking.booking.models.resource import BookableResource

        return (
            self._session.query(BookableResource)
            .filter(BookableResource.slug == self._SEED_RESOURCE_SLUG)
            .first()
        )

    def _resolve_seed_user_id(self) -> Any:
        """Return an existing core user's id to own the load-test reservations.

        Reuses the earliest existing user (deterministic) — the plugin already
        reads ``vbwd_user`` to resolve booking customers; it never *creates* a
        core user (provisioning is a core concern). If the instance has no user
        at all, the seed stops with :class:`BookingSeedError` rather than
        inventing a core row.
        """
        if self._seed_user_id is not None:
            return self._seed_user_id
        from vbwd.models.user import User

        user_id = (
            self._session.query(User.id)
            .order_by(User.created_at.asc())
            .limit(1)
            .scalar()
        )
        if user_id is None:
            raise BookingSeedError(
                "bookings load-test seed needs at least one existing user to own "
                "the reservations (it reuses a user, never creates one); seed/demo "
                "users first"
            )
        self._seed_user_id = user_id
        return user_id

    def _drop_seed_resource_if_unreferenced(self, resource_id: Any) -> None:
        from plugins.booking.booking.models.booking import Booking
        from plugins.booking.booking.models.resource import BookableResource

        # Query the DB for any remaining reservation on the resource rather than a
        # (possibly stale) relationship: the delete above ran with
        # ``synchronize_session=False``.
        still_referenced = (
            self._session.query(Booking.id)
            .filter(Booking.resource_id == resource_id)
            .first()
        )
        if still_referenced is not None:
            return
        resource = self._session.get(BookableResource, resource_id)
        if resource is not None:
            self._session.delete(resource)


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
        _BookingsExchanger(
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
