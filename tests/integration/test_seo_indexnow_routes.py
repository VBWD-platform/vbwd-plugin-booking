"""S154 D4 — the admin/vendor resource routes trigger the IndexNow ping.

End-to-end through the real Flask route (not just the ``seo_indexnow`` unit),
so the wiring from ``routes.py`` into ``notify_resource_changed`` /
``notify_resources_changed`` is exercised. The cms import is monkeypatched at
``seo_indexnow._import_ping_indexnow_urls`` (no real cms/network needed), and
the fe-admin "indexable" switch is driven through the real ``config_store``.

Engineering requirements (binding, restated): TDD-first · DevOps-first · SOLID ·
DI · DRY · Liskov · clean code · NO OVERENGINEERING.
"""
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.user import User


@pytest.fixture
def client(app):
    return app.test_client()


def _make_admin(db):
    admin = User(
        id=uuid4(),
        email=f"admin-{uuid4().hex[:8]}@example.com",
        password_hash="x",
        status=UserStatus.ACTIVE,
        role=UserRole.ADMIN,
    )
    db.session.add(admin)
    db.session.commit()
    return admin


def _auth_as_admin(monkeypatch, admin):
    import vbwd.middleware.auth as auth_mod

    repo = MagicMock()
    repo.find_by_id.return_value = admin
    svc = MagicMock()
    svc.verify_token.return_value = str(admin.id)
    monkeypatch.setattr(auth_mod, "UserRepository", lambda *a, **k: repo)
    monkeypatch.setattr(auth_mod, "AuthService", lambda *a, **k: svc)
    monkeypatch.setattr(type(admin), "is_admin", property(lambda self: True))
    monkeypatch.setattr(type(admin), "has_permission", lambda self, perm: True)


class _IndexableConfigStore:
    """A fake ``config_store`` driving booking's fe-admin "indexable" switch."""

    def __init__(self, resources_on):
        self._config = {"seo_index_resources": resources_on}

    def get_config(self, plugin_name):
        return self._config if plugin_name == "booking" else {}


HEADERS = {"Authorization": "Bearer valid"}


def _fake_ping(monkeypatch):
    from plugins.booking.booking.services import seo_indexnow

    ping = MagicMock()
    monkeypatch.setattr(seo_indexnow, "_import_ping_indexnow_urls", lambda: ping)
    return ping


def _make_resource(db, **overrides):
    from plugins.booking.booking.models.resource import BookableResource

    fields = {
        "id": uuid4(),
        "name": "Room A",
        "slug": f"room-{uuid4().hex[:8]}",
        "price": Decimal("100.00"),
        "is_active": True,
    }
    fields.update(overrides)
    resource = BookableResource(**fields)
    db.session.add(resource)
    db.session.commit()
    return resource


def test_create_resource_pings_indexnow_when_switch_on(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=True))

    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={"name": "Yoga Room", "slug": "yoga-room", "price": "25.00"},
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    ping.assert_called_once_with(["/booking/yoga-room"])


def test_create_resource_does_not_ping_when_switch_off(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=False))

    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={"name": "Spin Bike", "slug": "spin-bike", "price": "25.00"},
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    ping.assert_not_called()


def test_update_resource_pings_indexnow(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    resource = _make_resource(db, slug="room-update")
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=True))

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"price": "50.00"},
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    ping.assert_called_once_with(["/booking/room-update"])


def test_update_resource_slug_rename_pings_both_urls(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    resource = _make_resource(db, slug="old-room")
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=True))

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"slug": "new-room"},
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    ping.assert_called_once_with(["/booking/old-room", "/booking/new-room"])


def test_update_resource_is_active_toggle_pings_indexnow(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    resource = _make_resource(db, slug="room-toggle", is_active=True)
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=True))

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"is_active": False},
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    ping.assert_called_once_with(["/booking/room-toggle"])


def test_delete_resource_pings_indexnow_with_its_slug(app, db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)
    resource = _make_resource(db, slug="room-delete")
    ping = _fake_ping(monkeypatch)
    monkeypatch.setattr(app, "config_store", _IndexableConfigStore(resources_on=True))

    resp = client.delete(
        f"/api/v1/admin/booking/resources/{resource.id}",
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    ping.assert_called_once_with(["/booking/room-delete"])
