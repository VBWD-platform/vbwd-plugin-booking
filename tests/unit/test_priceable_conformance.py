"""S85.1 — BookableResource conforms to the core ``Priceable`` protocol.

After the storage migration the resource exposes ``raw_price`` (a float reading
the stored ``price``) and keeps its ``taxes`` relationship; the dropped
``currency`` column no longer exists; and ``to_dict()`` no longer carries it.
"""
from uuid import uuid4

from vbwd.pricing.priceable import Priceable
from plugins.booking.booking.models.resource import BookableResource


def _resource() -> BookableResource:
    resource = BookableResource()
    resource.id = uuid4()
    resource.name = "Room A"
    resource.slug = "room-a"
    resource.price = 49.5
    resource.availability = {}
    resource.taxes = []
    return resource


def test_resource_raw_price_returns_stored_price_float():
    resource = _resource()
    assert resource.raw_price == 49.5
    assert isinstance(resource.raw_price, float)


def test_resource_has_no_currency_column():
    assert not hasattr(BookableResource, "currency")


def test_resource_has_taxes_relationship():
    assert hasattr(BookableResource, "taxes")
    assert list(_resource().taxes) == []


def test_to_dict_drops_currency_key():
    assert "currency" not in _resource().to_dict()


def test_resource_satisfies_priceable_protocol():
    assert isinstance(_resource(), Priceable)
