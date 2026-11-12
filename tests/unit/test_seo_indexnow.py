"""S154 D4 — booking pings cms's IndexNow seam on resource change.

Unit level: the cms import is monkeypatched (no DB, no cms source needed), so
these run against the per-plugin isolated CI (booking without cms) too, where
the import naturally raises ``ImportError`` and every assertion still holds
(no-op, never a crash).

Engineering requirements (binding, restated): TDD-first · DevOps-first · SOLID ·
DI · DRY · Liskov · clean code · NO OVERENGINEERING.
"""
import logging
from unittest.mock import MagicMock

from plugins.booking.booking.services import seo_indexnow


def _switch_on(monkeypatch, enabled=True):
    monkeypatch.setattr(seo_indexnow, "resources_indexing_enabled", lambda: enabled)


def _fake_cms_ping(monkeypatch):
    ping = MagicMock()
    monkeypatch.setattr(seo_indexnow, "_import_ping_indexnow_urls", lambda: ping)
    return ping


def test_notify_resource_changed_pings_the_resource_path_when_switch_on(monkeypatch):
    ping = _fake_cms_ping(monkeypatch)
    _switch_on(monkeypatch, True)

    seo_indexnow.notify_resource_changed("yoga-room")

    ping.assert_called_once_with(["/booking/yoga-room"])


def test_notify_resource_changed_noop_when_switch_off(monkeypatch):
    ping = _fake_cms_ping(monkeypatch)
    _switch_on(monkeypatch, False)

    seo_indexnow.notify_resource_changed("yoga-room")

    ping.assert_not_called()


def test_notify_resource_changed_noop_without_a_slug(monkeypatch):
    ping = _fake_cms_ping(monkeypatch)
    _switch_on(monkeypatch, True)

    seo_indexnow.notify_resource_changed("")
    seo_indexnow.notify_resource_changed(None)

    ping.assert_not_called()


def test_notify_resources_changed_batches_every_slug_into_one_ping(monkeypatch):
    ping = _fake_cms_ping(monkeypatch)
    _switch_on(monkeypatch, True)

    seo_indexnow.notify_resources_changed(["yoga-room", "spin-bike"])

    ping.assert_called_once_with(["/booking/yoga-room", "/booking/spin-bike"])


def test_notify_resources_changed_noop_when_switch_off(monkeypatch):
    ping = _fake_cms_ping(monkeypatch)
    _switch_on(monkeypatch, False)

    seo_indexnow.notify_resources_changed(["yoga-room"])

    ping.assert_not_called()


def test_noop_when_cms_is_not_importable(monkeypatch):
    def _missing_cms():
        raise ImportError("No module named 'plugins.cms'")

    monkeypatch.setattr(seo_indexnow, "_import_ping_indexnow_urls", _missing_cms)
    _switch_on(monkeypatch, True)

    # Never raises — the plugin keeps working with cms absent/disabled.
    seo_indexnow.notify_resource_changed("yoga-room")


def test_ping_failure_is_swallowed(monkeypatch, caplog):
    ping = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(seo_indexnow, "_import_ping_indexnow_urls", lambda: ping)
    _switch_on(monkeypatch, True)

    with caplog.at_level(logging.WARNING):
        seo_indexnow.notify_resource_changed("yoga-room")

    assert caplog.records
