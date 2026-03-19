"""Unit tests for BookableResource model."""
import uuid
from datetime import datetime
from decimal import Decimal

from plugins.booking.booking.models.resource import BookableResource


class TestBookableResource:
    def test_create_specialist_resource(self):
        resource = BookableResource()
        resource.name = "Dr. Smith"
        resource.slug = "dr-smith"
        resource.resource_type = "specialist"
        resource.capacity = 1
        resource.slot_duration_minutes = 30
        resource.price = Decimal("50.00")
        resource.price_unit = "per_slot"

        assert resource.resource_type == "specialist"
        assert resource.capacity == 1
        assert resource.slot_duration_minutes == 30

    def test_create_hotel_room_resource(self):
        resource = BookableResource()
        resource.name = "Standard Room"
        resource.slug = "standard-room"
        resource.resource_type = "room"
        resource.capacity = 1
        resource.slot_duration_minutes = None
        resource.price = Decimal("89.00")
        resource.price_unit = "per_night"

        assert resource.slot_duration_minutes is None
        assert resource.price_unit == "per_night"

    def test_create_group_class_resource(self):
        resource = BookableResource()
        resource.name = "Yoga Class"
        resource.slug = "yoga-class"
        resource.resource_type = "class"
        resource.capacity = 20
        resource.slot_duration_minutes = 60
        resource.price = Decimal("15.00")

        assert resource.capacity == 20

    def test_availability_json(self):
        resource = BookableResource()
        resource.name = "Test"
        resource.slug = "test"
        resource.resource_type = "specialist"
        resource.price = Decimal("50.00")
        resource.availability = {
            "schedule": {
                "mon": [{"start": "09:00", "end": "17:00"}],
                "tue": [{"start": "09:00", "end": "17:00"}],
                "wed": [],
            },
            "exceptions": [
                {"date": "2026-04-01", "closed": True, "reason": "Holiday"},
            ],
            "lead_time_hours": 24,
            "max_advance_days": 90,
        }

        assert len(resource.availability["schedule"]["mon"]) == 1
        assert resource.availability["schedule"]["wed"] == []
        assert resource.availability["lead_time_hours"] == 24

    def test_custom_fields_schema(self):
        resource = BookableResource()
        resource.name = "Dr. Johnson"
        resource.slug = "dr-johnson"
        resource.resource_type = "specialist"
        resource.price = Decimal("75.00")
        resource.custom_fields_schema = [
            {"id": "symptoms", "label": "Symptoms", "type": "text", "required": True},
            {"id": "insurance", "label": "Insurance ID", "type": "string", "required": False},
        ]

        assert len(resource.custom_fields_schema) == 2
        assert resource.custom_fields_schema[0]["id"] == "symptoms"

    def test_config_stores_cancellation_settings(self):
        resource = BookableResource()
        resource.name = "Room"
        resource.slug = "room"
        resource.resource_type = "room"
        resource.price = Decimal("89.00")
        resource.config = {
            "confirmation_mode": "auto",
            "cancellation_hours": 24,
            "requires_payment": True,
            "buffer_minutes": 15,
            "timezone": "Europe/Berlin",
        }

        assert resource.config["confirmation_mode"] == "auto"
        assert resource.config["buffer_minutes"] == 15

    def test_to_dict(self):
        resource = BookableResource()
        resource.id = uuid.uuid4()
        resource.name = "Meeting Room A"
        resource.slug = "meeting-room-a"
        resource.resource_type = "space"
        resource.capacity = 10
        resource.slot_duration_minutes = 60
        resource.price = Decimal("25.00")
        resource.currency = "EUR"
        resource.price_unit = "per_hour"
        resource.is_active = True
        resource.availability = {}
        resource.created_at = datetime(2026, 3, 19)
        resource.updated_at = datetime(2026, 3, 19)

        result = resource.to_dict()

        assert result["name"] == "Meeting Room A"
        assert result["resource_type"] == "space"
        assert result["capacity"] == 10
        assert result["price"] == "25.00"
        assert result["price_unit"] == "per_hour"
        assert result["categories"] == []
