"""Unit tests for BookingService.reschedule_booking — Sprint 28 D8.

Mocks every collaborator so the service-layer logic (validation, event
emission, audit-note append, invoice non-touch) is exercised in isolation.
Real DB + route integration lives in tests/integration.
"""
from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from vbwd.utils.datetime_utils import utcnow


def _make_booking(**overrides):
    now = utcnow()
    booking = MagicMock()
    booking.id = overrides.get("id", uuid4())
    booking.user_id = overrides.get("user_id", uuid4())
    booking.resource_id = overrides.get("resource_id", uuid4())
    booking.status = overrides.get("status", "confirmed")
    booking.start_at = overrides.get("start_at", now + timedelta(days=3))
    booking.end_at = overrides.get("end_at", now + timedelta(days=3, hours=1))
    booking.quantity = overrides.get("quantity", 1)
    booking.admin_notes = overrides.get("admin_notes", "")
    booking.invoice_id = overrides.get("invoice_id", uuid4())
    return booking


def _make_resource(capacity=1):
    resource = MagicMock()
    resource.id = uuid4()
    resource.capacity = capacity
    resource.is_active = True
    return resource


@pytest.fixture
def service_and_mocks():
    from plugins.booking.booking.services.booking_service import BookingService

    booking_repo = MagicMock()
    resource_repo = MagicMock()
    availability_service = MagicMock()
    invoice_service = MagicMock()
    event_bus = MagicMock()

    service = BookingService(
        booking_repository=booking_repo,
        resource_repository=resource_repo,
        availability_service=availability_service,
        invoice_service=invoice_service,
        event_bus=event_bus,
    )
    return (
        service,
        booking_repo,
        resource_repo,
        availability_service,
        invoice_service,
        event_bus,
    )


class TestRescheduleBookingHappyPath:
    def test_updates_times_and_emits_event(self, service_and_mocks):
        (
            service,
            booking_repo,
            resource_repo,
            _,
            invoice_service,
            event_bus,
        ) = service_and_mocks

        user_id = uuid4()
        booking = _make_booking(user_id=user_id, status="confirmed")
        original_start = booking.start_at
        booking_repo.find_by_id.return_value = booking

        resource = _make_resource(capacity=5)
        resource_repo.find_by_id.return_value = resource

        # Capacity check: no other bookings on the new slot
        booking_repo.count_by_resource_and_slot.return_value = 0

        new_start = utcnow() + timedelta(days=5)
        new_end = new_start + timedelta(hours=1)

        result = service.reschedule_booking(
            booking_id=booking.id,
            user_id=user_id,
            new_start_at=new_start,
            new_end_at=new_end,
            cancellation_grace_period_hours=24,
            min_lead_time_hours=1,
        )

        assert result is booking
        assert booking.start_at == new_start
        assert booking.end_at == new_end
        assert booking.status == "confirmed"  # unchanged
        # Audit note appended
        assert "rescheduled from" in (booking.admin_notes or "").lower()
        booking_repo.save.assert_called_once_with(booking)
        # Event emitted with old + new start
        event_bus.publish.assert_called_once()
        event_name, payload = event_bus.publish.call_args[0]
        assert event_name == "booking.rescheduled"
        assert payload["old_start_at"] == original_start.isoformat()
        assert payload["new_start_at"] == new_start.isoformat()
        # Invoice left alone — no invoice-service calls
        invoice_service.assert_not_called()


