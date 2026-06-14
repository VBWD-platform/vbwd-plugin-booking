"""S85.4 — booking invoice records the per-rate tax breakdown columns.

When wired with the core ``PriceFactory``, ``BookingInvoiceService`` records the
line item's first-class ``net_amount`` / ``tax_amount`` / ``tax_breakdown`` and
rolls the invoice ``subtotal`` / ``tax_amount`` / ``total_amount`` up from the
line. The charge stays ``Price.brutto`` (D8). Flipping the global
``prices_mode_in_db`` changes the recorded net/tax for the same stored price.
A resource with no factory (legacy) records net == gross, empty breakdown.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from vbwd.models.enums import LineItemType
from vbwd.models.tax import Tax
from vbwd.pricing.price_factory import PriceFactory
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


def _price_factory(prices_mode_in_db):
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
    resource.name = "Dr. Smith"
    resource.slug = "dr-smith"
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


def _added_invoice(session):
    added = [call.args[0] for call in session.add.call_args_list]
    return next(obj for obj in added if hasattr(obj, "invoice_number"))


def test_netto_mode_records_line_columns_and_invoice_rollup():
    session = MagicMock()
    service = BookingInvoiceService(session, price_factory=_price_factory("NETTO"))
    resource = _resource(Decimal("100.00"), [_tax(19)])

    service.create_checkout_invoice(
        uuid.uuid4(),
        resource,
        datetime(2026, 3, 20, 10, 0),
        datetime(2026, 3, 20, 10, 30),
        quantity=1,
    )

    line = _added_line(session)
    assert line.net_amount == Decimal("100.00")
    assert line.tax_amount == Decimal("19.00")
    assert line.total_price == Decimal("119.00")  # gross unchanged
    assert line.tax_breakdown == [
        {"code": "VAT_DE", "name": "VAT", "rate": 19.0, "amount": 19.0}
    ]

    invoice = _added_invoice(session)
    assert invoice.subtotal == Decimal("100.00")
    assert invoice.tax_amount == Decimal("19.00")
    assert invoice.total_amount == Decimal("119.00")


def test_brutto_mode_changes_recorded_net_and_tax():
    session = MagicMock()
    service = BookingInvoiceService(session, price_factory=_price_factory("BRUTTO"))
    resource = _resource(Decimal("119.00"), [_tax(19)])

    service.create_checkout_invoice(
        uuid.uuid4(),
        resource,
        datetime(2026, 3, 20, 10, 0),
        datetime(2026, 3, 20, 10, 30),
        quantity=1,
    )

    line = _added_line(session)
    assert line.net_amount == Decimal("100.00")
    assert line.tax_amount == Decimal("19.00")
    assert line.total_price == Decimal("119.00")  # gross == charge


def test_legacy_no_factory_records_net_equals_gross_empty_breakdown():
    session = MagicMock()
    service = BookingInvoiceService(session)  # no factory
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = "Dr. Smith"
    resource.slug = "dr-smith"
    resource.price = Decimal("50.00")
    resource.custom_schema = None

    service.create_checkout_invoice(
        uuid.uuid4(),
        resource,
        datetime(2026, 3, 20, 10, 0),
        datetime(2026, 3, 20, 10, 30),
        quantity=1,
    )

    line = _added_line(session)
    assert line.net_amount == Decimal("50.00")
    assert line.tax_amount == Decimal("0.00")
    assert line.tax_breakdown == []
