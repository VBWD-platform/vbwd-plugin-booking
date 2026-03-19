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

    def on_enable(self):
        from plugins.booking.booking.events import register_email_contexts

        register_email_contexts()
