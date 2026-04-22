"""Tests for GET /api/v1/booking/config — public policy values endpoint."""
from unittest.mock import MagicMock, patch

from flask import Flask


def _make_app_with_booking_plugin(plugin_config: dict):
    """Build a throwaway Flask app that hosts only the booking blueprint
    and a stub plugin_manager — fast and isolated from the full app factory.
    """
    from plugins.booking.booking.routes import booking_bp

    flask_app = Flask(__name__)
    flask_app.register_blueprint(booking_bp)

    stub_plugin = MagicMock()
    stub_plugin.get_config.side_effect = lambda key, default=None: plugin_config.get(
        key, default
    )

    plugin_manager = MagicMock()
    plugin_manager.get_plugin.return_value = stub_plugin

    flask_app.plugin_manager = plugin_manager  # type: ignore[attr-defined]
    return flask_app, plugin_manager, stub_plugin


class TestBookingConfigEndpoint:
    def test_returns_configured_values(self):
        config = {
            "cancellation_grace_period_hours": 48,
            "min_lead_time_hours": 2,
            "max_advance_booking_days": 120,
            "default_slot_duration_minutes": 30,
        }
        flask_app, plugin_manager, _ = _make_app_with_booking_plugin(config)

        with flask_app.test_client() as client:
            response = client.get("/api/v1/booking/config")

        assert response.status_code == 200
        body = response.get_json()
        assert body["cancellation_grace_period_hours"] == 48
        assert body["min_lead_time_hours"] == 2
        assert body["max_advance_booking_days"] == 120
        assert body["default_slot_duration_minutes"] == 30
        plugin_manager.get_plugin.assert_called_with("booking")

    def test_returns_defaults_when_plugin_has_no_overrides(self):
        flask_app, _, _ = _make_app_with_booking_plugin({})

        with flask_app.test_client() as client:
            response = client.get("/api/v1/booking/config")

        assert response.status_code == 200
        body = response.get_json()
        # Endpoint must return its documented shape even when the plugin
        # config is empty — hardcoded defaults should fall through.
        assert body["cancellation_grace_period_hours"] == 24
        assert body["min_lead_time_hours"] == 1
        assert body["max_advance_booking_days"] == 90
        assert body["default_slot_duration_minutes"] == 60

    def test_is_public_no_auth_required(self):
        flask_app, _, _ = _make_app_with_booking_plugin(
            {"cancellation_grace_period_hours": 12}
        )

        with flask_app.test_client() as client:
            response = client.get("/api/v1/booking/config")

        assert response.status_code == 200

    def test_returns_503_when_plugin_missing(self):
        from plugins.booking.booking.routes import booking_bp

        flask_app = Flask(__name__)
        flask_app.register_blueprint(booking_bp)

        plugin_manager = MagicMock()
        plugin_manager.get_plugin.return_value = None
        flask_app.plugin_manager = plugin_manager  # type: ignore[attr-defined]

        with flask_app.test_client() as client:
            response = client.get("/api/v1/booking/config")

        assert response.status_code == 503
