"""Vendor self-service route — gated + permission-checked.

When ``marketplace_enabled`` is False the vendor surface is invisible (403);
when True a user holding ``marketplace.vendor`` can create a bookable resource
they own (``vendor_id`` = their user id). A plain user is rejected even when the
flag is on.
"""
from uuid import uuid4

from plugins.booking.booking import routes as booking_routes


VENDOR_RESOURCES_PATH = "/api/v1/booking/vendor/resources"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client, db, email):
    from vbwd.models.user import User

    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Vendor123@"},
    )
    assert register_response.status_code in (200, 201), register_response.data
    user = db.session.query(User).filter_by(email=email).first()
    user.status = "ACTIVE"
    db.session.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Vendor123@"}
    )
    body = login.get_json()
    token = body.get("token") or body.get("access_token")
    assert token, login.data
    return user, token


def _grant_vendor_permission(db, user):
    """Attach a user access level carrying ``marketplace.vendor`` to ``user``."""
    from vbwd.models.role import Permission
    from vbwd.models.user_access_level import UserAccessLevel

    permission = (
        db.session.query(Permission).filter_by(name="marketplace.vendor").first()
    )
    if permission is None:
        permission = Permission(
            id=uuid4(),
            name="marketplace.vendor",
            description="Sell as a vendor",
            resource="marketplace",
            action="vendor",
        )
        db.session.add(permission)
    suffix = uuid4().hex[:8]
    level = UserAccessLevel(
        id=uuid4(),
        slug=f"vendor-{suffix}",
        name=f"Vendor {suffix}",
    )
    level.permissions.append(permission)
    user.assigned_user_access_levels.append(level)
    db.session.commit()


def _make_vendor(client, db, email):
    user, token = _register_and_login(client, db, email)
    _grant_vendor_permission(db, user)
    return user, token


def _enable_marketplace(monkeypatch, enabled):
    monkeypatch.setattr(booking_routes, "marketplace_enabled", lambda: enabled)


def _resource_body(name="Vendor Room"):
    return {"name": name, "price": 12.5}


def test_vendor_create_blocked_when_marketplace_disabled(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"v-off-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, False)

    resp = client.post(
        VENDOR_RESOURCES_PATH, json=_resource_body(), headers=_auth(token)
    )
    assert resp.status_code == 403, resp.get_json()


def test_vendor_create_requires_permission(client, db, monkeypatch):
    _user, token = _register_and_login(
        client, db, f"plain-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    resp = client.post(
        VENDOR_RESOURCES_PATH, json=_resource_body(), headers=_auth(token)
    )
    assert resp.status_code == 403, resp.get_json()


def test_vendor_create_sets_vendor_id(client, db, monkeypatch):
    user, token = _make_vendor(client, db, f"v-create-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resp = client.post(
        VENDOR_RESOURCES_PATH,
        json=_resource_body("My Room"),
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.get_json()
    resource = resp.get_json()["resource"]
    assert resource["vendor_id"] == str(user.id)
    assert resource["is_active"] is True
    assert resource["slug"]  # auto-generated when omitted


def _create_resource(client, token, name="Vendor Room"):
    resp = client.post(
        VENDOR_RESOURCES_PATH, json=_resource_body(name), headers=_auth(token)
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["resource"]


# ── READ: list ──────────────────────────────────────────────────────


def test_vendor_list_returns_only_owned(client, db, monkeypatch):
    owner, owner_token = _make_vendor(
        client, db, f"v-list-a-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"v-list-b-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    mine = _create_resource(client, owner_token, "Mine A")
    _create_resource(client, other_token, "Theirs B")

    resp = client.get(VENDOR_RESOURCES_PATH, headers=_auth(owner_token))
    assert resp.status_code == 200, resp.get_json()
    resources = resp.get_json()["resources"]
    returned_ids = {res["id"] for res in resources}
    assert mine["id"] in returned_ids
    assert all(res["vendor_id"] == str(owner.id) for res in resources)


def test_vendor_list_blocked_when_marketplace_disabled(client, db, monkeypatch):
    _owner, token = _make_vendor(
        client, db, f"v-list-off-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, False)

    resp = client.get(VENDOR_RESOURCES_PATH, headers=_auth(token))
    assert resp.status_code == 403, resp.get_json()


# ── READ: single ────────────────────────────────────────────────────


def test_vendor_get_single_owned(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-get-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, token, "Get Room")

    resp = client.get(f"{VENDOR_RESOURCES_PATH}/{created['id']}", headers=_auth(token))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["resource"]["id"] == created["id"]


def test_vendor_get_missing_returns_404(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-get-404-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resp = client.get(f"{VENDOR_RESOURCES_PATH}/{uuid4()}", headers=_auth(token))
    assert resp.status_code == 404, resp.get_json()


def test_vendor_get_not_owned_returns_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"v-get-own-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"v-get-oth-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, owner_token, "Owned Room")

    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}", headers=_auth(other_token)
    )
    assert resp.status_code == 403, resp.get_json()


# ── UPDATE ──────────────────────────────────────────────────────────


def test_vendor_update_owned(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-upd-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, token, "Before")

    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}",
        json={"name": "After", "price": 99.0, "is_active": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.get_json()
    resource = resp.get_json()["resource"]
    assert resource["name"] == "After"
    assert resource["price"] == 99.0
    assert resource["is_active"] is False


def test_vendor_update_missing_returns_404(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-upd-404-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{uuid4()}",
        json={"name": "X"},
        headers=_auth(token),
    )
    assert resp.status_code == 404, resp.get_json()


def test_vendor_update_not_owned_returns_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"v-upd-own-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"v-upd-oth-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, owner_token, "Owned Room")

    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}",
        json={"name": "Hijacked"},
        headers=_auth(other_token),
    )
    assert resp.status_code == 403, resp.get_json()


# ── DELETE ──────────────────────────────────────────────────────────


def test_vendor_delete_owned(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-del-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, token, "Doomed")

    resp = client.delete(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True

    follow_up = client.get(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}", headers=_auth(token)
    )
    assert follow_up.status_code == 404, follow_up.get_json()


def test_vendor_delete_missing_returns_404(client, db, monkeypatch):
    _owner, token = _make_vendor(client, db, f"v-del-404-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resp = client.delete(f"{VENDOR_RESOURCES_PATH}/{uuid4()}", headers=_auth(token))
    assert resp.status_code == 404, resp.get_json()


def test_vendor_delete_not_owned_returns_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"v-del-own-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"v-del-oth-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)
    created = _create_resource(client, owner_token, "Owned Room")

    resp = client.delete(
        f"{VENDOR_RESOURCES_PATH}/{created['id']}", headers=_auth(other_token)
    )
    assert resp.status_code == 403, resp.get_json()
