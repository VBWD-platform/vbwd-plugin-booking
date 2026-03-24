"""AvailabilityService — compute available slots from schedule + existing bookings."""
from datetime import date, datetime, timedelta

from plugins.booking.booking.repositories.booking_repository import BookingRepository


WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class AvailabilityService:
    def __init__(self, booking_repository: BookingRepository):
        self.booking_repository = booking_repository

    def get_available_slots(self, resource, target_date: date) -> list[dict]:
        """Compute available time slots for a resource on a given date.

        Returns list of {start: "HH:MM", end: "HH:MM", available_capacity: int}.
        """
        availability = resource.availability or {}
        schedule = availability.get("schedule", {})
        exceptions = availability.get("exceptions", [])
        config = resource.config or {}
        buffer_minutes = config.get("buffer_minutes", 0)
        lead_time_hours = availability.get("lead_time_hours", 0)
        max_advance_days = availability.get("max_advance_days", 365)

        # Check lead time
        now = datetime.utcnow()
        if lead_time_hours > 0:
            earliest_bookable = now + timedelta(hours=lead_time_hours)
            if datetime.combine(target_date, datetime.max.time()) < earliest_bookable:
                return []

        # Check max advance days
        days_ahead = (target_date - now.date()).days
        if days_ahead > max_advance_days:
            return []
        if days_ahead < 0:
            return []

        # Check exceptions (closed day)
        target_date_str = target_date.isoformat()
        for exception in exceptions:
            if exception.get("date") == target_date_str and exception.get("closed"):
                return []

        # Get schedule for this weekday
        weekday_name = WEEKDAY_NAMES[target_date.weekday()]

        # Check exception overrides for this date
        exception_slots = None
        for exception in exceptions:
            if exception.get("date") == target_date_str and "slots" in exception:
                exception_slots = exception["slots"]
                break

        time_windows = (
            exception_slots if exception_slots else schedule.get(weekday_name, [])
        )

        if not time_windows:
            return []

        # For flexible-duration resources (hotels), return day availability
        if resource.slot_duration_minutes is None:
            return self._get_flexible_availability(resource, target_date, time_windows)

        # Generate fixed-duration slots
        slots = []
        reference_date = target_date
        slot_duration = timedelta(minutes=resource.slot_duration_minutes)
        buffer = timedelta(minutes=buffer_minutes)

        for window in time_windows:
            window_start_time = self._parse_time(window["start"])
            window_end_dt = datetime.combine(
                reference_date, self._parse_time(window["end"])
            )
            current_dt = datetime.combine(reference_date, window_start_time)

            while current_dt + slot_duration <= window_end_dt:
                slot_end_dt = current_dt + slot_duration

                # Skip if slot is in the past (within lead time)
                if current_dt < now + timedelta(hours=lead_time_hours):
                    current_dt += slot_duration + buffer
                    continue

                # Check if slot is manually blocked
                if self._is_slot_blocked(
                    resource.id, target_date, current_dt.strftime("%H:%M")
                ):
                    current_dt += slot_duration + buffer
                    continue

                # Count existing bookings for this slot
                booked_count = self.booking_repository.count_by_resource_and_slot(
                    resource.id, current_dt, slot_end_dt
                )
                available_capacity = resource.capacity - booked_count

                if available_capacity > 0:
                    slots.append(
                        {
                            "start": current_dt.strftime("%H:%M"),
                            "end": slot_end_dt.strftime("%H:%M"),
                            "available_capacity": available_capacity,
                        }
                    )

                current_dt += slot_duration + buffer

        return slots

    @staticmethod
    def _is_slot_blocked(resource_id, target_date: date, start_time: str) -> bool:
        """Check if a slot is manually blocked."""
        try:
            from vbwd.extensions import db
            from plugins.booking.booking.models.slot_block import (
                BookableResourceSlotBlock,
            )

            return (
                db.session.query(BookableResourceSlotBlock)
                .filter_by(
                    resource_id=resource_id,
                    date=target_date,
                    start_time=start_time,
                )
                .first()
                is not None
            )
        except Exception:
            return False

    def _get_flexible_availability(self, resource, target_date, time_windows):
        """For flexible-duration resources (hotels): check if day is available."""
        booked_count = self.booking_repository.count_by_resource_and_slot(
            resource.id,
            datetime.combine(target_date, datetime.min.time()),
            datetime.combine(target_date, datetime.max.time()),
        )
        available_capacity = resource.capacity - booked_count
        if available_capacity > 0:
            return [
                {
                    "date": target_date.isoformat(),
                    "available_capacity": available_capacity,
                }
            ]
        return []

    @staticmethod
    def _parse_time(time_str: str):
        """Parse 'HH:MM' string to time object."""
        hours, minutes = time_str.split(":")
        return datetime.strptime(f"{hours}:{minutes}", "%H:%M").time()
