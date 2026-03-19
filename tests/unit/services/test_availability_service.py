"""Unit tests for AvailabilityService."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from plugins.booking.booking.services.availability_service import AvailabilityService


def _make_resource(
    slot_duration_minutes=30,
    capacity=1,
    schedule=None,
    exceptions=None,
    buffer_minutes=0,
    lead_time_hours=0,
    max_advance_days=365,
):
    """Helper to create a mock resource."""
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.slot_duration_minutes = slot_duration_minutes
    resource.capacity = capacity
    resource.availability = {
        "schedule": schedule
        or {
            "mon": [{"start": "09:00", "end": "12:00"}],
            "tue": [{"start": "09:00", "end": "12:00"}],
            "wed": [{"start": "09:00", "end": "12:00"}],
            "thu": [{"start": "09:00", "end": "12:00"}],
            "fri": [{"start": "09:00", "end": "12:00"}],
            "sat": [],
            "sun": [],
        },
        "exceptions": exceptions or [],
        "lead_time_hours": lead_time_hours,
        "max_advance_days": max_advance_days,
    }
    resource.config = {"buffer_minutes": buffer_minutes}
    resource.price = Decimal("50.00")
    return resource


class TestAvailabilityServiceSlots:
    """Test fixed-duration slot generation."""

    def test_returns_slots_from_weekly_schedule(self):
        booking_repo = MagicMock()
        booking_repo.count_by_resource_and_slot.return_value = 0
        service = AvailabilityService(booking_repo)

        # Monday with 09:00-12:00 and 30min slots = 6 slots
        resource = _make_resource(slot_duration_minutes=30)
        target = date.today() + timedelta(
            days=(7 - date.today().weekday())
        )  # next Monday

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert len(slots) == 6
        assert slots[0]["start"] == "09:00"
        assert slots[0]["end"] == "09:30"
        assert slots[-1]["start"] == "11:30"
        assert slots[-1]["end"] == "12:00"

    def test_subtracts_existing_bookings(self):
        booking_repo = MagicMock()
        # First slot is booked, rest are free
        booking_repo.count_by_resource_and_slot.side_effect = [1, 0, 0, 0, 0, 0]
        service = AvailabilityService(booking_repo)

        resource = _make_resource(slot_duration_minutes=30, capacity=1)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert len(slots) == 5  # 6 total minus 1 booked

    def test_respects_capacity_for_group_resources(self):
        booking_repo = MagicMock()
        # 15 out of 20 spots booked
        booking_repo.count_by_resource_and_slot.return_value = 15
        service = AvailabilityService(booking_repo)

        resource = _make_resource(slot_duration_minutes=60, capacity=20)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert len(slots) > 0
        assert slots[0]["available_capacity"] == 5

    def test_applies_buffer_between_slots(self):
        booking_repo = MagicMock()
        booking_repo.count_by_resource_and_slot.return_value = 0
        service = AvailabilityService(booking_repo)

        # 30min slots + 15min buffer in 3h window = 4 slots (not 6)
        resource = _make_resource(slot_duration_minutes=30, buffer_minutes=15)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert len(slots) == 4

    def test_handles_closed_days(self):
        booking_repo = MagicMock()
        service = AvailabilityService(booking_repo)

        # Saturday is closed (empty schedule)
        resource = _make_resource()
        # Find next Saturday
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        target = today + timedelta(days=days_until_saturday)

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert slots == []

    def test_handles_exception_dates_closed(self):
        booking_repo = MagicMock()
        service = AvailabilityService(booking_repo)

        target = date.today() + timedelta(days=(7 - date.today().weekday()))
        resource = _make_resource(
            exceptions=[
                {"date": target.isoformat(), "closed": True, "reason": "Holiday"}
            ]
        )

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert slots == []

    def test_returns_empty_for_fully_booked(self):
        booking_repo = MagicMock()
        booking_repo.count_by_resource_and_slot.return_value = 1  # capacity = 1
        service = AvailabilityService(booking_repo)

        resource = _make_resource(slot_duration_minutes=30, capacity=1)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert slots == []

    def test_past_dates_return_empty(self):
        booking_repo = MagicMock()
        service = AvailabilityService(booking_repo)

        resource = _make_resource()
        past_date = date.today() - timedelta(days=5)

        slots = service.get_available_slots(resource, past_date)
        assert slots == []

    def test_max_advance_days_exceeded_returns_empty(self):
        booking_repo = MagicMock()
        service = AvailabilityService(booking_repo)

        resource = _make_resource(max_advance_days=30)
        far_future = date.today() + timedelta(days=60)

        slots = service.get_available_slots(resource, far_future)
        assert slots == []


class TestAvailabilityServiceFlexible:
    """Test flexible-duration (hotel) availability."""

    def test_flexible_resource_returns_day_availability(self):
        booking_repo = MagicMock()
        booking_repo.count_by_resource_and_slot.return_value = 0
        service = AvailabilityService(booking_repo)

        resource = _make_resource(slot_duration_minutes=None, capacity=5)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert len(slots) == 1
        assert slots[0]["available_capacity"] == 5

    def test_flexible_resource_fully_booked(self):
        booking_repo = MagicMock()
        booking_repo.count_by_resource_and_slot.return_value = 5  # all rooms taken
        service = AvailabilityService(booking_repo)

        resource = _make_resource(slot_duration_minutes=None, capacity=5)
        target = date.today() + timedelta(days=(7 - date.today().weekday()))

        with patch(
            "plugins.booking.booking.services.availability_service.datetime"
        ) as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 1, 1)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime
            mock_dt.min = datetime.min
            mock_dt.max = datetime.max
            slots = service.get_available_slots(resource, target)

        assert slots == []
