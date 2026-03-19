"""Booking plugin events — definitions and email template registration."""


# Event type constants
BOOKING_CREATED = "booking.created"
BOOKING_CONFIRMED = "booking.confirmed"
BOOKING_CANCELLED = "booking.cancelled"
BOOKING_CANCELLED_BY_PROVIDER = "booking.cancelled_by_provider"
BOOKING_CHARGED = "booking.charged"
BOOKING_COMPLETED = "booking.completed"
BOOKING_REMINDER = "booking.reminder"


def register_email_contexts():
    """Register email template variable schemas for booking events."""
    try:
        from plugins.email.booking.services.event_context_registry import (
            EventContextRegistry,
        )
    except ImportError:
        return

    EventContextRegistry.register(
        BOOKING_CREATED,
        {
            "description": "Sent when a new booking is created",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
                "start_at": {"type": "string", "example": "2026-03-20T10:00:00"},
                "end_at": {"type": "string", "example": "2026-03-20T10:30:00"},
                "booking_url": {
                    "type": "string",
                    "example": "/dashboard/bookings/uuid",
                },
            },
        },
    )

    EventContextRegistry.register(
        BOOKING_CONFIRMED,
        {
            "description": "Sent when booking payment is authorized",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
                "start_at": {"type": "string", "example": "2026-03-20T10:00:00"},
                "booking_url": {
                    "type": "string",
                    "example": "/dashboard/bookings/uuid",
                },
            },
        },
    )

    EventContextRegistry.register(
        BOOKING_CANCELLED,
        {
            "description": "Sent when user cancels a booking",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
                "cancelled_by": {"type": "string", "example": "user"},
                "refund_percent": {"type": "integer", "example": 100},
            },
        },
    )

    EventContextRegistry.register(
        BOOKING_CANCELLED_BY_PROVIDER,
        {
            "description": "Sent when provider cancels — always 100% refund",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
                "reason": {"type": "string", "example": "Doctor is unavailable"},
            },
        },
    )

    EventContextRegistry.register(
        BOOKING_COMPLETED,
        {
            "description": "Sent when booking time passes and payment is charged",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
            },
        },
    )

    EventContextRegistry.register(
        BOOKING_REMINDER,
        {
            "description": "Reminder sent before a booking",
            "variables": {
                "user_name": {"type": "string", "example": "Alice"},
                "user_email": {"type": "string", "example": "alice@example.com"},
                "resource_name": {"type": "string", "example": "Dr. Smith"},
                "start_at": {"type": "string", "example": "2026-03-20T10:00:00"},
                "hours_until": {"type": "integer", "example": 24},
            },
        },
    )
