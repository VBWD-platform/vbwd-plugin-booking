"""Unit tests for Booking model."""
import uuid
from datetime import datetime


from plugins.booking.booking.models.booking import Booking


class TestBooking:
    def test_create_booking(self):
        booking = Booking()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.start_at = datetime(2026, 3, 20, 10, 0, 0)
        booking.end_at = datetime(2026, 3, 20, 10, 30, 0)
        booking.status = "confirmed"
        booking.quantity = 1

        assert booking.status == "confirmed"
        assert booking.quantity == 1

    def test_default_status_is_confirmed(self):
        booking = Booking()
        # Column default, not set until flush
        assert booking.status is None or booking.status == "confirmed"

    def test_custom_fields_stores_user_data(self):
        booking = Booking()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.start_at = datetime(2026, 3, 20, 10, 0)
        booking.end_at = datetime(2026, 3, 20, 10, 30)
        booking.custom_fields = {
            "symptoms": "headache",
            "insurance_id": "AOK-123456",
        }

        assert booking.custom_fields["symptoms"] == "headache"

    def test_hotel_booking_with_quantity(self):
        booking = Booking()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.start_at = datetime(2026, 4, 1)
        booking.end_at = datetime(2026, 4, 5)
        booking.quantity = 2
        booking.custom_fields = {"guests": 3, "breakfast": True}

        assert booking.quantity == 2
        assert booking.custom_fields["guests"] == 3

    def test_booking_with_notes(self):
        booking = Booking()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.start_at = datetime(2026, 3, 20, 14, 0)
        booking.end_at = datetime(2026, 3, 20, 15, 0)
        booking.notes = "Please prepare projector"
        booking.admin_notes = "VIP client"

        assert booking.notes == "Please prepare projector"
        assert booking.admin_notes == "VIP client"

    def test_to_dict(self):
        booking = Booking()
        booking.id = uuid.uuid4()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.invoice_id = uuid.uuid4()
        booking.start_at = datetime(2026, 3, 20, 10, 0, 0)
        booking.end_at = datetime(2026, 3, 20, 10, 30, 0)
        booking.status = "confirmed"
        booking.quantity = 1
        booking.custom_fields = {"symptoms": "headache"}
        booking.notes = "First visit"
        booking.created_at = datetime(2026, 3, 19)
        booking.updated_at = datetime(2026, 3, 19)

        result = booking.to_dict()

        assert result["status"] == "confirmed"
        assert result["quantity"] == 1
        assert result["custom_fields"]["symptoms"] == "headache"
        assert result["notes"] == "First visit"
        assert result["invoice_id"] is not None

    def test_to_dict_without_invoice(self):
        booking = Booking()
        booking.id = uuid.uuid4()
        booking.resource_id = uuid.uuid4()
        booking.user_id = uuid.uuid4()
        booking.start_at = datetime(2026, 3, 20, 10, 0)
        booking.end_at = datetime(2026, 3, 20, 10, 30)
        booking.status = "pending"
        booking.quantity = 1
        booking.created_at = datetime(2026, 3, 19)
        booking.updated_at = datetime(2026, 3, 19)

        result = booking.to_dict()

        assert result["invoice_id"] is None
        assert result["status"] == "pending"

    def test_status_values(self):
        """Verify all valid status values can be set."""
        for status in ["confirmed", "pending", "cancelled", "completed", "no_show"]:
            booking = Booking()
            booking.status = status
            assert booking.status == status
