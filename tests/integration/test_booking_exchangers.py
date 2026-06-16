"""Integration: booking entity exchangers (real PG) — S46.6.

* ``bookings`` round-trips by ``id`` (export → wipe → import → equal), the only
  stable natural key the model has (flagged: no booking-reference column).
* export redacts the free-text ``notes`` / ``admin_notes`` PII unless
  ``include_pii``.
* registration: after ``BookingPlugin._register_data_exchangers`` the exchanger
  appears in ``data_exchange_registry`` with cluster ``sales``.

Data is seeded through the ORM session (no raw SQL); the shared ``db`` fixture
creates + drops the test DB.

Engineering requirements (binding, restated): TDD-first; DevOps-first; SOLID/DI/
DRY; Liskov; no overengineering. Quality guard: ``bin/pre-commit-check.sh
--plugin booking --full``.
"""
import uuid
from datetime import datetime, timedelta

from vbwd.services.data_exchange.envelope import build_envelope, iter_ndjson_lines
from vbwd.services.data_exchange.port import CLUSTER_SALES, ExportSelector
from plugins.booking.booking.models.booking import Booking
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.services.data_exchange.booking_exchangers import (
    build_booking_exchangers,
)
from vbwd.models.user import User


def _exchanger(session):
    return build_booking_exchangers(session)[0]


def _seed_booking(db, *, notes="customer note"):
    resource = BookableResource(
        name="Room A",
        slug=f"room-{uuid.uuid4().hex[:8]}",
        price=10,
    )
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db.session.add_all([resource, user])
    db.session.commit()
    start = datetime(2026, 7, 1, 10, 0, 0)
    booking = Booking(
        resource_id=resource.id,
        user_id=user.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        status="confirmed",
        quantity=2,
        notes=notes,
        admin_notes="internal",
    )
    db.session.add(booking)
    db.session.commit()
    return booking


class TestBookingsRoundTrip:
    def test_round_trip_by_id(self, db):
        booking = _seed_booking(db)
        booking_id = booking.id
        exchanger = _exchanger(db.session)

        before = exchanger.export(
            ExportSelector(ids=[str(booking_id)]), include_pii=True
        ).rows
        assert before and str(before[0]["id"]) == str(booking_id)
        assert before[0]["quantity"] == 2

        db.session.query(Booking).filter(Booking.id == booking_id).delete()
        db.session.commit()
        assert db.session.get(Booking, booking_id) is None

        payload = build_envelope("bookings", before, instance="test")
        result = exchanger.import_(payload, mode="upsert", dry_run=False)
        assert result.created == 1

        rebuilt = db.session.get(Booking, booking_id)
        assert rebuilt is not None
        assert rebuilt.quantity == 2
        assert rebuilt.status == "confirmed"

    def test_ndjson_round_trip_by_id(self, db):
        """The real CLI path: export → NDJSON text → import_ndjson back.

        S89.1 load-test bug: a ``bookings`` NDJSON export re-imports with
        ``outcome=error``. Unlike :meth:`test_round_trip_by_id` (which feeds the
        in-memory Python rows straight back, keeping ``datetime``/UUID objects),
        the CLI serialises every row through ``json.dumps`` — so ``start_at`` /
        ``end_at`` arrive as ISO strings and the id/FKs as UUID strings. The
        import must deserialise those back into the model's typed columns; a raw
        string into a ``db.DateTime`` column breaks the flush.
        """
        booking = _seed_booking(db)
        booking_id = booking.id
        exchanger = _exchanger(db.session)

        # Serialise exactly as the CLI does: chunked iter_export → NDJSON lines.
        chunks = exchanger.iter_export(
            ExportSelector(ids=[str(booking_id)]),
            chunk_size=5000,
            include_pii=True,
        )
        ndjson_text = "".join(iter_ndjson_lines("bookings", chunks, instance="test"))

        db.session.query(Booking).filter(Booking.id == booking_id).delete()
        db.session.commit()
        assert db.session.get(Booking, booking_id) is None

        result = exchanger.import_ndjson(
            ndjson_text.splitlines(keepends=True), mode="upsert", dry_run=False
        )
        assert result.errors == []
        assert result.created == 1

        rebuilt = db.session.get(Booking, booking_id)
        assert rebuilt is not None
        assert rebuilt.quantity == 2
        assert rebuilt.status == "confirmed"
        assert rebuilt.start_at == datetime(2026, 7, 1, 10, 0, 0)
        assert rebuilt.end_at == datetime(2026, 7, 1, 11, 0, 0)
        assert str(rebuilt.resource_id) == str(booking.resource_id)
        assert str(rebuilt.user_id) == str(booking.user_id)

        # Re-import the same NDJSON → idempotent upsert (updates, no new row).
        second = exchanger.import_ndjson(
            ndjson_text.splitlines(keepends=True), mode="upsert", dry_run=False
        )
        assert second.errors == []
        assert second.updated == 1
        assert second.created == 0
        assert db.session.query(Booking).filter(Booking.id == booking_id).count() == 1

    def test_export_redacts_pii_without_permission(self, db):
        booking = _seed_booking(db, notes="sensitive")
        exchanger = _exchanger(db.session)

        without_pii = exchanger.export(
            ExportSelector(ids=[str(booking.id)]), include_pii=False
        ).rows
        assert without_pii[0]["notes"] is None
        assert without_pii[0]["admin_notes"] is None

        with_pii = exchanger.export(
            ExportSelector(ids=[str(booking.id)]), include_pii=True
        ).rows
        assert with_pii[0]["notes"] == "sensitive"


class TestRegistration:
    def test_on_enable_registers_booking_exchanger(self, db):
        from vbwd.services.data_exchange.registry import data_exchange_registry
        from plugins.booking import BookingPlugin

        plugin = BookingPlugin()
        plugin.initialize({})
        plugin._register_data_exchangers()

        exchanger = data_exchange_registry.get("bookings")
        assert exchanger is not None
        assert exchanger.cluster == CLUSTER_SALES
        assert exchanger.supports_import is True
        assert "csv" in exchanger.supported_formats
