"""Single home for reading the booking plugin's runtime config (DRY).

Reads fresh from the shared ``config_store`` on every call (multi-worker safe,
admin changes take effect without restart) and falls back to the plugin's
``DEFAULT_CONFIG`` for any missing key. Mirrors the shop plugin's helper.

Safe to call outside an application context (e.g. a service unit test with a
mock session): it then returns the ``DEFAULT_CONFIG`` values, so vendor-mode
reads as OFF and the checkout stamp is skipped — never raising.
"""
from typing import Any, Dict

from flask import current_app, has_app_context


def booking_config() -> Dict[str, Any]:
    """The merged booking config: ``DEFAULT_CONFIG`` overlaid with saved values."""
    from plugins.booking import DEFAULT_CONFIG

    merged = {**DEFAULT_CONFIG}
    if has_app_context():
        config_store = getattr(current_app, "config_store", None)
        if config_store is not None:
            merged.update(config_store.get_config("booking") or {})
    return merged


def marketplace_enabled() -> bool:
    """Whether vendor-mode (self-service vendor routes + checkout stamp) is on."""
    return bool(booking_config().get("marketplace_enabled", False))
