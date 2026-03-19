"""Unit tests for BookingService."""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from plugins.booking.booking.services.booking_service import (
    BookingService,
    BookingError,
)


def _make_resource(
    name="Dr. Smith",
    slug="dr-smith",
    capacity=1,
    is_active=True,
    price=Decimal("50.00"),
):
    resource = MagicMock()
    resource.id = uuid.uuid4()
    resource.name = name
    resource.slug = slug
    resource.capacity = capacity
    resource.is_active = is_active
    resource.price = price
    resource.currency = "EUR"
    resource.resource_type = "specialist"
    return resource


def _make_service(
    resource=None,
    booked_count=0,
    existing_booking=None,
):
    booking_repo = MagicMock()
    resource_repo = MagicMock()
    availability_service = MagicMock()
    invoice_service = MagicMock()
    event_bus = MagicMock()

    if resource:
        resource_repo.find_by_slug.return_value = resource
        resource_repo.find_by_id.return_value = resource
    else:
        resource_repo.find_by_slug.return_value = None

    booking_repo.count_by_resource_and_slot.return_value = booked_count
    booking_repo.find_by_id.return_value = existing_booking

    invoice_mock = MagicMock()
    invoice_mock.id = uuid.uuid4()
    invoice_service.create_booking_invoice.return_value = invoice_mock

    service = BookingService(
        booking_repository=booking_repo,
        resource_repository=resource_repo,
        availability_service=availability_service,
        invoice_service=invoice_service,
        event_bus=event_bus,
    )
    return service, booking_repo, resource_repo, invoice_service, event_bus


