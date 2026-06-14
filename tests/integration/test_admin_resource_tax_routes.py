"""S72.3 — admin create/update resource accept ``tax_ids`` (integration).

Contract:
- POST/PUT accept ``tax_ids: [uuid]``; each must exist AND be active.
- Update is a replace-set; an empty list clears the assignment; duplicate ids
  are deduped (order-preserving).
- A nonexistent or inactive tax id is rejected with 400.
- The persisted resource's ``to_dict()`` reflects the assigned taxes.
- The public resource detail response reflects the summed applied taxes.
"""
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.user import User
from vbwd.models.tax import Tax


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


def _make_tax(db, *, is_active=True, rate="19.00"):
    tax = Tax(
        id=uuid4(),
        name=f"Tax {uuid4().hex[:6]}",
        code=f"TX_{uuid4().hex[:6]}",
        rate=Decimal(rate),
        is_active=is_active,
    )
    db.session.add(tax)
    db.session.commit()
    return tax


def _make_resource(db):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Room A",
        slug=f"room-{uuid4().hex[:8]}",
        price=Decimal("100.00"),
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


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


HEADERS = {"Authorization": "Bearer valid"}


def test_create_resource_with_tax_ids_persists_m2m_deduped(db, client, monkeypatch):
    admin = _make_admin(db)
    tax_one = _make_tax(db)
    tax_two = _make_tax(db)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={
            "name": "Taxed Room",
            "slug": f"taxed-{uuid4().hex[:8]}",
            "price": "100.00",
            "tax_ids": [str(tax_one.id), str(tax_two.id), str(tax_one.id)],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    resource = resp.get_json()
    # Deduped, order-preserving.
    assert resource["tax_ids"] == [str(tax_one.id), str(tax_two.id)]


def test_create_resource_rejects_inactive_tax(db, client, monkeypatch):
    admin = _make_admin(db)
    inactive = _make_tax(db, is_active=False)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={
            "name": "Bad Room",
            "slug": f"bad-{uuid4().hex[:8]}",
            "price": "10.00",
            "tax_ids": [str(inactive.id)],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 400, resp.get_json()


def test_create_resource_rejects_unknown_tax(db, client, monkeypatch):
    admin = _make_admin(db)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={
            "name": "Ghost Room",
            "slug": f"ghost-{uuid4().hex[:8]}",
            "price": "10.00",
            "tax_ids": [str(uuid4())],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 400, resp.get_json()


def test_update_resource_replace_set_of_tax_ids(db, client, monkeypatch):
    admin = _make_admin(db)
    resource = _make_resource(db)
    first = _make_tax(db)
    second = _make_tax(db)
    resource.taxes = [first]
    db.session.commit()
    _auth_as_admin(monkeypatch, admin)

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"tax_ids": [str(second.id)]},
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["tax_ids"] == [str(second.id)]


def test_update_resource_empty_tax_ids_clears_assignment(db, client, monkeypatch):
    admin = _make_admin(db)
    resource = _make_resource(db)
    tax = _make_tax(db)
    resource.taxes = [tax]
    db.session.commit()
    _auth_as_admin(monkeypatch, admin)

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"tax_ids": []},
        headers=HEADERS,
    )

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["tax_ids"] == []


def test_update_resource_rejects_unknown_tax(db, client, monkeypatch):
    admin = _make_admin(db)
    resource = _make_resource(db)
    _auth_as_admin(monkeypatch, admin)

    resp = client.put(
        f"/api/v1/admin/booking/resources/{resource.id}",
        json={"tax_ids": [str(uuid4())]},
        headers=HEADERS,
    )

    assert resp.status_code == 400, resp.get_json()


def test_public_resource_detail_pricing_sums_assigned_taxes(db, client):
    """The public resource detail response reflects the summed applied taxes."""
    resource = _make_resource(db)
    vat = _make_tax(db, rate="19.00")
    reduced = _make_tax(db, rate="7.00")
    resource.taxes = [vat, reduced]
    db.session.commit()

    resp = client.get(f"/api/v1/booking/resources/{resource.slug}")

    assert resp.status_code == 200, resp.get_json()
    pricing = resp.get_json()["pricing"]
    assert pricing["net_amount"] == "100.00"
    assert pricing["tax_amount"] == "26.00"
    assert pricing["gross_amount"] == "126.00"
    assert pricing["tax_rate"] == "26.00"
    assert {tax["code"] for tax in pricing["taxes"]} == {vat.code, reduced.code}
