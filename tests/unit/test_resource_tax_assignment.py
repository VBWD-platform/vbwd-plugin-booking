"""S72.3 — tax assignment on booking BookableResource (unit, no DB).

RED→GREEN contract:
- ``BookableResource.to_dict()`` exposes ``tax_ids: [<id>]`` and resolved
  ``taxes: [{id, code, name, rate}]`` from the M2M ``taxes`` relationship.
- ``ResourcePricingService.get_resource_pricing_payload`` (S85.2: via the core
  ``PriceFactory``) sums the rates of the assigned taxes into net/tax/gross.
"""
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from vbwd.models.tax import Tax
from vbwd.pricing.price_factory import PriceFactory
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.services.resource_pricing_service import (
    ResourcePricingService,
)


def _service(prices_mode_in_db: str = "NETTO") -> ResourcePricingService:
    settings_reader = MagicMock(return_value={"prices_mode_in_db": prices_mode_in_db})
    currency_service = MagicMock()
    currency_service.get_default_currency.return_value = MagicMock(code="EUR")
    factory = PriceFactory(
        settings_reader=settings_reader, currency_service=currency_service
    )
    return ResourcePricingService(price_factory=factory)


def _fake_tax(code: str, name: str, rate: str) -> Tax:
    """A real core ``Tax`` instance (no DB) — exercises ``calculate``."""
    tax = Tax(name=name, code=code, rate=Decimal(rate))
    tax.id = uuid4()
    return tax


def _resource(price: str = "100.00", taxes=None) -> BookableResource:
    resource = BookableResource()
    resource.id = uuid4()
    resource.name = "Room A"
    resource.slug = "room-a"
    resource.description = None
    resource.custom_schema_id = None
    resource.capacity = 1
    resource.slot_duration_minutes = None
    resource.price = Decimal(price)
    resource.price_unit = "per_slot"
    resource.availability = {}
    resource.custom_fields_schema = None
    resource.image_url = None
    resource.config = {}
    resource.is_active = True
    resource.sort_order = 0
    resource.created_at = None
    resource.updated_at = None
    # ``categories`` and ``taxes`` are normally lazy-loaded; set them directly.
    resource.categories = []
    resource.taxes = taxes or []
    return resource


def test_to_dict_exposes_tax_ids_and_resolved_taxes():
    vat = _fake_tax("VAT_DE", "German VAT", "19.00")
    reduced = _fake_tax("VAT_DE_RED", "German VAT (reduced)", "7.00")
    resource = _resource(taxes=[vat, reduced])

    data = resource.to_dict()

    assert data["tax_ids"] == [str(vat.id), str(reduced.id)]
    assert data["taxes"] == [
        {"id": str(vat.id), "code": "VAT_DE", "name": "German VAT", "rate": "19.00"},
        {
            "id": str(reduced.id),
            "code": "VAT_DE_RED",
            "name": "German VAT (reduced)",
            "rate": "7.00",
        },
    ]


def test_to_dict_no_taxes_yields_empty_lists():
    resource = _resource(taxes=[])

    data = resource.to_dict()

    assert data["tax_ids"] == []
    assert data["taxes"] == []


def test_pricing_sums_assigned_tax_rates_into_net_tax_gross():
    """Assigned taxes (19% + 7% = 26%) take precedence; net=price, tax=26,
    gross=126 on a 100.00 resource."""
    resource = _resource(
        price="100.00",
        taxes=[
            _fake_tax("VAT_DE", "German VAT", "19.00"),
            _fake_tax("VAT_DE_RED", "German VAT (reduced)", "7.00"),
        ],
    )

    result = _service().get_resource_pricing_payload(resource)

    assert result["net_amount"] == "100.00"
    assert result["tax_amount"] == "26.00"
    assert result["gross_amount"] == "126.00"
    assert result["tax_rate"] == "26.00"
    assert [tax["code"] for tax in result["taxes"]] == ["VAT_DE", "VAT_DE_RED"]


def test_pricing_falls_back_to_bare_net_when_no_taxes_assigned():
    """With no assigned taxes pricing reflects the bare net price."""
    resource = _resource(price="100.00", taxes=[])

    result = _service().get_resource_pricing_payload(resource)

    assert result["net_amount"] == "100.00"
    assert result["tax_amount"] == "0.00"
    assert result["gross_amount"] == "100.00"
    assert result["tax_rate"] == "0.00"
    assert result["taxes"] == []
