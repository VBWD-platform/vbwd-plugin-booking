from vbwd.plugins.base import BasePlugin, PluginMetadata


DEFAULT_CONFIG = {
    "default_timezone": "Europe/Berlin",
    "max_advance_booking_days": 90,
    "min_lead_time_hours": 1,
    "cancellation_grace_period_hours": 24,
    "default_confirmation_mode": "auto",
    "default_slot_duration_minutes": 60,
    "default_buffer_minutes": 15,
    "invoice_prefix": "BK",
    "enable_recurring_bookings": False,
    "max_bookings_per_user_per_day": 5,
    "capture_mode": "manual",
}


class BookingPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="booking",
            version="0.1.0",
            author="VBWD",
            description="Booking plugin — appointments, rooms, spaces, seats",
            dependencies=["email"],
        )

    def initialize(self, config=None):
        merged = {**DEFAULT_CONFIG}
        if config:
            merged.update(config)
        super().initialize(merged)

    def on_enable(self):
        """Register PDF template path with the core PdfService once enabled."""
        super().on_enable()
        try:
            import os

            from flask import current_app

            pdf_service = current_app.container.pdf_service()  # type: ignore[attr-defined]
            template_dir = os.path.join(
                os.path.dirname(__file__), "booking", "templates", "pdf"
            )
            pdf_service.register_plugin_template_path(template_dir)
        except Exception:
            # Running outside an app context (e.g. test import). The PDF
            # route re-registers as a fallback before rendering.
            pass

    def get_blueprint(self):
        from plugins.booking.booking.routes import booking_bp

        return booking_bp

    def get_url_prefix(self) -> str:
        return ""

    @property
    def admin_permissions(self):
        return [
            {
                "key": "booking.resources.view",
                "label": "View resources",
                "group": "Booking",
            },
            {
                "key": "booking.resources.manage",
                "label": "Manage resources",
                "group": "Booking",
            },
            {
                "key": "booking.bookings.view",
                "label": "View bookings",
                "group": "Booking",
            },
            {
                "key": "booking.bookings.manage",
                "label": "Manage bookings",
                "group": "Booking",
            },
            {
                "key": "booking.schemas.manage",
                "label": "Manage schemas",
                "group": "Booking",
            },
            {
                "key": "booking.configure",
                "label": "Booking settings",
                "group": "Booking",
            },
        ]

    def on_enable(self):
        from plugins.booking.booking.events import register_email_contexts

        register_email_contexts()

    def register_event_handlers(self, event_bus):
        import logging

        logger = logging.getLogger(__name__)

        from vbwd.extensions import db
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )
        from plugins.booking.booking.handlers.payment_handler import (
            BookingPaymentHandler,
        )

        handler = BookingPaymentHandler(
            session=db.session,
            booking_repository=BookingRepository(db.session),
            resource_repository=ResourceRepository(db.session),
            event_bus=event_bus,
        )
        event_bus.subscribe("invoice.paid", handler.on_invoice_paid)
        event_bus.subscribe("invoice.refunded", handler.on_invoice_refunded)
        logger.info(
            "[booking] Event handlers registered (invoice.paid, invoice.refunded)"
        )

        # Auto-capture: when booking completes, capture authorized payment
        from flask import current_app

        container = getattr(current_app, "container", None)
        if container:
            from vbwd.handlers.auto_capture_handler import AutoCaptureHandler

            auto_capture = AutoCaptureHandler(container)
            event_bus.subscribe("booking.completed", auto_capture.on_booking_completed)
