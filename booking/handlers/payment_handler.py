"""BookingPaymentHandler — creates/cancels bookings on invoice events."""
import logging
import os
from datetime import datetime

from plugins.booking.booking.models.booking import Booking

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


class BookingPaymentHandler:
    """Listens for ``invoice.paid`` / ``invoice.refunded`` to create
    or cancel Booking records linked to booking invoices.
    """

    def __init__(self, session, booking_repository, resource_repository, event_bus):
        self._session_factory = session
        self.event_bus = event_bus

    @property
    def _session(self):
        """Get the current scoped session (fresh per request)."""
        from vbwd.extensions import db

        return db.session

    def _get_booking_repo(self):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        return BookingRepository(self._session)

    def _get_resource_repo(self):
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )

        return ResourceRepository(self._session)

    def _resolve_user(self, user_id) -> tuple[str, str]:
        """Return (user_email, user_name) for a user_id."""
        from vbwd.models.user import User

        user = self._session.get(User, user_id)
        if not user:
            return ("", "")
        return (user.email, user.email)

    def on_invoice_paid(self, event_name: str, data: dict) -> None:
        """EventBus callback — signature: (event_name, data)."""
        invoice_id = data.get("invoice_id")
        if not invoice_id:
            return

        from vbwd.models.invoice import UserInvoice

        invoice = (
            self._session.query(UserInvoice)
            .filter_by(invoice_number=invoice_id)
            .first()
        )
        if not invoice:
            logger.debug("Booking handler: invoice %s not found", invoice_id)
            return

        for line_item in invoice.line_items:
            extra = line_item.extra_data or {}
            if extra.get("plugin") != "booking":
                continue

            resource = self._get_resource_repo().find_by_slug(
                extra.get("resource_slug", "")
            )
            if not resource:
                logger.warning(
                    "Booking handler: resource '%s' not found, skipping",
                    extra.get("resource_slug"),
                )
                continue

            booking = Booking()
            booking.resource_id = resource.id
            booking.user_id = invoice.user_id
            booking.invoice_id = invoice.id
            booking.start_at = datetime.fromisoformat(extra["start_at"])
            booking.end_at = datetime.fromisoformat(extra["end_at"])
            booking.status = "confirmed"
            booking.quantity = extra.get("quantity", 1)
            booking.custom_fields = extra.get("custom_fields", {})
            booking.notes = extra.get("notes")

            self._get_booking_repo().save(booking)

            # Write booking_id back to line item metadata
            line_item.extra_data = {**extra, "booking_id": str(booking.id)}

            if self.event_bus:
                user_email, user_name = self._resolve_user(invoice.user_id)
                self.event_bus.publish(
                    "booking.created",
                    {
                        "user_id": str(invoice.user_id),
                        "user_email": user_email,
                        "user_name": user_name,
                        "booking_id": str(booking.id),
                        "resource_name": resource.name,
                        "start_at": extra["start_at"],
                        "end_at": extra["end_at"],
                        "booking_url": f"{FRONTEND_URL}/dashboard/bookings/{booking.id}",
                    },
                )

            logger.info(
                "Booking created from invoice %s for resource %s",
                invoice_id,
                resource.slug,
            )

    def on_invoice_refunded(self, event_name: str, data: dict) -> None:
        """Cancel all bookings linked to a refunded invoice."""
        invoice_uuid = data.get("invoice_uuid")
        if not invoice_uuid:
            return

        bookings = self._get_booking_repo().find_by_invoice_id(invoice_uuid)

        for booking in bookings:
            if booking.status in ("cancelled", "completed"):
                continue

            booking.status = "cancelled"

            if self.event_bus:
                user_email, user_name = self._resolve_user(booking.user_id)
                self.event_bus.publish(
                    "booking.cancelled",
                    {
                        "user_id": str(booking.user_id),
                        "user_email": user_email,
                        "user_name": user_name,
                        "booking_id": str(booking.id),
                        "cancelled_by": "refund",
                        "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
                    },
                )

            logger.info(
                "Booking %s cancelled due to invoice refund",
                booking.id,
            )
