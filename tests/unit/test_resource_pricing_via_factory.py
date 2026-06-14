"""S85.2 — ``ResourcePricingService`` computes via the core ``PriceFactory``.

Mode-sensitivity headline: with the SAME stored ``price`` double + a linked tax,
flipping the global ``prices_mode_in_db`` between ``NETTO`` and ``BRUTTO`` yields
different net/gross. No bespoke tax math remains; the payload embeds the
serialized ``Price`` object.
"""
from unittest.mock import MagicMock

from vbwd.pricing.price_factory import PriceFactory
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.services.resource_pricing_service import (
    ResourcePricingService,
)


class _FakeTax:
    def __init__(self, code, rate, name="VAT"):
        self.id = code
        self.code = code
        self.rate = rate
        self.name = name


def _service(prices_mode_in_db):
    settings_reader = MagicMock(return_value={"prices_mode_in_db": prices_mode_in_db})
    currency_service = MagicMock()
    currency_service.get_default_currency.return_value = MagicMock(code="EUR")
    factory = PriceFactory(
        settings_reader=settings_reader, currency_service=currency_service
    )
    return ResourcePricingService(price_factory=factory)


def _resource(price, taxes):
    resource = BookableResource(name="Room", slug="room", price=price)
    resource.taxes = taxes
    return resource


def test_netto_mode_adds_tax_on_top():
    payload = _service("NETTO").get_resource_pricing_payload(
        _resource(100.0, [_FakeTax("VAT_DE", 19.0)])
    )
    assert payload["net_amount"] == "100.00"
    assert payload["gross_amount"] == "119.00"


def test_brutto_mode_extracts_net_from_gross():
    payload = _service("BRUTTO").get_resource_pricing_payload(
        _resource(119.0, [_FakeTax("VAT_DE", 19.0)])
    )
    assert payload["gross_amount"] == "119.00"
    assert payload["net_amount"] == "100.00"


def test_mode_flip_changes_net_and_gross_for_same_stored_double():
    resource = _resource(100.0, [_FakeTax("VAT_DE", 19.0)])
    netto = _service("NETTO").get_resource_pricing_payload(resource)
    brutto = _service("BRUTTO").get_resource_pricing_payload(resource)
    assert netto["gross_amount"] != brutto["gross_amount"]
    assert netto["net_amount"] != brutto["net_amount"]


def test_payload_embeds_serialized_price_object():
    payload = _service("NETTO").get_resource_pricing_payload(
        _resource(100.0, [_FakeTax("VAT_DE", 19.0)])
    )
    assert payload["price"]["netto"] == 100.0
    assert payload["price"]["brutto"] == 119.0
    assert payload["price"]["currency"] == "EUR"


def test_taxless_resource_net_equals_gross():
    payload = _service("NETTO").get_resource_pricing_payload(_resource(50.0, []))
    assert payload["net_amount"] == payload["gross_amount"] == "50.00"
    assert payload["taxes"] == []
