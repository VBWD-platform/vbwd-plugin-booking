"""S96.2 — BookingInvoiceService must not silently zero out tax.

Pre-S96, an absent ``price_factory`` made ``_charge_for`` return
``tax_fields=None`` and ``_apply_tax_fields`` recorded ``net == gross``,
``tax == 0``, empty breakdown — even for a taxed resource (a Liskov violation:
a structurally taxed line silently becomes tax-free). The fix requires the
factory in the charge path and raises when it is missing, so the no-tax outcome
can only come from a genuinely untaxed resource computed through the factory.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from vbwd.models.enums import LineItemType
from vbwd.models.tax import Tax
from vbwd.pricing.price_factory import PriceFactory
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


def _price_factory(prices_mode_in_db="NETTO"):
    settings_reader = MagicMock(return_value={"prices_mode_in_db": prices_mode_in_db})
    currency_service = MagicMock()
    currency_service.get_default_currency.return_value = MagicMock(code="EUR")
    return PriceFactory(
        settings_reader=settings_reader, currency_service=currency_service
    )


def _tax(rate):
    tax = Tax(name="VAT", code="VAT_DE", rate=Decimal(str(rate)))
    tax.id = uuid.uuid4()
    return tax


def _resource(price, taxes):
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = "Tennis Court"
    resource.slug = "tennis-court"
    resource.raw_price = float(price)
    resource.price = Decimal(str(price))
    resource.taxes = taxes
    resource.custom_schema = None
    return resource


def _added_line(session):
    added = [call.args[0] for call in session.add.call_args_list]
    return next(
        obj
        for obj in added
        if hasattr(obj, "item_type") and obj.item_type == LineItemType.CUSTOM
    )


def test_create_checkout_invoice_without_factory_raises():
    session = MagicMock()
    service = BookingInvoiceService(session)  # no factory

    with pytest.raises(ValueError):
        service.create_checkout_invoice(
            uuid.uuid4(),
            _resource(Decimal("100.00"), [_tax(19)]),
            datetime(2026, 3, 20, 10, 0),
            datetime(2026, 3, 20, 10, 30),
            quantity=1,
        )


def test_create_booking_invoice_without_factory_raises():
    session = MagicMock()
    service = BookingInvoiceService(session)  # no factory
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.quantity = 1
    booking.start_at = datetime(2026, 3, 20, 10, 0)
    booking.end_at = datetime(2026, 3, 20, 10, 30)

    with pytest.raises(ValueError):
        service.create_booking_invoice(
            uuid.uuid4(), _resource(Decimal("100.00"), [_tax(19)]), booking
        )


def test_untaxed_resource_with_factory_records_zero_tax():
    """Legitimate untaxed path: factory present, resource has no taxes."""
    session = MagicMock()
    service = BookingInvoiceService(session, price_factory=_price_factory())

    service.create_checkout_invoice(
        uuid.uuid4(),
        _resource(Decimal("50.00"), []),
        datetime(2026, 3, 20, 10, 0),
        datetime(2026, 3, 20, 10, 30),
        quantity=1,
    )

    line = _added_line(session)
    assert line.net_amount == Decimal("50.00")
    assert line.tax_amount == Decimal("0.00")
    assert line.tax_breakdown == []
    assert line.total_price == Decimal("50.00")
