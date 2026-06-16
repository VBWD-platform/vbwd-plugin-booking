"""Integration: S89.1 Slice B load-test bulk seed for ``bookings`` (real PG).

Proves the seed override end-to-end through the repository layer (no raw SQL):

* ``bulk_seed(N)`` inserts N valid ``loadtest-`` reservations, each linked to the
  one shared ``loadtest-`` resource and to a reused existing user, with a valid
  slot.
* the seeded rows round-trip: export → wipe → import recreates them with the
  resource link intact (the S89 measurement's hard requirement).
* ``bulk_seed`` is idempotent (a second run skips, the resource is reused — one
  resource, not duplicated).
* ``bulk_seed(reset=True)`` drops only the load-test reservations + the
  now-unreferenced ``loadtest-`` resource, leaving a pre-existing non-loadtest
  booking + its resource untouched.

The ``db`` fixture seeds an admin user (``TestDataSeeder``), so the seed's
"reuse an existing user" path resolves a real ``vbwd_user.id`` for the FK.

Engineering requirements (binding, restated): TDD-first; DevOps-first (cold
local + CI via the shared ``db`` fixture, no raw SQL); SOLID/DI/DRY; Liskov;
no overengineering. Quality guard: ``bin/pre-commit-check.sh --plugin booking
--full``.
"""
import uuid
from datetime import datetime, timedelta

from vbwd.services.data_exchange.envelope import build_envelope
from vbwd.services.data_exchange.port import ExportSelector
from vbwd.models.user import User

from plugins.booking.booking.models.booking import Booking
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.services.data_exchange.booking_exchangers import (
    build_booking_exchangers,
)

_SEED_RESOURCE_SLUG = "loadtest-bookings-resource"


def _bookings_exchanger(session):
    return {
        exchanger.entity_key: exchanger
        for exchanger in build_booking_exchangers(session)
    }["bookings"]


def _seed_resource(session):
    return (
        session.query(BookableResource)
        .filter(BookableResource.slug == _SEED_RESOURCE_SLUG)
        .first()
    )


def _loadtest_bookings(session):
    resource = _seed_resource(session)
    if resource is None:
        return []
    return session.query(Booking).filter(Booking.resource_id == resource.id).all()


