"""Admin bulk-copy (duplicate) of BookableResource (integration).

Contract for ``POST /api/v1/admin/booking/resources/bulk/copy`` with
``{"ids": [...]}``:

- Returns 201 with the created resources + a ``count``.
- Every copy is ``is_active = False`` (copies are never live).
- ``name`` becomes ``"<original> (Copy)"``; ``slug`` is made unique against the
  repo — ``<base>-copy``, then ``<base>-copy-2``, ``-copy-3`` … — so copying the
  same resource twice (and bulk-copying the same id twice) never collides on the
  UNIQUE slug column.
- The recurring-schedule ``availability`` JSON is copied verbatim.
- Owned ``BookableResourceImage`` link rows are duplicated and re-pointed at the
  new resource, while the shared ``cms_image`` rows they reference are neither
  duplicated nor touched (UNIQUE(resource_id, cms_image_id) respected).
- Shared refs — taxes (M2M) and categories (M2M) — are re-pointed onto the copy,
  never duplicated (the ``vbwd_tax`` / ``booking_resource_category`` row counts
  are unchanged).
- Dated one-off ``BookableResourceSlotBlock`` rows are NOT copied.
- ``Booking`` rows (user transactions) are NOT copied.
- Unknown ids are skipped, not fatal.
- The ``booking.resources.manage`` permission is required.
"""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.user import User
from vbwd.models.tax import Tax


BULK_COPY_URL = "/api/v1/admin/booking/resources/bulk/copy"
HEADERS = {"Authorization": "Bearer valid"}


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


def _make_tax(db, *, rate="19.00"):
    tax = Tax(
        id=uuid4(),
        name=f"Tax {uuid4().hex[:6]}",
        code=f"TX_{uuid4().hex[:6]}",
        rate=Decimal(rate),
        is_active=True,
    )
    db.session.add(tax)
    db.session.commit()
    return tax


def _make_category(db):
    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )

    category = BookableResourceCategory(
        id=uuid4(),
        name=f"Category {uuid4().hex[:6]}",
        slug=f"cat-{uuid4().hex[:8]}",
    )
    db.session.add(category)
    db.session.commit()
    return category


def _make_resource(db, *, slug=None, availability=None):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Room A",
        slug=slug or f"room-{uuid4().hex[:8]}",
        description="A nice room",
        capacity=4,
        slot_duration_minutes=30,
        price=Decimal("100.00"),
        price_unit="per_hour",
        availability=availability if availability is not None else {"mon": ["09:00"]},
        config={"buffer_minutes": 15},
        sort_order=7,
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def _make_cms_image(db):
    from plugins.cms.src.models.cms_image import CmsImage

    slug = f"img-{uuid4().hex[:8]}"
    image = CmsImage(
        id=uuid4(),
        slug=slug,
        file_path=f"images/{slug}.jpg",
        url_path=f"/uploads/images/{slug}.jpg",
        mime_type="image/jpeg",
    )
    db.session.add(image)
    db.session.commit()
    return image


def _link_image(db, resource, cms_image, *, is_primary=False, sort_order=0):
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    link = BookableResourceImage(
        id=uuid4(),
        resource_id=resource.id,
        cms_image_id=cms_image.id,
        is_primary=is_primary,
        sort_order=sort_order,
    )
    db.session.add(link)
    db.session.commit()
    return link


def _make_slot_block(db, resource):
    from plugins.booking.booking.models.slot_block import (
        BookableResourceSlotBlock,
    )

    block = BookableResourceSlotBlock(
        id=uuid4(),
        resource_id=resource.id,
        date=date(2026, 7, 9),
        start_time="09:00",
        end_time="09:30",
        reason="maintenance",
    )
    db.session.add(block)
    db.session.commit()
    return block


