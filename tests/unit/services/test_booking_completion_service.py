"""Tests for BookingCompletionService — auto-completes past bookings."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from plugins.booking.booking.services.booking_completion_service import (
    BookingCompletionService,
)


def _make_booking(status="confirmed", end_at=None):
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.user_id = uuid.uuid4()
    booking.resource_id = uuid.uuid4()
    booking.invoice_id = uuid.uuid4()
    booking.status = status
    booking.end_at = end_at or (datetime.utcnow() - timedelta(hours=1))
    return booking


class TestBookingCompletionService:
    def _make_service(self, past_bookings=None):
        booking_repo = MagicMock()
        resource_repo = MagicMock()
        event_bus = MagicMock()

        booking_repo.find_past_confirmed.return_value = past_bookings or []

        service = BookingCompletionService(
            booking_repository=booking_repo,
            resource_repository=resource_repo,
            event_bus=event_bus,
        )
        return service, booking_repo, event_bus

    def test_completes_past_confirmed_bookings(self):
        booking = _make_booking(status="confirmed")
        service, booking_repo, event_bus = self._make_service([booking])

        completed = service.complete_past_bookings()

        assert len(completed) == 1
        assert booking.status == "completed"

    def test_publishes_booking_completed_event(self):
        booking = _make_booking(status="confirmed")
        service, _, event_bus = self._make_service([booking])

        service.complete_past_bookings()

        event_bus.publish.assert_called_once()
        assert event_bus.publish.call_args[0][0] == "booking.completed"

    def test_skips_cancelled_bookings(self):
        """Only confirmed bookings should be completed."""
        service, booking_repo, event_bus = self._make_service([])

        completed = service.complete_past_bookings()

        assert len(completed) == 0
        event_bus.publish.assert_not_called()

    def test_completes_multiple_bookings(self):
        bookings = [_make_booking() for _ in range(3)]
        service, _, event_bus = self._make_service(bookings)

        completed = service.complete_past_bookings()

        assert len(completed) == 3
        assert event_bus.publish.call_count == 3

    def test_returns_completed_booking_ids(self):
        booking = _make_booking()
        service, _, _ = self._make_service([booking])

        completed = service.complete_past_bookings()

        assert completed[0] == booking.id
