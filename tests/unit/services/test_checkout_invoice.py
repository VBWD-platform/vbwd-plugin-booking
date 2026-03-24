"""Unit tests for BookingInvoiceService.create_checkout_invoice (TDD-first)."""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from vbwd.models.enums import InvoiceStatus, LineItemType

from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


def _make_resource(
    name="Dr. Smith",
    slug="dr-smith",
    price=Decimal("50.00"),
    currency="EUR",
    custom_schema=None,
):
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = name
    resource.slug = slug
    resource.price = price
    resource.currency = currency
    resource.custom_schema = custom_schema
    return resource


class TestCreateCheckoutInvoice:
    def test_creates_invoice_with_correct_amount(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(price=Decimal("50.00"))
        user_id = uuid.uuid4()

        invoice = service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
            quantity=1,
        )

        assert invoice.amount == Decimal("50.00")
        assert invoice.currency == "EUR"
        assert invoice.status == InvoiceStatus.PENDING

    def test_creates_invoice_with_quantity_multiplied(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(price=Decimal("89.00"))
        user_id = uuid.uuid4()

        invoice = service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 11, 0),
            quantity=3,
        )

        assert invoice.amount == Decimal("267.00")

    def test_invoice_number_has_prefix(self):
        session = MagicMock()
        service = BookingInvoiceService(session, invoice_prefix="BK")
        resource = _make_resource()
        user_id = uuid.uuid4()

        invoice = service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        assert invoice.invoice_number.startswith("BK-")

    def test_line_item_extra_data_contains_booking_metadata(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(name="Dr. Johnson", slug="dr-johnson")
        user_id = uuid.uuid4()
        custom_fields = {"symptoms": "headache"}

        service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
            custom_fields=custom_fields,
            notes="First visit",
        )

        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_item = next(
            obj
            for obj in added_objects
            if hasattr(obj, "extra_data") and obj.extra_data
        )

        assert line_item.extra_data["plugin"] == "booking"
        assert line_item.extra_data["resource_slug"] == "dr-johnson"
        assert line_item.extra_data["resource_name"] == "Dr. Johnson"
        assert line_item.extra_data["start_at"] == "2026-03-20T10:00:00"
        assert line_item.extra_data["end_at"] == "2026-03-20T10:30:00"
        assert line_item.extra_data["custom_fields"]["symptoms"] == "headache"
        assert line_item.extra_data["notes"] == "First visit"
        assert line_item.extra_data["quantity"] == 1

    def test_line_item_has_no_booking_id(self):
        """Checkout invoice has no booking_id — booking doesn't exist yet."""
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource()
        user_id = uuid.uuid4()

        service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_item = next(
            obj
            for obj in added_objects
            if hasattr(obj, "extra_data") and obj.extra_data
        )

        assert "booking_id" not in line_item.extra_data

    def test_line_item_description_includes_resource_and_date(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(name="Meeting Room A")
        user_id = uuid.uuid4()

        service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 4, 15, 14, 0),
            end_at=datetime(2026, 4, 15, 15, 0),
        )

        added_objects = [call.args[0] for call in session.add.call_args_list]
        line_item = next(
            obj
            for obj in added_objects
            if hasattr(obj, "item_type") and obj.item_type == LineItemType.CUSTOM
        )

        assert "Meeting Room A" in line_item.description
        assert "2026-04-15" in line_item.description

    def test_default_quantity_is_one(self):
        session = MagicMock()
        service = BookingInvoiceService(session)
        resource = _make_resource(price=Decimal("100.00"))
        user_id = uuid.uuid4()

        invoice = service.create_checkout_invoice(
            user_id=user_id,
            resource=resource,
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        assert invoice.amount == Decimal("100.00")
