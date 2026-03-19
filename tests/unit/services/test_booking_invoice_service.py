"""Unit tests for BookingInvoiceService."""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from vbwd.models.enums import InvoiceStatus, LineItemType

from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


def _make_resource(name="Dr. Smith", slug="dr-smith", price=Decimal("50.00")):
    resource = MagicMock()
    resource.name = name
    resource.slug = slug
    resource.price = price
    resource.currency = "EUR"
    resource.resource_type = "specialist"
    return resource


def _make_booking(start_at=None, end_at=None, quantity=1, custom_fields=None):
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.start_at = start_at or datetime(2026, 3, 20, 10, 0)
    booking.end_at = end_at or datetime(2026, 3, 20, 10, 30)
    booking.quantity = quantity
    booking.custom_fields = custom_fields or {}
    return booking


class TestBookingInvoiceService:
    def test_creates_invoice_with_correct_amount(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(price=Decimal("50.00"))
        booking = _make_booking(quantity=1)
        user_id = uuid.uuid4()

        invoice = service.create_booking_invoice(user_id, resource, booking)

        assert invoice.amount == Decimal("50.00")
        assert invoice.currency == "EUR"
        assert invoice.status == InvoiceStatus.PENDING

    def test_creates_invoice_with_quantity(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(price=Decimal("89.00"))
        booking = _make_booking(quantity=3)
        user_id = uuid.uuid4()

        invoice = service.create_booking_invoice(user_id, resource, booking)

        assert invoice.amount == Decimal("267.00")  # 89 * 3

    def test_creates_custom_line_item(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource()
        booking = _make_booking()
        user_id = uuid.uuid4()

        service.create_booking_invoice(user_id, resource, booking)

        # Check that session.add was called with InvoiceLineItem
        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_items = [
            obj
            for obj in added_objects
            if hasattr(obj, "item_type") and obj.item_type == LineItemType.CUSTOM
        ]
        assert len(line_items) == 1

    def test_line_item_metadata_contains_booking_details(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(name="Dr. Johnson", slug="dr-johnson")
        booking = _make_booking(custom_fields={"symptoms": "headache"})
        user_id = uuid.uuid4()

        service.create_booking_invoice(user_id, resource, booking)

        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_item = next(
            obj
            for obj in added_objects
            if hasattr(obj, "extra_data") and obj.extra_data
        )

        assert line_item.extra_data["plugin"] == "booking"
        assert line_item.extra_data["resource_name"] == "Dr. Johnson"
        assert line_item.extra_data["resource_slug"] == "dr-johnson"
        assert line_item.extra_data["custom_fields"]["symptoms"] == "headache"

    def test_invoice_number_has_prefix(self):
        session = MagicMock()
        service = BookingInvoiceService(session, invoice_prefix="BK")
        resource = _make_resource()
        booking = _make_booking()
        user_id = uuid.uuid4()

        invoice = service.create_booking_invoice(user_id, resource, booking)

        assert invoice.invoice_number.startswith("BK-")

    def test_line_item_description_includes_resource_and_date(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(name="Meeting Room A")
        booking = _make_booking(start_at=datetime(2026, 4, 15, 14, 0))
        user_id = uuid.uuid4()

        service.create_booking_invoice(user_id, resource, booking)

        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_item = next(
            obj
            for obj in added_objects
            if hasattr(obj, "item_type") and obj.item_type == LineItemType.CUSTOM
        )

        assert "Meeting Room A" in line_item.description
        assert "2026-04-15" in line_item.description
