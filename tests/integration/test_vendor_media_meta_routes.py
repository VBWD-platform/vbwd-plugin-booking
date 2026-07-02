"""Vendor self-service resource images / tags / custom-field routes.

Mirrors ``test_vendor_mode_routes.py``: every route is gated behind
``marketplace_enabled`` AND the ``marketplace.vendor`` permission, and every
resource-scoped route enforces ``vendor_id == g.user_id`` ownership (a foreign
vendor gets 403). The underlying primitives are the SAME the admin routes use
(the CMS image chain, the core ``tags_and_custom_fields()`` port) — vendor +
admin must never diverge. Bookable resources have no stock.
"""
import io
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


def _create_resource(client, token, name="Vendor Room"):
    resp = client.post(
        VENDOR_RESOURCES_PATH,
        json={"name": name, "price": 12.5},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["resource"]["id"]


def _create_field_def(db, key, field_type="text"):
    from vbwd.models.custom_field_def import CustomFieldDef

    definition = CustomFieldDef(
        id=uuid4(),
        entity_type="booking_resource",
        key=key,
        label=key.title(),
        type=field_type,
        is_active=True,
    )
    db.session.add(definition)
    db.session.commit()
    return definition


# ── Images ───────────────────────────────────────────────────────────


def test_images_list_own_resource(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvi-l-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["images"] == []


def test_images_list_other_vendor_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"bvi-o-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"bvi-x-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, owner_token)
    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images", headers=_auth(other_token)
    )
    assert resp.status_code == 403, resp.get_json()


def test_images_upload_owner_reaches_cms_guard(client, db, monkeypatch):
    """Owner upload reaches the CMS chain: 201 if CMS present, else the 501 guard.

    Never 403/404/500 for the owner — that would mean ownership or the CMS guard
    is broken. When CMS is present the envelope is the normalised
    ``{"image": {id, url, alt, sort_order, is_primary}}``.
    """
    _user, token = _make_vendor(client, db, f"bvi-u-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.post(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images",
        data={"file": (io.BytesIO(b"img-bytes"), "pic.jpg")},
        content_type="multipart/form-data",
        headers=_auth(token),
    )
    assert resp.status_code in (201, 501), resp.get_json()
    if resp.status_code == 201:
        image = resp.get_json()["image"]
        assert set(image.keys()) == {"id", "url", "alt", "sort_order", "is_primary"}
        assert image["is_primary"] is True


def test_images_upload_missing_file_400(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvi-nf-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.post(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images",
        data={},
        content_type="multipart/form-data",
        headers=_auth(token),
    )
    # 400 (no file) when CMS present, 501 when CMS absent — never owner failure.
    assert resp.status_code in (400, 501), resp.get_json()


def test_images_upload_other_vendor_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"bvi-uo-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"bvi-ux-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, owner_token)
    resp = client.post(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images",
        data={"file": (io.BytesIO(b"img-bytes"), "pic.jpg")},
        content_type="multipart/form-data",
        headers=_auth(other_token),
    )
    assert resp.status_code == 403, resp.get_json()


def test_images_list_blocked_when_disabled(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvi-d-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)
    resource_id = _create_resource(client, token)

    _enable_marketplace(monkeypatch, False)
    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/images", headers=_auth(token)
    )
    assert resp.status_code == 403, resp.get_json()


# ── Tags ─────────────────────────────────────────────────────────────


def test_tags_get_empty_by_default(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvt-g-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/tags", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["tags"] == []


def test_tags_put_replaces(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvt-p-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/tags",
        json={"tags": ["featured", "new"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.get_json()
    assert set(resp.get_json()["tags"]) == {"featured", "new"}

    read = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/tags", headers=_auth(token)
    )
    assert set(read.get_json()["tags"]) == {"featured", "new"}


def test_tags_put_other_vendor_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"bvt-o-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"bvt-x-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, owner_token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/tags",
        json={"tags": ["hack"]},
        headers=_auth(other_token),
    )
    assert resp.status_code == 403, resp.get_json()


def test_tags_put_requires_list(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvt-r-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/tags",
        json={"tags": "not-a-list"},
        headers=_auth(token),
    )
    assert resp.status_code == 400, resp.get_json()


# ── Custom fields ────────────────────────────────────────────────────


def test_custom_fields_get_empty_by_default(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvc-g-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.get(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/custom-fields", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["custom_fields"] == {}


def test_custom_fields_put_upserts(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvc-p-{uuid4().hex[:6]}@example.com")
    field_key = f"material_{uuid4().hex[:6]}"
    _create_field_def(db, key=field_key)
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/custom-fields",
        json={"custom_fields": {field_key: "oak"}},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["custom_fields"][field_key] == "oak"


def test_custom_fields_put_unknown_key_400(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvc-u-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/custom-fields",
        json={"custom_fields": {"nope_unknown_key": "x"}},
        headers=_auth(token),
    )
    assert resp.status_code == 400, resp.get_json()


def test_custom_fields_put_other_vendor_403(client, db, monkeypatch):
    _owner, owner_token = _make_vendor(
        client, db, f"bvc-o-{uuid4().hex[:6]}@example.com"
    )
    _other, other_token = _make_vendor(
        client, db, f"bvc-x-{uuid4().hex[:6]}@example.com"
    )
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, owner_token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/custom-fields",
        json={"custom_fields": {"any": "x"}},
        headers=_auth(other_token),
    )
    assert resp.status_code == 403, resp.get_json()


def test_custom_fields_put_requires_object(client, db, monkeypatch):
    _user, token = _make_vendor(client, db, f"bvc-r-{uuid4().hex[:6]}@example.com")
    _enable_marketplace(monkeypatch, True)

    resource_id = _create_resource(client, token)
    resp = client.put(
        f"{VENDOR_RESOURCES_PATH}/{resource_id}/custom-fields",
        json={"custom_fields": ["not", "an", "object"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400, resp.get_json()
