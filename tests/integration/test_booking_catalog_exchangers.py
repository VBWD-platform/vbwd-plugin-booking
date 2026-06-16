"""Integration: booking catalog exchangers (real PG) — S61.

Covers the two new catalog exchangers added by S61:

* ``booking_categories`` (``BookableResourceCategory``, natural key ``slug``) —
  carries the self-referential ``parent`` by ``parent_slug`` (resolved on
  import; the export-only ``fk_natural_key_map`` cannot do the slug→id resolve).
* ``booking_resources`` (``BookableResource``, natural key ``slug``) — carries
  the resource↔category M2M as ``category_slugs`` (resolved on import), plus the
  ``availability`` JSON and ``price`` / ``price_unit`` round-tripping verbatim.

Scenarios (sprint TDD plan): round-trip linked-by-slug, FK-by-slug (different id
on the target instance), upsert, missing referent (error row, no crash), dry_run
(no writes), hierarchy (parent slug), manifest/perms, envelope validity.

Data is seeded through the ORM session (no raw SQL); the shared ``db`` fixture
creates + drops the test DB.

Engineering requirements (binding, restated): TDD-first; DevOps-first; SOLID/DI/
DRY; Liskov (a missing referent yields an error row, never a crash); clean code;
no overengineering. Quality guard: ``bin/pre-commit-check.sh --plugin booking
--full``.
"""
import uuid
from decimal import Decimal

from vbwd.services.data_exchange.envelope import (
    build_envelope,
    validate_envelope,
)
from vbwd.services.data_exchange.port import CLUSTER_SALES, ExportSelector
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.models.resource_category import (
    BookableResourceCategory,
)
from plugins.booking.booking.services.data_exchange.booking_exchangers import (
    build_booking_exchangers,
)


def _exchanger(session, entity_key):
    for exchanger in build_booking_exchangers(session):
        if exchanger.entity_key == entity_key:
            return exchanger
    raise AssertionError(f"exchanger '{entity_key}' not built")


_AVAILABILITY = {
    "monday": [{"start": "09:00", "end": "17:00"}],
    "tuesday": [{"start": "09:00", "end": "12:00"}],
}


def _seed_category(db, *, slug=None, name="Medical", parent=None):
    category = BookableResourceCategory(
        name=name,
        slug=slug or f"cat-{uuid.uuid4().hex[:8]}",
        description="A category",
        sort_order=3,
    )
    if parent is not None:
        category.parent_id = parent.id
    db.session.add(category)
    db.session.commit()
    return category


def _seed_resource(db, *, slug=None, categories=(), price="49.50"):
    resource = BookableResource(
        name="Dr. Smith",
        slug=slug or f"res-{uuid.uuid4().hex[:8]}",
        description="Specialist",
        capacity=2,
        slot_duration_minutes=30,
        price=Decimal(price),
        price_unit="per_slot",
        availability=dict(_AVAILABILITY),
        sort_order=7,
    )
    for category in categories:
        resource.categories.append(category)
    db.session.add(resource)
    db.session.commit()
    return resource


