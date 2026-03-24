"""Unit tests for BookingPaymentHandler — TDD-first."""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from plugins.booking.booking.handlers.payment_handler import BookingPaymentHandler

_active_patches = []


@pytest.fixture(autouse=True)
def cleanup_patches():
    yield
    for p in _active_patches:
        p.stop()
    _active_patches.clear()


def _make_line_item(plugin="booking", resource_slug="dr-smith", quantity=1):
    """Create a mock line item with booking extra_data."""
    line_item = MagicMock()
    line_item.extra_data = {
        "plugin": plugin,
        "resource_slug": resource_slug,
        "resource_name": "Dr. Smith",
        "resource_type": "specialist",
        "start_at": "2026-03-20T10:00:00",
        "end_at": "2026-03-20T10:30:00",
        "quantity": quantity,
        "custom_fields": {"symptoms": "headache"},
        "notes": "First visit",
    }
    return line_item


def _make_invoice(line_items=None, user_id=None):
    invoice = MagicMock()
    invoice.id = uuid.uuid4()
    invoice.user_id = user_id or uuid.uuid4()
    invoice.invoice_number = "BK-ABCD1234"
    invoice.line_items = line_items or []
    return invoice


def _make_resource():
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = "Dr. Smith"
    resource.slug = "dr-smith"
    resource.capacity = 5
    resource.is_active = True
    return resource


def _make_handler(invoice=None, resource=None, booked_count=0):
    mock_session = MagicMock()
    booking_repository = MagicMock()
    resource_repository = MagicMock()
    event_bus = MagicMock()

    resource_repository.find_by_slug.return_value = resource
    booking_repository.count_by_resource_and_slot.return_value = booked_count
    booking_repository.find_by_invoice_id.return_value = []

    # Mock invoice query
    invoice_query = MagicMock()
    if invoice:
        invoice_query.first.return_value = invoice
    else:
        invoice_query.first.return_value = None
    mock_session.query.return_value.filter_by.return_value = invoice_query

    handler = BookingPaymentHandler(
        session=mock_session,
        booking_repository=booking_repository,
        resource_repository=resource_repository,
        event_bus=event_bus,
    )

    # Patch db.session and repo constructors to return our mocks
    p1 = patch("vbwd.extensions.db.session", mock_session)
    p2 = patch.object(handler, "_get_booking_repo", return_value=booking_repository)
    p3 = patch.object(handler, "_get_resource_repo", return_value=resource_repository)
    p1.start()
    p2.start()
    p3.start()
    _active_patches.extend([p1, p2, p3])

    return handler, booking_repository, resource_repository, event_bus, mock_session


class TestOnInvoicePaid:
    def test_creates_booking_from_paid_invoice(self):
        resource = _make_resource()
        line_item = _make_line_item()
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, _, _ = _make_handler(
            invoice=invoice, resource=resource
        )

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        booking_repo.save.assert_called_once()
        saved_booking = booking_repo.save.call_args[0][0]
        assert saved_booking.user_id == invoice.user_id
        assert saved_booking.resource_id == resource.id
        assert saved_booking.status == "confirmed"
        assert saved_booking.quantity == 1
        assert saved_booking.invoice_id == invoice.id

    def test_booking_has_correct_times(self):
        resource = _make_resource()
        line_item = _make_line_item()
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, _, _ = _make_handler(
            invoice=invoice, resource=resource
        )

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        saved_booking = booking_repo.save.call_args[0][0]
        assert saved_booking.start_at == datetime(2026, 3, 20, 10, 0)
        assert saved_booking.end_at == datetime(2026, 3, 20, 10, 30)

    def test_booking_has_custom_fields_and_notes(self):
        resource = _make_resource()
        line_item = _make_line_item()
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, _, _ = _make_handler(
            invoice=invoice, resource=resource
        )

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        saved_booking = booking_repo.save.call_args[0][0]
        assert saved_booking.custom_fields == {"symptoms": "headache"}
        assert saved_booking.notes == "First visit"

    def test_publishes_booking_created_event(self):
        resource = _make_resource()
        line_item = _make_line_item()
        invoice = _make_invoice(line_items=[line_item])
        handler, _, _, event_bus, _ = _make_handler(invoice=invoice, resource=resource)

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        event_bus.publish.assert_called_once()
        event_name = event_bus.publish.call_args[0][0]
        assert event_name == "booking.created"

    def test_ignores_non_booking_line_items(self):
        line_item = _make_line_item(plugin="subscription")
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, event_bus, _ = _make_handler(invoice=invoice)

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        booking_repo.save.assert_not_called()
        event_bus.publish.assert_not_called()

    def test_ignores_invoice_not_found(self):
        handler, booking_repo, _, event_bus, _ = _make_handler(invoice=None)

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "UNKNOWN"})

        booking_repo.save.assert_not_called()
        event_bus.publish.assert_not_called()

    def test_skips_line_item_when_resource_not_found(self):
        line_item = _make_line_item()
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, _, _ = _make_handler(invoice=invoice, resource=None)

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        booking_repo.save.assert_not_called()

    def test_handles_multiple_booking_line_items(self):
        resource = _make_resource()
        line_item_one = _make_line_item(resource_slug="dr-smith")
        line_item_two = _make_line_item(resource_slug="dr-smith")
        invoice = _make_invoice(line_items=[line_item_one, line_item_two])
        handler, booking_repo, _, event_bus, _ = _make_handler(
            invoice=invoice, resource=resource
        )

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        assert booking_repo.save.call_count == 2
        assert event_bus.publish.call_count == 2

    def test_booking_created_with_quantity_from_extra_data(self):
        resource = _make_resource()
        line_item = _make_line_item(quantity=3)
        invoice = _make_invoice(line_items=[line_item])
        handler, booking_repo, _, _, _ = _make_handler(
            invoice=invoice, resource=resource
        )

        handler.on_invoice_paid("invoice.paid", {"invoice_id": "BK-ABCD1234"})

        saved_booking = booking_repo.save.call_args[0][0]
        assert saved_booking.quantity == 3


