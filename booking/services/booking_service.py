"""BookingService — create, cancel, complete, reschedule bookings."""
import os
from datetime import datetime

from vbwd.utils.datetime_utils import utcnow

from plugins.booking.booking.repositories.booking_repository import BookingRepository
from plugins.booking.booking.repositories.resource_repository import ResourceRepository
from plugins.booking.booking.services.availability_service import AvailabilityService
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)
from plugins.booking.booking.models.booking import Booking

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


class BookingError(Exception):
    """Raised when a booking operation fails."""

    pass


class BookingService:
    def __init__(
        self,
        booking_repository: BookingRepository,
        resource_repository: ResourceRepository,
        availability_service: AvailabilityService,
        invoice_service: BookingInvoiceService,
        event_bus=None,
    ):
        self.booking_repository = booking_repository
        self.resource_repository = resource_repository
        self.availability_service = availability_service
        self.invoice_service = invoice_service
        self.event_bus = event_bus

    def _resolve_user(self, user_id) -> tuple[str, str]:
        """Return (user_email, user_name) for a user_id."""
        from vbwd.models.user import User

        user = self.booking_repository.session.get(User, user_id)
        if not user:
            return ("", "")
        return (user.email, user.email)

    def create_booking(
        self,
        user_id,
        resource_slug: str,
        start_at: datetime,
        end_at: datetime,
        quantity: int = 1,
        custom_fields: dict | None = None,
        notes: str | None = None,
    ) -> Booking:
        """Create a new booking after checking availability."""
        resource = self.resource_repository.find_by_slug(resource_slug)
        if not resource:
            raise BookingError(f"Resource '{resource_slug}' not found")

        if not resource.is_active:
            raise BookingError(f"Resource '{resource_slug}' is not active")

        # Check capacity
        booked_count = self.booking_repository.count_by_resource_and_slot(
            resource.id, start_at, end_at
        )
        available_capacity = resource.capacity - booked_count
        if quantity > available_capacity:
            raise BookingError(
                f"Not enough capacity: requested {quantity}, "
                f"available {available_capacity}"
            )

        # Create booking
        booking = Booking()
        booking.resource_id = resource.id
        booking.user_id = user_id
        booking.start_at = start_at
        booking.end_at = end_at
        booking.status = "pending"
        booking.quantity = quantity
        booking.custom_fields = custom_fields or {}
        booking.notes = notes
        self.booking_repository.save(booking)

        # Create invoice
        invoice = self.invoice_service.create_booking_invoice(
            user_id, resource, booking
        )
        booking.invoice_id = invoice.id

        # Publish event
        if self.event_bus:
            user_email, user_name = self._resolve_user(user_id)
            self.event_bus.publish(
                "booking.created",
                {
                    "user_id": str(user_id),
                    "user_email": user_email,
                    "user_name": user_name,
                    "booking_id": str(booking.id),
                    "resource_name": resource.name,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "booking_url": f"{FRONTEND_URL}/dashboard/bookings/{booking.id}",
                },
            )

        return booking

    def cancel_booking(self, booking_id, cancelled_by: str = "user") -> Booking:
        """Cancel a booking."""
        booking = self.booking_repository.find_by_id(booking_id)
        if not booking:
            raise BookingError("Booking not found")

        if booking.status in ("cancelled", "completed"):
            raise BookingError(f"Cannot cancel booking with status '{booking.status}'")

        booking.status = "cancelled"

        if self.event_bus:
            resource = self.resource_repository.find_by_id(booking.resource_id)
            user_email, user_name = self._resolve_user(booking.user_id)
            self.event_bus.publish(
                "booking.cancelled",
                {
                    "user_id": str(booking.user_id),
                    "user_email": user_email,
                    "user_name": user_name,
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                    "cancelled_by": cancelled_by,
                    "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
                },
            )

        return booking

    def cancel_by_provider(self, booking_id, reason: str) -> Booking:
        """Cancel a booking by provider — always 100% refund."""
        booking = self.booking_repository.find_by_id(booking_id)
        if not booking:
            raise BookingError("Booking not found")

        if booking.status in ("cancelled", "completed"):
            raise BookingError(f"Cannot cancel booking with status '{booking.status}'")

        booking.status = "cancelled"

        if self.event_bus:
            resource = self.resource_repository.find_by_id(booking.resource_id)
            user_email, user_name = self._resolve_user(booking.user_id)
            self.event_bus.publish(
                "booking.cancelled_by_provider",
                {
                    "user_id": str(booking.user_id),
                    "user_email": user_email,
                    "user_name": user_name,
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                    "reason": reason,
                    "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
                },
            )

        return booking

    def complete_booking(self, booking_id) -> Booking:
        """Mark a booking as completed."""
        booking = self.booking_repository.find_by_id(booking_id)
        if not booking:
            raise BookingError("Booking not found")

        if booking.status != "confirmed":
            raise BookingError(
                f"Can only complete confirmed bookings, got '{booking.status}'"
            )

        booking.status = "completed"

        if self.event_bus:
            resource = self.resource_repository.find_by_id(booking.resource_id)
            user_email, user_name = self._resolve_user(booking.user_id)
            self.event_bus.publish(
                "booking.completed",
                {
                    "user_id": str(booking.user_id),
                    "user_email": user_email,
                    "user_name": user_name,
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                    "invoice_id": str(booking.invoice_id)
                    if booking.invoice_id
                    else None,
                    "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
                },
            )

        return booking

    def reschedule_booking(
        self,
        booking_id,
        user_id,
        new_start_at: datetime,
        new_end_at: datetime,
        *,
        cancellation_grace_period_hours: int,
        min_lead_time_hours: int,
    ) -> Booking:
        """Reschedule an upcoming booking in-place.

        Per Sprint 28 Q2: the invoice is NOT touched. Only booking.start_at
        and booking.end_at change; status remains as-is. An audit line is
        appended to admin_notes, and "booking.rescheduled" is emitted.

        Per Sprint 28 Q3: the same grace period as cancel applies regardless
        of status (so a pending-unpaid booking can't be moved late either).

        Raises BookingError on any validation failure.
        """
        booking = self.booking_repository.find_by_id(booking_id)
        if not booking:
            raise BookingError("Booking not found")

        if str(booking.user_id) != str(user_id):
            raise BookingError("Only the booking owner may reschedule")

        if booking.status not in ("pending", "confirmed"):
            raise BookingError(
                f"Cannot reschedule booking with status '{booking.status}'"
            )

        now = utcnow()

        # Cut-off: the *original* start must still be outside the grace window.
        grace_seconds = cancellation_grace_period_hours * 3600
        current_start = self._as_naive(booking.start_at)
        if (current_start - self._as_naive(now)).total_seconds() < grace_seconds:
            raise BookingError(
                "Reschedule grace period has passed — booking is too close to its start time"
            )

        # New start must respect min lead time.
        lead_seconds = min_lead_time_hours * 3600
        if (
            self._as_naive(new_start_at) - self._as_naive(now)
        ).total_seconds() < lead_seconds:
            raise BookingError(
                "New start time is in the past or violates the minimum lead time"
            )

        if new_end_at <= new_start_at:
            raise BookingError("New end time must be after the new start time")

        # Capacity check on the new slot — exclude this booking so the
        # resource doesn't compete with itself when the new slot overlaps.
        resource = self.resource_repository.find_by_id(booking.resource_id)
        if not resource:
            raise BookingError("Resource for this booking no longer exists")

        concurrent_count = self.booking_repository.count_by_resource_and_slot(
            resource.id,
            new_start_at,
            new_end_at,
            exclude_booking_id=booking.id,
        )
        available_capacity = resource.capacity - concurrent_count
        if booking.quantity > available_capacity:
            raise BookingError("Requested slot is at full capacity / unavailable")

        old_start_at = booking.start_at
        booking.start_at = new_start_at
        booking.end_at = new_end_at

        audit_line = (
            f"Rescheduled from {old_start_at.isoformat()} to {new_start_at.isoformat()} "
            f"at {now.isoformat()}"
        )
        existing_notes = booking.admin_notes or ""
        booking.admin_notes = (
            f"{existing_notes}\n{audit_line}".strip() if existing_notes else audit_line
        )

        self.booking_repository.save(booking)

        if self.event_bus:
            user_email, user_name = self._resolve_user(booking.user_id)
            self.event_bus.publish(
                "booking.rescheduled",
                {
                    "user_id": str(booking.user_id),
                    "user_email": user_email,
                    "user_name": user_name,
                    "booking_id": str(booking.id),
                    "resource_name": resource.name,
                    "old_start_at": old_start_at.isoformat(),
                    "new_start_at": new_start_at.isoformat(),
                    "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings/{booking.id}",
                },
            )

        return booking

    @staticmethod
    def _as_naive(value: datetime) -> datetime:
        """Drop tzinfo for arithmetic when Python is mixing aware + naive.

        The codebase stores times as naive UTC; `utcnow()` returns a naive
        UTC datetime. Incoming API datetimes may be tz-aware — normalise so
        subtractions don't throw.
        """
        if value.tzinfo is None:
            return value
        return value.replace(tzinfo=None)

    def get_user_bookings(self, user_id) -> list[Booking]:
        """Get all bookings for a user."""
        return self.booking_repository.find_by_user(user_id)

    def get_booking(self, booking_id) -> Booking | None:
        """Get a single booking by ID."""
        return self.booking_repository.find_by_id(booking_id)
