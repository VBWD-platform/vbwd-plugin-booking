from vbwd.plugins.base import BasePlugin, PluginMetadata


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

    def get_blueprint(self):
        from plugins.booking.booking.routes import booking_bp

        return booking_bp

    def get_url_prefix(self) -> str:
        return ""