class TestCreateBooking:
    def test_create_booking_success(self):
        resource = _make_resource()
        service, booking_repo, _, invoice_svc, event_bus = _make_service(
            resource=resource, booked_count=0
        )

        booking = service.create_booking(
            user_id=uuid.uuid4(),
            resource_slug="dr-smith",
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        assert booking.status == "pending"
        assert booking.resource_id == resource.id
        booking_repo.save.assert_called_once()
        invoice_svc.create_booking_invoice.assert_called_once()

    def test_create_booking_resource_not_found_raises(self):
        service, *_ = _make_service(resource=None)

        with pytest.raises(BookingError, match="not found"):
            service.create_booking(
                user_id=uuid.uuid4(),
                resource_slug="nonexistent",
                start_at=datetime(2026, 3, 20, 10, 0),
                end_at=datetime(2026, 3, 20, 10, 30),
            )

    def test_create_booking_inactive_resource_raises(self):
        resource = _make_resource(is_active=False)
        service, *_ = _make_service(resource=resource)

        with pytest.raises(BookingError, match="not active"):
            service.create_booking(
                user_id=uuid.uuid4(),
                resource_slug="dr-smith",
                start_at=datetime(2026, 3, 20, 10, 0),
                end_at=datetime(2026, 3, 20, 10, 30),
            )

    def test_create_booking_no_capacity_raises(self):
        resource = _make_resource(capacity=1)
        service, *_ = _make_service(resource=resource, booked_count=1)

        with pytest.raises(BookingError, match="Not enough capacity"):
            service.create_booking(
                user_id=uuid.uuid4(),
                resource_slug="dr-smith",
                start_at=datetime(2026, 3, 20, 10, 0),
                end_at=datetime(2026, 3, 20, 10, 30),
            )

    def test_create_booking_with_custom_fields(self):
        resource = _make_resource()
        service, *_ = _make_service(resource=resource)

        booking = service.create_booking(
            user_id=uuid.uuid4(),
            resource_slug="dr-smith",
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
            custom_fields={"symptoms": "headache"},
        )

        assert booking.custom_fields["symptoms"] == "headache"

    def test_create_booking_creates_invoice(self):
        resource = _make_resource()
        service, _, _, invoice_svc, _ = _make_service(resource=resource)

        booking = service.create_booking(
            user_id=uuid.uuid4(),
            resource_slug="dr-smith",
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        invoice_svc.create_booking_invoice.assert_called_once()
        assert booking.invoice_id is not None

    def test_create_booking_publishes_event(self):
        resource = _make_resource()
        service, _, _, _, event_bus = _make_service(resource=resource)

        service.create_booking(
            user_id=uuid.uuid4(),
            resource_slug="dr-smith",
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 10, 30),
        )

        event_bus.publish.assert_called_once()
        event_name = event_bus.publish.call_args[0][0]
        assert event_name == "booking.created"

    def test_create_booking_with_quantity(self):
        resource = _make_resource(capacity=20)
        service, *_ = _make_service(resource=resource, booked_count=15)

        booking = service.create_booking(
            user_id=uuid.uuid4(),
            resource_slug="dr-smith",
            start_at=datetime(2026, 3, 20, 10, 0),
            end_at=datetime(2026, 3, 20, 11, 0),
            quantity=3,
        )

        assert booking.quantity == 3


class TestCancelBooking:
    def test_cancel_booking_success(self):
        existing = MagicMock()
        existing.status = "confirmed"
        existing.resource_id = uuid.uuid4()
        existing.user_id = uuid.uuid4()
        existing.id = uuid.uuid4()
        service, *_ = _make_service(
            resource=_make_resource(), existing_booking=existing
        )

        result = service.cancel_booking(existing.id)

        assert result.status == "cancelled"

    def test_cancel_already_cancelled_raises(self):
        existing = MagicMock()
        existing.status = "cancelled"
        service, *_ = _make_service(existing_booking=existing)

        with pytest.raises(BookingError, match="Cannot cancel"):
            service.cancel_booking(uuid.uuid4())

    def test_cancel_completed_raises(self):
        existing = MagicMock()
        existing.status = "completed"
        service, *_ = _make_service(existing_booking=existing)

        with pytest.raises(BookingError, match="Cannot cancel"):
            service.cancel_booking(uuid.uuid4())

    def test_cancel_publishes_event(self):
        existing = MagicMock()
        existing.status = "confirmed"
        existing.resource_id = uuid.uuid4()
        existing.user_id = uuid.uuid4()
        existing.id = uuid.uuid4()
        resource = _make_resource()
        service, _, _, _, event_bus = _make_service(
            resource=resource, existing_booking=existing
        )

        service.cancel_booking(existing.id)

        event_bus.publish.assert_called_once()
        assert event_bus.publish.call_args[0][0] == "booking.cancelled"

    def test_cancel_not_found_raises(self):
        service, *_ = _make_service(existing_booking=None)

        with pytest.raises(BookingError, match="not found"):
            service.cancel_booking(uuid.uuid4())


class TestCancelByProvider:
    def test_cancel_by_provider_success(self):
        existing = MagicMock()
        existing.status = "confirmed"
        existing.resource_id = uuid.uuid4()
        existing.user_id = uuid.uuid4()
        existing.id = uuid.uuid4()
        service, _, _, _, event_bus = _make_service(
            resource=_make_resource(), existing_booking=existing
        )

        result = service.cancel_by_provider(existing.id, reason="Doctor is sick")

        assert result.status == "cancelled"
        event_bus.publish.assert_called_once()
        assert event_bus.publish.call_args[0][0] == "booking.cancelled_by_provider"
        assert event_bus.publish.call_args[0][1]["reason"] == "Doctor is sick"


class TestCompleteBooking:
    def test_complete_booking_success(self):
        existing = MagicMock()
        existing.status = "confirmed"
        existing.resource_id = uuid.uuid4()
        existing.user_id = uuid.uuid4()
        existing.id = uuid.uuid4()
        service, *_ = _make_service(
            resource=_make_resource(), existing_booking=existing
        )

        result = service.complete_booking(existing.id)

        assert result.status == "completed"

    def test_complete_non_confirmed_raises(self):
        existing = MagicMock()
        existing.status = "pending"
        service, *_ = _make_service(existing_booking=existing)

        with pytest.raises(BookingError, match="only complete confirmed"):
            service.complete_booking(uuid.uuid4())

    def test_complete_publishes_event(self):
        existing = MagicMock()
        existing.status = "confirmed"
        existing.resource_id = uuid.uuid4()
        existing.user_id = uuid.uuid4()
        existing.id = uuid.uuid4()
        service, _, _, _, event_bus = _make_service(
            resource=_make_resource(), existing_booking=existing
        )

        service.complete_booking(existing.id)

        event_bus.publish.assert_called_once()
        assert event_bus.publish.call_args[0][0] == "booking.completed"