def _make_booking(invoice_id=None, status="confirmed"):
    booking = MagicMock()
    booking.id = uuid.uuid4()
    booking.user_id = uuid.uuid4()
    booking.resource_id = uuid.uuid4()
    booking.invoice_id = invoice_id
    booking.status = status
    return booking


class TestOnInvoiceRefunded:
    def test_cancels_bookings_linked_to_invoice(self):
        invoice_id = uuid.uuid4()
        booking = _make_booking(invoice_id=invoice_id)
        handler, booking_repo, _, _, _ = _make_handler()
        booking_repo.find_by_invoice_id.return_value = [booking]

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234", "invoice_uuid": str(invoice_id)},
        )

        assert booking.status == "cancelled"

    def test_publishes_booking_cancelled_event(self):
        invoice_id = uuid.uuid4()
        booking = _make_booking(invoice_id=invoice_id)
        handler, booking_repo, _, event_bus, _ = _make_handler()
        booking_repo.find_by_invoice_id.return_value = [booking]

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234", "invoice_uuid": str(invoice_id)},
        )

        event_bus.publish.assert_called_once()
        event_name = event_bus.publish.call_args[0][0]
        assert event_name == "booking.cancelled"
        event_data = event_bus.publish.call_args[0][1]
        assert event_data["cancelled_by"] == "refund"

    def test_ignores_missing_invoice_uuid(self):
        handler, booking_repo, _, event_bus, _ = _make_handler()

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234"},
        )

        booking_repo.find_by_invoice_id.assert_not_called()
        event_bus.publish.assert_not_called()

    def test_skips_already_cancelled_bookings(self):
        invoice_id = uuid.uuid4()
        booking = _make_booking(invoice_id=invoice_id, status="cancelled")
        handler, booking_repo, _, event_bus, _ = _make_handler()
        booking_repo.find_by_invoice_id.return_value = [booking]

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234", "invoice_uuid": str(invoice_id)},
        )

        assert booking.status == "cancelled"
        event_bus.publish.assert_not_called()

    def test_cancels_multiple_bookings_on_same_invoice(self):
        invoice_id = uuid.uuid4()
        booking_one = _make_booking(invoice_id=invoice_id)
        booking_two = _make_booking(invoice_id=invoice_id)
        handler, booking_repo, _, event_bus, _ = _make_handler()
        booking_repo.find_by_invoice_id.return_value = [booking_one, booking_two]

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234", "invoice_uuid": str(invoice_id)},
        )

        assert booking_one.status == "cancelled"
        assert booking_two.status == "cancelled"
        assert event_bus.publish.call_count == 2

    def test_no_bookings_found_is_silent(self):
        invoice_id = uuid.uuid4()
        handler, booking_repo, _, event_bus, _ = _make_handler()
        booking_repo.find_by_invoice_id.return_value = []

        handler.on_invoice_refunded(
            "invoice.refunded",
            {"invoice_id": "BK-ABCD1234", "invoice_uuid": str(invoice_id)},
        )

        event_bus.publish.assert_not_called()
