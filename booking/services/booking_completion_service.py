"""BookingCompletionService — auto-completes bookings whose time has passed."""
import logging
import os

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


class BookingCompletionService:
    def __init__(self, booking_repository, resource_repository, event_bus):
        self.booking_repository = booking_repository
        self.resource_repository = resource_repository
        self.event_bus = event_bus

    def complete_past_bookings(self) -> list:
        """Find confirmed bookings with end_at in the past and complete them.

        Returns list of completed booking IDs.
        """
        past_bookings = self.booking_repository.find_past_confirmed()
        completed_ids = []

        for booking in past_bookings:
            booking.status = "completed"

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

            completed_ids.append(booking.id)
            logger.info("Auto-completed booking %s", booking.id)

        return completed_ids

    def _resolve_user(self, user_id) -> tuple[str, str]:
        from vbwd.models.user import User

        user = self.booking_repository.session.get(User, user_id)
        if not user:
            return ("", "")
        return (user.email, user.email)