class TestRescheduleBookingValidation:
    def test_rejects_non_owner(self, service_and_mocks):
        service, booking_repo, resource_repo, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        owner_id = uuid4()
        other_user_id = uuid4()
        booking = _make_booking(user_id=owner_id)
        booking_repo.find_by_id.return_value = booking
        resource_repo.find_by_id.return_value = _make_resource()
        booking_repo.count_by_resource_and_slot.return_value = 0

        with pytest.raises(BookingError, match="owner"):
            service.reschedule_booking(
                booking_id=booking.id,
                user_id=other_user_id,
                new_start_at=utcnow() + timedelta(days=5),
                new_end_at=utcnow() + timedelta(days=5, hours=1),
                cancellation_grace_period_hours=24,
                min_lead_time_hours=1,
            )

    def test_rejects_when_current_start_within_grace_period(self, service_and_mocks):
        service, booking_repo, _, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        user_id = uuid4()
        booking = _make_booking(
            user_id=user_id,
            status="confirmed",
            start_at=utcnow() + timedelta(hours=10),  # only 10 hours away
        )
        booking_repo.find_by_id.return_value = booking

        with pytest.raises(BookingError, match="grace|cut-?off|too late"):
            service.reschedule_booking(
                booking_id=booking.id,
                user_id=user_id,
                new_start_at=utcnow() + timedelta(days=5),
                new_end_at=utcnow() + timedelta(days=5, hours=1),
                cancellation_grace_period_hours=24,
                min_lead_time_hours=1,
            )

    def test_rejects_new_start_in_past(self, service_and_mocks):
        service, booking_repo, resource_repo, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        user_id = uuid4()
        booking = _make_booking(user_id=user_id, status="confirmed")
        booking_repo.find_by_id.return_value = booking
        resource_repo.find_by_id.return_value = _make_resource()

        with pytest.raises(BookingError, match="past|future|lead.?time"):
            service.reschedule_booking(
                booking_id=booking.id,
                user_id=user_id,
                new_start_at=utcnow() - timedelta(hours=1),
                new_end_at=utcnow() - timedelta(minutes=30),
                cancellation_grace_period_hours=24,
                min_lead_time_hours=1,
            )

    def test_rejects_when_status_not_reschedulable(self, service_and_mocks):
        service, booking_repo, _, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        for terminal_status in ("cancelled", "completed"):
            user_id = uuid4()
            booking = _make_booking(user_id=user_id, status=terminal_status)
            booking_repo.find_by_id.return_value = booking

            with pytest.raises(BookingError, match="status"):
                service.reschedule_booking(
                    booking_id=booking.id,
                    user_id=user_id,
                    new_start_at=utcnow() + timedelta(days=5),
                    new_end_at=utcnow() + timedelta(days=5, hours=1),
                    cancellation_grace_period_hours=24,
                    min_lead_time_hours=1,
                )

    def test_rejects_when_booking_not_found(self, service_and_mocks):
        service, booking_repo, _, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        booking_repo.find_by_id.return_value = None

        with pytest.raises(BookingError, match="not found"):
            service.reschedule_booking(
                booking_id=uuid4(),
                user_id=uuid4(),
                new_start_at=utcnow() + timedelta(days=5),
                new_end_at=utcnow() + timedelta(days=5, hours=1),
                cancellation_grace_period_hours=24,
                min_lead_time_hours=1,
            )

    def test_rejects_when_new_slot_full(self, service_and_mocks):
        service, booking_repo, resource_repo, _, _, _ = service_and_mocks
        from plugins.booking.booking.services.booking_service import BookingError

        user_id = uuid4()
        booking = _make_booking(user_id=user_id, status="confirmed", quantity=1)
        booking_repo.find_by_id.return_value = booking

        resource = _make_resource(capacity=1)
        resource_repo.find_by_id.return_value = resource

        # The new slot already has 1 booking at full capacity (not counting this one)
        booking_repo.count_by_resource_and_slot.return_value = 1

        with pytest.raises(BookingError, match="capacity|unavailable|full"):
            service.reschedule_booking(
                booking_id=booking.id,
                user_id=user_id,
                new_start_at=utcnow() + timedelta(days=5),
                new_end_at=utcnow() + timedelta(days=5, hours=1),
                cancellation_grace_period_hours=24,
                min_lead_time_hours=1,
            )

    def test_does_not_count_itself_as_taking_the_new_slot(self, service_and_mocks):
        """If the user picks an overlapping new slot and the booking is
        counted as its own competitor, capacity=1 resources would be
        unreschedulable to any adjacent time. Repo must be called with
        exclude_booking_id so the service can trust the count."""
        service, booking_repo, resource_repo, _, _, _ = service_and_mocks

        user_id = uuid4()
        booking = _make_booking(user_id=user_id, status="confirmed", quantity=1)
        booking_repo.find_by_id.return_value = booking

        resource = _make_resource(capacity=1)
        resource_repo.find_by_id.return_value = resource
        booking_repo.count_by_resource_and_slot.return_value = 0

        new_start = utcnow() + timedelta(days=5)
        new_end = new_start + timedelta(hours=1)

        service.reschedule_booking(
            booking_id=booking.id,
            user_id=user_id,
            new_start_at=new_start,
            new_end_at=new_end,
            cancellation_grace_period_hours=24,
            min_lead_time_hours=1,
        )

        # Assert count_by_resource_and_slot was called with exclude kwarg.
        args, kwargs = booking_repo.count_by_resource_and_slot.call_args
        assert "exclude_booking_id" in kwargs
        assert kwargs["exclude_booking_id"] == booking.id
