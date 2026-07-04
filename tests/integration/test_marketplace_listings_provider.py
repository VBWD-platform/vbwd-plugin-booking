"""Booking marketplace vendor-listings provider (integration).

The booking vertical contributes a ``vendor_listings_provider`` the marketplace
registry calls to aggregate a user's resource listings. This test exercises the
provider DIRECTLY against a real session — it never imports the marketplace
plugin, so it passes in the per-plugin isolated CI (which clones booking alone).

Seeds through ``ResourceRepository`` (no raw SQL) and asserts:
  - an empty list for a vendor who owns nothing (Liskov: safe empty result),
  - the vendor's own ``BookableResource.to_dict()`` for a vendor who owns one,
  - another vendor's resource is excluded (ownership scoping).
"""
from decimal import Decimal
from uuid import uuid4

from vbwd.models.user import User

from plugins.booking.booking.marketplace_listings import vendor_listings_provider
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.repositories.resource_repository import ResourceRepository


def _make_vendor(db):
    """Seed a real core user (vendor_id has a FK to users) and return its id."""
    user = User(email=f"booking-vendor-{uuid4().hex}@example.com", password_hash="x")
    db.session.add(user)
    db.session.commit()
    return user.id


def _make_resource(db, vendor_id, name):
    repository = ResourceRepository(db.session)
    resource = BookableResource(
        id=uuid4(),
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
        price=Decimal("50.00"),
        is_active=True,
        vendor_id=vendor_id,
    )
    return repository.save(resource)


def test_provider_returns_empty_for_vendor_without_resources(db):
    unknown_vendor_id = uuid4()

    assert vendor_listings_provider(unknown_vendor_id) == []


def test_provider_returns_only_the_vendors_own_resource_dicts(db):
    vendor_id = _make_vendor(db)
    other_vendor_id = _make_vendor(db)

    owned = _make_resource(db, vendor_id, "Owned Room")
    _make_resource(db, other_vendor_id, "Other Room")

    listings = vendor_listings_provider(vendor_id)

    assert len(listings) == 1
    assert listings[0] == owned.to_dict()
    assert listings[0]["id"] == str(owned.id)
