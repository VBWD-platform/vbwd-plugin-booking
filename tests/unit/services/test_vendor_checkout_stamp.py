"""Both invoice-building flows stamp the vendor id on the buyer line (money path).

When vendor-mode is on and the resource is vendor-owned, the created invoice
line's ``extra_data`` carries ``vendor_id`` = the vendor's user id (the
documented convention ``marketplace`` credits from). When the flag is off, or
the resource is platform-owned, no stamp is written (classic behaviour
unchanged). Covers BOTH ``create_booking_invoice`` and ``create_checkout_invoice``.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from vbwd.pricing.price_factory import PriceFactory

from plugins.booking.booking.services import booking_invoice_service
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


def _price_factory():
    """An untaxed (NETTO-mode) PriceFactory — S96.2 requires a wired factory."""
    settings_reader = MagicMock(return_value={"prices_mode_in_db": "NETTO"})
    currency_service = MagicMock()
    currency_service.get_default_currency.return_value = MagicMock(code="EUR")
    return PriceFactory(
        settings_reader=settings_reader, currency_service=currency_service
    )


def _service():
    return BookingInvoiceService(MagicMock(), price_factory=_price_factory())


def _make_resource(vendor_id=None):
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = "Vendor Room"
    resource.slug = "vendor-room"
    resource.price = Decimal("50.00")
    resource.raw_price = 50.0
    resource.taxes = []
    resource.custom_schema = None
    resource.vendor_id = vendor_id
    return resource


def _make_booking():
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.start_at = datetime(2026, 3, 20, 10, 0)
    booking.end_at = datetime(2026, 3, 20, 10, 30)
    booking.quantity = 1
    booking.custom_fields = {}
    return booking


def _line(session_add_calls):
    from vbwd.models.invoice_line_item import InvoiceLineItem

    for call in session_add_calls:
        obj = call.args[0]
        if isinstance(obj, InvoiceLineItem):
            return obj
    raise AssertionError("no line item was added")


def _enable(monkeypatch, enabled):
    monkeypatch.setattr(booking_invoice_service, "marketplace_enabled", lambda: enabled)


def test_checkout_invoice_stamps_vendor_id_when_enabled(monkeypatch):
    _enable(monkeypatch, True)
    vendor_id = uuid.uuid4()
    service = _service()
    service.create_checkout_invoice(
        user_id=uuid.uuid4(),
        resource=_make_resource(vendor_id=vendor_id),
        start_at=datetime(2026, 3, 20, 10, 0),
        end_at=datetime(2026, 3, 20, 10, 30),
    )
    line = _line(service.session.add.call_args_list)
    assert line.extra_data["vendor_id"] == str(vendor_id)


def test_booking_invoice_stamps_vendor_id_when_enabled(monkeypatch):
    _enable(monkeypatch, True)
    vendor_id = uuid.uuid4()
    service = _service()
    service.create_booking_invoice(
        user_id=uuid.uuid4(),
        resource=_make_resource(vendor_id=vendor_id),
        booking=_make_booking(),
    )
    line = _line(service.session.add.call_args_list)
    assert line.extra_data["vendor_id"] == str(vendor_id)


def test_checkout_invoice_no_stamp_when_disabled(monkeypatch):
    _enable(monkeypatch, False)
    service = _service()
    service.create_checkout_invoice(
        user_id=uuid.uuid4(),
        resource=_make_resource(vendor_id=uuid.uuid4()),
        start_at=datetime(2026, 3, 20, 10, 0),
        end_at=datetime(2026, 3, 20, 10, 30),
    )
    line = _line(service.session.add.call_args_list)
    assert "vendor_id" not in line.extra_data


def test_booking_invoice_no_stamp_for_platform_resource(monkeypatch):
    _enable(monkeypatch, True)
    service = _service()
    service.create_booking_invoice(
        user_id=uuid.uuid4(),
        resource=_make_resource(vendor_id=None),
        booking=_make_booking(),
    )
    line = _line(service.session.add.call_args_list)
    assert "vendor_id" not in line.extra_data