def _make_booking(db, resource, user):
    from plugins.booking.booking.models.booking import Booking

    booking = Booking(
        id=uuid4(),
        resource_id=resource.id,
        user_id=user.id,
        start_at=datetime(2026, 7, 9, 9, 0),
        end_at=datetime(2026, 7, 9, 9, 30),
        status="confirmed",
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _auth_as_admin(monkeypatch, admin, *, has_permission=True):
    import vbwd.middleware.auth as auth_mod

    repo = MagicMock()
    repo.find_by_id.return_value = admin
    svc = MagicMock()
    svc.verify_token.return_value = str(admin.id)
    monkeypatch.setattr(auth_mod, "UserRepository", lambda *a, **k: repo)
    monkeypatch.setattr(auth_mod, "AuthService", lambda *a, **k: svc)
    monkeypatch.setattr(type(admin), "is_admin", property(lambda self: True))
    monkeypatch.setattr(
        type(admin), "has_permission", lambda self, perm: has_permission
    )


def _images_for(db, resource_id):
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    return (
        db.session.query(BookableResourceImage).filter_by(resource_id=resource_id).all()
    )


def _slot_blocks_for(db, resource_id):
    from plugins.booking.booking.models.slot_block import (
        BookableResourceSlotBlock,
    )

    return (
        db.session.query(BookableResourceSlotBlock)
        .filter_by(resource_id=resource_id)
        .count()
    )


def _bookings_for(db, resource_id):
    from plugins.booking.booking.models.booking import Booking

    return db.session.query(Booking).filter_by(resource_id=resource_id).count()


def test_bulk_copy_creates_inactive_named_copy(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["count"] == 1
    copy = body["resources"][0]
    assert copy["id"] != str(source.id)
    assert copy["name"] == "Room A (Copy)"
    assert copy["is_active"] is False
    assert copy["capacity"] == 4
    assert copy["price"] == 100.0
    assert copy["price_unit"] == "per_hour"
    assert copy["sort_order"] == 7


def test_bulk_copy_slug_is_unique_and_collision_safe(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db, slug="studio")
    _auth_as_admin(monkeypatch, admin)

    first = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)
    second = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert first.status_code == 201, first.get_json()
    assert second.status_code == 201, second.get_json()
    assert first.get_json()["resources"][0]["slug"] == "studio-copy"
    assert second.get_json()["resources"][0]["slug"] == "studio-copy-2"


def test_bulk_copy_same_id_twice_in_one_call_makes_distinct_slugs(
    db, client, monkeypatch
):
    admin = _make_admin(db)
    source = _make_resource(db, slug="atelier")
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        BULK_COPY_URL,
        json={"ids": [str(source.id), str(source.id)]},
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    slugs = [r["slug"] for r in resp.get_json()["resources"]]
    assert resp.get_json()["count"] == 2
    assert sorted(slugs) == ["atelier-copy", "atelier-copy-2"]


def test_bulk_copy_two_resources_at_once(db, client, monkeypatch):
    admin = _make_admin(db)
    first = _make_resource(db, slug="alpha")
    second = _make_resource(db, slug="beta")
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        BULK_COPY_URL,
        json={"ids": [str(first.id), str(second.id)]},
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["count"] == 2
    slugs = {r["slug"] for r in resp.get_json()["resources"]}
    assert slugs == {"alpha-copy", "beta-copy"}


def test_bulk_copy_copies_availability_verbatim(db, client, monkeypatch):
    admin = _make_admin(db)
    availability = {"mon": ["09:00", "10:00"], "tue": ["14:00"], "buffer": 5}
    source = _make_resource(db, availability=availability)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["resources"][0]["availability"] == availability


def test_bulk_copy_duplicates_image_links_sharing_cms_image(db, client, monkeypatch):
    from plugins.cms.src.models.cms_image import CmsImage

    admin = _make_admin(db)
    source = _make_resource(db)
    image_one = _make_cms_image(db)
    image_two = _make_cms_image(db)
    _link_image(db, source, image_one, is_primary=True, sort_order=0)
    _link_image(db, source, image_two, sort_order=1)
    _auth_as_admin(monkeypatch, admin)

    cms_count_before = db.session.query(CmsImage).count()

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    copy_id = resp.get_json()["resources"][0]["id"]

    copy_links = _images_for(db, copy_id)
    assert len(copy_links) == 2
    # The link rows are re-pointed to the copy but reference the SAME cms images.
    assert {str(link.cms_image_id) for link in copy_links} == {
        str(image_one.id),
        str(image_two.id),
    }
    assert {str(link.resource_id) for link in copy_links} == {copy_id}
    # Source links untouched; no new cms_image rows created.
    assert len(_images_for(db, source.id)) == 2
    assert db.session.query(CmsImage).count() == cms_count_before


def test_bulk_copy_repoints_taxes_and_categories_not_duplicated(
    db, client, monkeypatch
):
    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )

    admin = _make_admin(db)
    source = _make_resource(db)
    tax = _make_tax(db)
    category = _make_category(db)
    source.taxes = [tax]
    source.categories = [category]
    db.session.commit()
    _auth_as_admin(monkeypatch, admin)

    tax_count_before = db.session.query(Tax).count()
    category_count_before = db.session.query(BookableResourceCategory).count()

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    copy = resp.get_json()["resources"][0]
    assert copy["tax_ids"] == [str(tax.id)]
    assert [c["id"] for c in copy["categories"]] == [str(category.id)]
    # The shared tax / category rows are re-pointed, never duplicated.
    assert db.session.query(Tax).count() == tax_count_before
    assert db.session.query(BookableResourceCategory).count() == category_count_before


def test_bulk_copy_does_not_copy_slot_blocks(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db)
    _make_slot_block(db, source)
    _make_slot_block(db, source)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    copy_id = resp.get_json()["resources"][0]["id"]
    assert _slot_blocks_for(db, source.id) == 2
    assert _slot_blocks_for(db, copy_id) == 0


def test_bulk_copy_does_not_copy_bookings(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db)
    _make_booking(db, source, admin)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 201, resp.get_json()
    copy_id = resp.get_json()["resources"][0]["id"]
    assert _bookings_for(db, source.id) == 1
    assert _bookings_for(db, copy_id) == 0


def test_bulk_copy_skips_unknown_id(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db)
    _auth_as_admin(monkeypatch, admin)

    resp = client.post(
        BULK_COPY_URL,
        json={"ids": [str(source.id), str(uuid4())]},
        headers=HEADERS,
    )

    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["count"] == 1


def test_bulk_copy_requires_manage_permission(db, client, monkeypatch):
    admin = _make_admin(db)
    source = _make_resource(db)
    _auth_as_admin(monkeypatch, admin, has_permission=False)

    resp = client.post(BULK_COPY_URL, json={"ids": [str(source.id)]}, headers=HEADERS)

    assert resp.status_code == 403, resp.get_json()
