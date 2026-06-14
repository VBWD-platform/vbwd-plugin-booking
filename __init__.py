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

    def _register_data_exchangers(self) -> None:
        """Register the booking entity exchangers into the data-exchange seam.

        Core declares none of these (it stays agnostic); the plugin adds them on
        enable through the shared ``db.session`` so bookings appear on the
        generic Settings → Import/Export page. Clear-safe: re-registering
        replaces by key (per-test app re-enable).
        """
        import logging

        try:
            from vbwd.extensions import db
            from plugins.booking.booking.services.data_exchange.booking_exchangers import (  # noqa: E501
                register_booking_exchangers,
            )

            register_booking_exchangers(db.session)
        except Exception as exchanger_error:
            logging.getLogger(__name__).warning(
                "[booking] Failed to register data exchangers: %s", exchanger_error
            )

    def on_enable(self):
        super().on_enable()

        from plugins.booking.booking.events import register_email_contexts

        register_email_contexts()

        self._register_data_exchangers()

        # S77 — register booking_resource as taggable/custom-field-able so the
        # core value endpoints resolve it (gated by booking.resources.manage)
        # and the resource serializer can append tags / custom fields.
        from vbwd.services.entity_type_registry import (
            EntityTypeRegistration,
            register_entity_type,
        )

        register_entity_type(
            EntityTypeRegistration(
                "booking_resource", "Booking resource", "booking.resources.manage"
            )
        )

        # S88 — contribute the booking catalog seed to ``flask reset-demo``
        # through the agnostic demo-data registry (core imports no booking model).
        from vbwd.services.demo_data_registry import register_catalog_seeder
        from plugins.booking.booking.demo_seed import seed_catalog

        register_catalog_seeder(seed_catalog)

        # S09 — register the plugin's repositories with the DI container so
        # the payment handler / completion service / consumers can resolve
        # them via `current_app.container.booking_<name>_repository()`
        # instead of constructing inline with `db.session`.
        from flask import current_app

        from vbwd.plugins.di_helpers import register_repositories
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )
        from plugins.booking.booking.repositories.custom_schema_repository import (
            CustomSchemaRepository,
        )
        from plugins.booking.booking.repositories.export_rule_repository import (
            ExportRuleRepository,
        )
        from plugins.booking.booking.repositories.resource_category_repository import (  # noqa: E501
            ResourceCategoryRepository,
        )
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )

        container = getattr(current_app, "container", None)
        if container is not None:
            register_repositories(
                container,
                {
                    "booking_booking_repository": BookingRepository,
                    "booking_resource_repository": ResourceRepository,
                    "booking_resource_category_repository": ResourceCategoryRepository,
                    "booking_custom_schema_repository": CustomSchemaRepository,
                    "booking_export_rule_repository": ExportRuleRepository,
                },
            )

        # Register PDF template path with the core PdfService once enabled.
        # Running outside an app context (e.g. test import) is fine — the PDF
        # route re-registers as a fallback before rendering.
        try:
            import os

            from flask import current_app

            pdf_service = current_app.container.pdf_service()  # type: ignore[attr-defined]
            template_dir = os.path.join(
                os.path.dirname(__file__), "booking", "templates", "pdf"
            )
            pdf_service.register_plugin_template_path(template_dir)
        except Exception:
            pass

        # Booking auto-completion scheduler (S01 — moved out of core).
        # Skip under TESTING: every test builds its own app and runs on_enable,
        # which would otherwise spin up a background thread per test app and
        # leak threads + DB connections across a full-suite run. Subscription
        # plugin's scheduler guards itself the same way.
        import logging

        scheduler_logger = logging.getLogger(__name__)
        try:
            from flask import current_app

            if not current_app.config.get("TESTING"):
                from plugins.booking.booking.scheduler import (
                    start_booking_scheduler,
                )

                start_booking_scheduler(current_app._get_current_object())
        except Exception as scheduler_error:
            scheduler_logger.warning(
                "[booking] Failed to start scheduler: %s", scheduler_error
            )

    def on_disable(self):
        super().on_disable()
        from vbwd.services.entity_type_registry import unregister_entity_type

        unregister_entity_type("booking_resource")

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
