"""Vendor-mode config flag defaults OFF (classic behaviour unchanged).

``marketplace_enabled`` gates the whole vendor surface (self-service route +
the checkout stamp). It must default to ``False`` so an install that never
enables the marketplace behaves exactly as before, and it must be safe to read
outside an application context (service unit tests).
"""


def test_default_config_marketplace_disabled():
    from plugins.booking import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.get("marketplace_enabled") is False


def test_marketplace_enabled_reads_config():
    from flask import Flask

    from plugins.booking.booking.services import plugin_config

    app = Flask(__name__)

    class _Store:
        def __init__(self, value):
            self._value = value

        def get_config(self, plugin_name):
            assert plugin_name == "booking"
            return {"marketplace_enabled": self._value}

    with app.app_context():
        app.config_store = _Store(True)  # type: ignore[attr-defined]
        assert plugin_config.marketplace_enabled() is True
        app.config_store = _Store(False)  # type: ignore[attr-defined]
        assert plugin_config.marketplace_enabled() is False


def test_marketplace_enabled_defaults_false_without_store():
    from flask import Flask

    from plugins.booking.booking.services import plugin_config

    app = Flask(__name__)
    with app.app_context():
        # No config_store attached → fall back to DEFAULT_CONFIG (False).
        assert plugin_config.marketplace_enabled() is False


def test_marketplace_enabled_defaults_false_without_app_context():
    from plugins.booking.booking.services import plugin_config

    # No application context at all → safe default (False), never raises.
    assert plugin_config.marketplace_enabled() is False