class TestCategoryExchanger:
    def test_round_trip_by_slug(self, db):
        category = _seed_category(db, slug="medical", name="Medical")
        exchanger = _exchanger(db.session, "booking_categories")

        rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows
        assert any(row["slug"] == "medical" for row in rows)

        db.session.query(BookableResourceCategory).delete()
        db.session.commit()
        assert (
            db.session.query(BookableResourceCategory).filter_by(slug="medical").first()
            is None
        )

        payload = build_envelope("booking_categories", rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []

        rebuilt = (
            db.session.query(BookableResourceCategory).filter_by(slug="medical").first()
        )
        assert rebuilt is not None
        assert rebuilt.name == "Medical"
        assert rebuilt.sort_order == 3
        assert category.slug == rebuilt.slug

    def test_hierarchy_parent_resolved_by_slug(self, db):
        parent = _seed_category(db, slug="health", name="Health")
        _seed_category(db, slug="dentistry", name="Dentistry", parent=parent)
        exchanger = _exchanger(db.session, "booking_categories")

        rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows
        child_row = next(row for row in rows if row["slug"] == "dentistry")
        assert child_row["parent_slug"] == "health"
        assert "parent_id" not in child_row

        db.session.query(BookableResourceCategory).delete()
        db.session.commit()

        payload = build_envelope("booking_categories", rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []

        rebuilt_parent = (
            db.session.query(BookableResourceCategory).filter_by(slug="health").first()
        )
        rebuilt_child = (
            db.session.query(BookableResourceCategory)
            .filter_by(slug="dentistry")
            .first()
        )
        assert rebuilt_child.parent_id == rebuilt_parent.id

    def test_hierarchy_import_order_independent_child_before_parent(self, db):
        """A child row BEFORE its parent in the payload still resolves (the flaky bug).

        The export row order is non-deterministic, so the import must topologically
        order parents before children rather than relying on payload order.
        """
        exchanger = _exchanger(db.session, "booking_categories")
        parent_row = {
            "name": "Health",
            "slug": "health",
            "description": None,
            "image_url": None,
            "config": {},
            "sort_order": 0,
            "is_active": True,
            "parent_slug": None,
        }
        child_row = {
            "name": "Dentistry",
            "slug": "dentistry",
            "description": None,
            "image_url": None,
            "config": {},
            "sort_order": 0,
            "is_active": True,
            "parent_slug": "health",
        }
        # Deliberately child FIRST — the broken order that triggered the flake.
        payload = build_envelope(
            "booking_categories", [child_row, parent_row], instance="test"
        )

        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []

        rebuilt_parent = (
            db.session.query(BookableResourceCategory).filter_by(slug="health").first()
        )
        rebuilt_child = (
            db.session.query(BookableResourceCategory)
            .filter_by(slug="dentistry")
            .first()
        )
        assert rebuilt_parent is not None
        assert rebuilt_child is not None
        assert rebuilt_child.parent_id == rebuilt_parent.id

    def test_three_level_hierarchy_import_shuffled(self, db):
        """A grandparent→parent→child chain imports regardless of payload order."""
        exchanger = _exchanger(db.session, "booking_categories")

        def _row(slug, name, parent_slug):
            return {
                "name": name,
                "slug": slug,
                "description": None,
                "image_url": None,
                "config": {},
                "sort_order": 0,
                "is_active": True,
                "parent_slug": parent_slug,
            }

        grandparent = _row("medical", "Medical", None)
        parent = _row("dental", "Dental", "medical")
        child = _row("orthodontics", "Orthodontics", "dental")
        # Worst-case shuffle: deepest first, root last.
        payload = build_envelope(
            "booking_categories", [child, parent, grandparent], instance="test"
        )

        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []

        rebuilt = {
            category.slug: category
            for category in db.session.query(BookableResourceCategory).all()
        }
        assert rebuilt["dental"].parent_id == rebuilt["medical"].id
        assert rebuilt["orthodontics"].parent_id == rebuilt["dental"].id

    def test_unknown_parent_slug_records_error_without_crash(self, db):
        rows = [
            {
                "slug": "orphan",
                "name": "Orphan",
                "description": None,
                "image_url": None,
                "config": {},
                "sort_order": 0,
                "is_active": True,
                "parent_slug": "does-not-exist",
            }
        ]
        exchanger = _exchanger(db.session, "booking_categories")
        payload = build_envelope("booking_categories", rows, instance="test")

        result = exchanger.import_(payload, mode="upsert", dry_run=False)

        assert len(result.errors) == 1
        assert result.errors[0]["row"] == 0
        assert (
            db.session.query(BookableResourceCategory).filter_by(slug="orphan").first()
            is None
        )


class TestResourceExchanger:
    def test_round_trip_resource_linked_by_category_slug(self, db):
        category = _seed_category(db, slug="rooms", name="Rooms")
        _seed_resource(db, slug="room-a", categories=[category], price="49.50")
        exchanger = _exchanger(db.session, "booking_resources")

        rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows
        row = next(item for item in rows if item["slug"] == "room-a")
        assert row["category_slugs"] == ["rooms"]
        assert row["availability"] == _AVAILABILITY
        assert row["price"] == 49.5
        assert row["price_unit"] == "per_slot"
        assert "category_id" not in row

        db.session.query(BookableResource).delete()
        db.session.commit()

        payload = build_envelope("booking_resources", rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []
        assert result.created == 1

        rebuilt = db.session.query(BookableResource).filter_by(slug="room-a").first()
        assert rebuilt is not None
        assert rebuilt.availability == _AVAILABILITY
        assert rebuilt.price == 49.5
        assert rebuilt.price_unit == "per_slot"
        assert rebuilt.capacity == 2
        assert [cat.slug for cat in rebuilt.categories] == ["rooms"]

    def test_fk_resolved_by_slug_not_id(self, db):
        """The category has a different id on the 'target' instance."""
        source_category = _seed_category(db, slug="events", name="Events")
        _seed_resource(db, slug="hall", categories=[source_category])
        exchanger = _exchanger(db.session, "booking_resources")
        rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows

        # Simulate another instance: drop everything, recreate the category with a
        # fresh id, then import the resource — it must bind by slug, not old id.
        db.session.query(BookableResource).delete()
        db.session.query(BookableResourceCategory).delete()
        db.session.commit()
        target_category = _seed_category(db, slug="events", name="Events")

        payload = build_envelope("booking_resources", rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.errors == []

        rebuilt = db.session.query(BookableResource).filter_by(slug="hall").first()
        assert [cat.id for cat in rebuilt.categories] == [target_category.id]

    def test_upsert_by_slug_updates_existing(self, db):
        category = _seed_category(db, slug="spaces", name="Spaces")
        _seed_resource(db, slug="desk", categories=[category], price="10.00")
        exchanger = _exchanger(db.session, "booking_resources")
        rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows

        row = next(item for item in rows if item["slug"] == "desk")
        row["name"] = "Renamed Desk"
        row["price"] = "12.00"

        payload = build_envelope("booking_resources", rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.updated == 1
        assert result.created == 0

        assert db.session.query(BookableResource).filter_by(slug="desk").count() == 1
        rebuilt = db.session.query(BookableResource).filter_by(slug="desk").first()
        assert rebuilt.name == "Renamed Desk"
        assert rebuilt.price == 12.0

    def test_unknown_category_slug_records_error_without_crash(self, db):
        good_category = _seed_category(db, slug="ok-cat", name="OK")
        exchanger = _exchanger(db.session, "booking_resources")
        rows = [
            {
                "name": "Bad",
                "slug": "bad-res",
                "description": None,
                "capacity": 1,
                "slot_duration_minutes": None,
                "price": "1.00",
                "price_unit": "per_slot",
                "availability": {},
                "custom_fields_schema": None,
                "image_url": None,
                "config": {},
                "is_active": True,
                "sort_order": 0,
                "category_slugs": ["missing-cat"],
            },
            {
                "name": "Good",
                "slug": "good-res",
                "description": None,
                "capacity": 1,
                "slot_duration_minutes": None,
                "price": "2.00",
                "price_unit": "per_slot",
                "availability": {},
                "custom_fields_schema": None,
                "image_url": None,
                "config": {},
                "is_active": True,
                "sort_order": 0,
                "category_slugs": [good_category.slug],
            },
        ]
        payload = build_envelope("booking_resources", rows, instance="test")

        result = exchanger.import_(payload, mode="upsert", dry_run=False)

        assert len(result.errors) == 1
        assert result.errors[0]["row"] == 0
        # The bad row is skipped; the good row is still applied.
        assert (
            db.session.query(BookableResource).filter_by(slug="bad-res").first() is None
        )
        good = db.session.query(BookableResource).filter_by(slug="good-res").first()
        assert good is not None
        assert [cat.slug for cat in good.categories] == [good_category.slug]

    def test_dry_run_writes_nothing(self, db):
        category = _seed_category(db, slug="dry-cat", name="Dry")
        exchanger = _exchanger(db.session, "booking_resources")
        rows = [
            {
                "name": "Preview",
                "slug": "preview-res",
                "description": None,
                "capacity": 1,
                "slot_duration_minutes": None,
                "price": "5.00",
                "price_unit": "per_slot",
                "availability": {},
                "custom_fields_schema": None,
                "image_url": None,
                "config": {},
                "is_active": True,
                "sort_order": 0,
                "category_slugs": [category.slug],
            }
        ]
        payload = build_envelope("booking_resources", rows, instance="test")

        result = exchanger.import_(payload, mode="upsert", dry_run=True)

        assert result.created == 1
        assert (
            db.session.query(BookableResource).filter_by(slug="preview-res").first()
            is None
        )


class TestEnvelopeAndManifest:
    def test_envelope_validates_for_each_entity(self, db):
        category = _seed_category(db, slug="env-cat", name="Env")
        _seed_resource(db, slug="env-res", categories=[category])
        for entity_key in ("booking_categories", "booking_resources"):
            exchanger = _exchanger(db.session, entity_key)
            rows = exchanger.export(ExportSelector(all=True), include_pii=False).rows
            payload = build_envelope(entity_key, rows, instance="test")
            assert validate_envelope(payload, entity_key) == rows

    def test_manifest_lists_catalog_entities_with_perms(self, db):
        from types import SimpleNamespace

        from vbwd.services.data_exchange.registry import data_exchange_registry
        from plugins.booking.booking.services.data_exchange.booking_exchangers import (
            register_booking_exchangers,
        )

        register_booking_exchangers(db.session)

        granted = {"booking.resources.view", "booking.resources.manage"}
        user = SimpleNamespace(
            role=SimpleNamespace(value="ADMIN"),
            has_permission=lambda perm: perm in granted,
        )
        manifest = data_exchange_registry.manifest_for(user)
        keys = {item["entity_key"] for item in manifest}
        assert "booking_categories" in keys
        assert "booking_resources" in keys
        for item in manifest:
            if item["entity_key"] in ("booking_categories", "booking_resources"):
                assert item["cluster"] == CLUSTER_SALES

        denied_user = SimpleNamespace(
            role=SimpleNamespace(value="ADMIN"),
            has_permission=lambda perm: False,
        )
        denied_manifest = data_exchange_registry.manifest_for(denied_user)
        denied_keys = {item["entity_key"] for item in denied_manifest}
        assert "booking_categories" not in denied_keys
        assert "booking_resources" not in denied_keys
