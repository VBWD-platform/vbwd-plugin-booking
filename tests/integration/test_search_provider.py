"""BookingResourceSearchProvider — search hits + get_detail over real rows.

A query finds ACTIVE bookable resources by name/description/slug; the hit
carries the public ``/booking/<slug>`` url + a price string; ``get_detail``
re-resolves by slug.
"""
from decimal import Decimal
from uuid import uuid4

import pytest

from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.search_provider import BookingResourceSearchProvider


def _resource(
    db, *, name, slug, description="", price=Decimal("100.00"), is_active=True
):
    resource = BookableResource(
        id=uuid4(),
        name=name,
        slug=slug,
        description=description,
        price=price,
        is_active=is_active,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


@pytest.fixture
def provider():
    return BookingResourceSearchProvider()


def test_search_finds_active_resource_by_name(db, provider):
    _resource(
        db,
        name="Tennis Court A",
        slug="tennis-court-a",
        description="An outdoor clay court.",
        price=Decimal("25.00"),
    )

    hits = provider.search("tennis", limit=5)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.entity_type == "booking_resource"
    assert hit.entity_label == "Booking"
    assert hit.key == "tennis-court-a"
    assert hit.title == "Tennis Court A"
    assert hit.url == "/booking/tennis-court-a"
    assert hit.price is not None and "25.00" in hit.price


def test_search_excludes_inactive(db, provider):
    _resource(
        db,
        name="Closed Sauna",
        slug="closed-sauna",
        is_active=False,
    )

    assert provider.search("sauna", limit=5) == []


def test_get_detail_resolves_by_slug(db, provider):
    _resource(
        db,
        name="Meeting Room 1",
        slug="meeting-room-1",
        description="Seats eight.",
    )

    hit = provider.get_detail("meeting-room-1")

    assert hit is not None
    assert hit.title == "Meeting Room 1"
    assert hit.url == "/booking/meeting-room-1"


def test_get_detail_unknown_slug_returns_none(db, provider):
    assert provider.get_detail("nope") is None