class TestBulkSeedBookings:
    def test_seeds_valid_linked_rows(self, db):
        exchanger = _bookings_exchanger(db.session)

        result = exchanger.bulk_seed(10)
        db.session.commit()

        assert result.created == 10
        resource = _seed_resource(db.session)
        assert resource is not None
        bookings = _loadtest_bookings(db.session)
        assert len(bookings) == 10
        for booking in bookings:
            assert booking.resource_id == resource.id
            assert booking.user_id is not None
            assert booking.end_at > booking.start_at

    def test_round_trips_with_resource_link(self, db):
        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(10)
        db.session.commit()

        resource_id = _seed_resource(db.session).id
        exported = exchanger.export(ExportSelector(ids=None), include_pii=True).rows
        loadtest_rows = [
            row for row in exported if str(row["resource_id"]) == str(resource_id)
        ]
        assert len(loadtest_rows) == 10

        # Wipe the load-test reservations (the resource + user stay) and re-import.
        db.session.query(Booking).filter(Booking.resource_id == resource_id).delete(
            synchronize_session=False
        )
        db.session.commit()
        assert _loadtest_bookings(db.session) == []

        payload = build_envelope("bookings", loadtest_rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)

        assert result.created == 10
        rebuilt = _loadtest_bookings(db.session)
        assert len(rebuilt) == 10
        assert all(booking.resource_id == resource_id for booking in rebuilt)

    def test_idempotent_reuses_one_resource(self, db):
        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(10)
        db.session.commit()

        # A fresh exchanger (cleared cache) must reuse the existing resource +
        # skip every already-present deterministic id.
        exchanger = _bookings_exchanger(db.session)
        result = exchanger.bulk_seed(10)
        db.session.commit()

        assert result.created == 0
        assert result.skipped == 10
        assert len(_loadtest_bookings(db.session)) == 10
        resources = (
            db.session.query(BookableResource)
            .filter(BookableResource.slug == _SEED_RESOURCE_SLUG)
            .all()
        )
        assert len(resources) == 1

    def test_reset_leaves_non_loadtest_booking_and_resource_untouched(self, db):
        # A pre-existing real reservation + real resource + real user must survive
        # --reset.
        keeper_resource = BookableResource(
            name="Real room",
            slug=f"real-room-{uuid.uuid4().hex[:8]}",
            price=10,
            availability={},
        )
        keeper_user = User(
            email=f"keeper-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.session.add_all([keeper_resource, keeper_user])
        db.session.commit()
        start = datetime(2026, 7, 1, 10, 0, 0)
        keeper_booking = Booking(
            resource_id=keeper_resource.id,
            user_id=keeper_user.id,
            start_at=start,
            end_at=start + timedelta(hours=1),
            status="confirmed",
            quantity=1,
        )
        db.session.add(keeper_booking)
        db.session.commit()
        keeper_booking_id = keeper_booking.id

        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(10)
        db.session.commit()

        exchanger = _bookings_exchanger(db.session)
        result = exchanger.bulk_seed(5, reset=True)
        db.session.commit()

        assert result.deleted == 10
        assert result.created == 5
        assert len(_loadtest_bookings(db.session)) == 5

        # The real booking + its resource are untouched.
        assert db.session.get(Booking, keeper_booking_id) is not None
        assert (
            db.session.query(BookableResource)
            .filter(BookableResource.id == keeper_resource.id)
            .first()
            is not None
        )

    def test_reset_keeps_shared_resource_for_cold_reimport(self, db):
        """``--reset`` drops the reservations but KEEPS the shared resource.

        S89.1 load-test bug (CI run 27576135604): the harness runs a *cold*
        import by ``bulk-seed bookings --count 0 --reset`` (empties the table)
        then importing the exported NDJSON. The exported rows carry the shared
        resource's UUID in ``resource_id``; if ``--reset`` also dropped that
        resource, the cold insert hit a ``ForeignKeyViolation`` and the CLI
        exited non-zero (``outcome=error``). The shared ``loadtest-`` resource is
        a stable, deterministic fixture (fixed slug), not load data — keeping it
        across a reset is what makes the same-instance export→reset→import
        round-trip valid (the documented guarantee).
        """
        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(10)
        db.session.commit()
        assert _seed_resource(db.session) is not None

        exchanger = _bookings_exchanger(db.session)
        result = exchanger.bulk_seed(0, reset=True)
        db.session.commit()

        assert result.deleted == 10
        assert result.created == 0
        assert _loadtest_bookings(db.session) == []
        # The shared resource survives so a cold re-import's resource_id FK
        # still resolves.
        assert _seed_resource(db.session) is not None

    def test_cold_reimport_after_reset_round_trips(self, db):
        """Reproduce the CI cold path: seed → export → reset → import (created).

        After ``--reset`` empties the reservations, importing the exported rows
        must re-insert them cleanly (the ``resource_id`` FK still resolves to the
        surviving shared resource) rather than raising a FK violation.
        """
        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(10)
        db.session.commit()

        resource_id = _seed_resource(db.session).id
        exported = exchanger.export(ExportSelector(ids=None), include_pii=True).rows
        loadtest_rows = [
            row for row in exported if str(row["resource_id"]) == str(resource_id)
        ]
        assert len(loadtest_rows) == 10

        # The harness's "cold" reset between cells: count 0 + reset.
        exchanger = _bookings_exchanger(db.session)
        exchanger.bulk_seed(0, reset=True)
        db.session.commit()
        assert _loadtest_bookings(db.session) == []

        # Cold import re-creates every reservation against the surviving FK.
        exchanger = _bookings_exchanger(db.session)
        payload = build_envelope("bookings", loadtest_rows, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)

        assert result.errors == []
        assert result.created == 10
        rebuilt = _loadtest_bookings(db.session)
        assert len(rebuilt) == 10
        assert all(str(booking.resource_id) == str(resource_id) for booking in rebuilt)
