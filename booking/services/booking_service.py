"""BookingService — create, cancel, complete bookings."""
from datetime import datetime

from plugins.booking.booking.repositories.booking_repository import BookingRepository
from plugins.booking.booking.repositories.resource_repository import ResourceRepository
from plugins.booking.booking.services.availability_service import AvailabilityService
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)
from plugins.booking.booking.models.booking import Booking


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
            self.event_bus.publish(
                "booking.created",
                {
                    "user_id": str(user_id),
                    "booking_id": str(booking.id),
                    "resource_name": resource.name,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
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
            self.event_bus.publish(
                "booking.cancelled",
                {
                    "user_id": str(booking.user_id),
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                    "cancelled_by": cancelled_by,
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
            self.event_bus.publish(
                "booking.cancelled_by_provider",
                {
                    "user_id": str(booking.user_id),
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                    "reason": reason,
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
            self.event_bus.publish(
                "booking.completed",
                {
                    "user_id": str(booking.user_id),
                    "booking_id": str(booking.id),
                    "resource_name": resource.name if resource else "Unknown",
                },
            )

        return booking

    def get_user_bookings(self, user_id) -> list[Booking]:
        """Get all bookings for a user."""
        return self.booking_repository.find_by_user(user_id)

    def get_booking(self, booking_id) -> Booking | None:
        """Get a single booking by ID."""
        return self.booking_repository.find_by_id(booking_id)
