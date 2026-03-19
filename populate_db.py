#!/usr/bin/env python3
"""Populate booking demo data. Idempotent — safe to re-run.

Usage: python plugins/booking/populate_db.py [--force]
"""
import argparse
import sys
from decimal import Decimal

sys.path.insert(0, "/app")

from vbwd.app import create_app  # noqa: E402
from vbwd.extensions import db  # noqa: E402

from plugins.booking.booking.models.resource_category import (  # noqa: E402
    BookableResourceCategory,
)
from plugins.booking.booking.models.resource import BookableResource  # noqa: E402
from plugins.booking.booking.models.booking import Booking  # noqa: E402


CATEGORIES = [
    {
        "name": "Medical",
        "slug": "medical",
        "description": "Medical appointments and consultations",
        "sort_order": 0,
    },
    {
        "name": "Workspace",
        "slug": "workspace",
        "description": "Meeting rooms and coworking spaces",
        "sort_order": 1,
    },
    {
        "name": "Events",
        "slug": "events",
        "description": "Event spaces and group activities",
        "sort_order": 2,
    },
]

WEEKDAY_SCHEDULE = {
    "schedule": {
        "mon": [{"start": "09:00", "end": "17:00"}],
        "tue": [{"start": "09:00", "end": "17:00"}],
        "wed": [{"start": "09:00", "end": "17:00"}],
        "thu": [{"start": "09:00", "end": "17:00"}],
        "fri": [{"start": "09:00", "end": "17:00"}],
        "sat": [],
        "sun": [],
    },
    "lead_time_hours": 2,
    "max_advance_days": 90,
}

HOTEL_SCHEDULE = {
    "schedule": {
        "mon": [{"start": "14:00", "end": "23:59"}],
        "tue": [{"start": "14:00", "end": "23:59"}],
        "wed": [{"start": "14:00", "end": "23:59"}],
        "thu": [{"start": "14:00", "end": "23:59"}],
        "fri": [{"start": "14:00", "end": "23:59"}],
        "sat": [{"start": "14:00", "end": "23:59"}],
        "sun": [{"start": "14:00", "end": "23:59"}],
    },
    "lead_time_hours": 24,
    "max_advance_days": 365,
}

RESOURCES = [
    {
        "name": "Dr. Smith",
        "slug": "dr-smith",
        "description": "General practitioner — 30 minute consultations",
        "resource_type": "specialist",
        "capacity": 1,
        "slot_duration_minutes": 30,
        "price": Decimal("50.00"),
        "price_unit": "per_slot",
        "availability": WEEKDAY_SCHEDULE,
        "custom_fields_schema": [
            {"id": "symptoms", "label": "Symptoms", "type": "text", "required": True},
            {
                "id": "insurance",
                "label": "Insurance ID",
                "type": "string",
                "required": False,
            },
        ],
        "config": {"buffer_minutes": 10, "confirmation_mode": "auto"},
        "categories": ["medical"],
    },
    {
        "name": "Dr. Johnson",
        "slug": "dr-johnson",
        "description": "Dentist — 45 minute appointments",
        "resource_type": "specialist",
        "capacity": 1,
        "slot_duration_minutes": 45,
        "price": Decimal("75.00"),
        "price_unit": "per_slot",
        "availability": WEEKDAY_SCHEDULE,
        "custom_fields_schema": [
            {
                "id": "concern",
                "label": "Primary Concern",
                "type": "string",
                "required": True,
            },
        ],
        "config": {"buffer_minutes": 15, "confirmation_mode": "auto"},
        "categories": ["medical"],
    },
    {
        "name": "Meeting Room A",
        "slug": "meeting-room-a",
        "description": "Conference room for up to 10 people",
        "resource_type": "space",
        "capacity": 10,
        "slot_duration_minutes": 60,
        "price": Decimal("25.00"),
        "price_unit": "per_hour",
        "availability": WEEKDAY_SCHEDULE,
        "custom_fields_schema": [
            {
                "id": "attendees",
                "label": "Number of Attendees",
                "type": "integer",
                "required": True,
            },
            {
                "id": "projector",
                "label": "Need Projector?",
                "type": "boolean",
                "required": False,
            },
        ],
        "config": {"buffer_minutes": 15, "confirmation_mode": "auto"},
        "categories": ["workspace"],
    },
    {
        "name": "Yoga Studio",
        "slug": "yoga-studio",
        "description": "Group yoga class — 20 spots available",
        "resource_type": "class",
        "capacity": 20,
        "slot_duration_minutes": 60,
        "price": Decimal("15.00"),
        "price_unit": "per_slot",
        "availability": WEEKDAY_SCHEDULE,
        "custom_fields_schema": [],
        "config": {"buffer_minutes": 30, "confirmation_mode": "auto"},
        "categories": ["events"],
    },
    {
        "name": "Hotel Room Standard",
        "slug": "hotel-standard",
        "description": "Standard hotel room — per night",
        "resource_type": "room",
        "capacity": 5,
        "slot_duration_minutes": None,
        "price": Decimal("89.00"),
        "price_unit": "per_night",
        "availability": HOTEL_SCHEDULE,
        "custom_fields_schema": [
            {
                "id": "guests",
                "label": "Number of Guests",
                "type": "integer",
                "required": True,
            },
            {
                "id": "breakfast",
                "label": "Include Breakfast?",
                "type": "boolean",
                "required": False,
            },
        ],
        "config": {"confirmation_mode": "auto"},
        "categories": ["events"],
    },
    {
        "name": "Hotel Room Suite",
        "slug": "hotel-suite",
        "description": "Luxury suite — per night",
        "resource_type": "room",
        "capacity": 2,
        "slot_duration_minutes": None,
        "price": Decimal("189.00"),
        "price_unit": "per_night",
        "availability": HOTEL_SCHEDULE,
        "custom_fields_schema": [
            {
                "id": "guests",
                "label": "Number of Guests",
                "type": "integer",
                "required": True,
            },
            {
                "id": "breakfast",
                "label": "Include Breakfast?",
                "type": "boolean",
                "required": False,
            },
            {
                "id": "champagne",
                "label": "Welcome Champagne?",
                "type": "boolean",
                "required": False,
            },
        ],
        "config": {"confirmation_mode": "manual"},
        "categories": ["events"],
    },
]


def populate(force=False):
    print("=== Booking Plugin — Demo Data ===\n")

    # Categories
    category_map = {}
    for category_data in CATEGORIES:
        existing = (
            db.session.query(BookableResourceCategory)
            .filter_by(slug=category_data["slug"])
            .first()
        )
        if existing and not force:
            print(f"  Exists: category '{existing.name}'")
            category_map[category_data["slug"]] = existing
        else:
            if existing and force:
                category = existing
            else:
                category = BookableResourceCategory()
            category.name = category_data["name"]
            category.slug = category_data["slug"]
            category.description = category_data["description"]
            category.sort_order = category_data["sort_order"]
            category.is_active = True
            db.session.add(category)
            db.session.flush()
            print(f"  Created: category '{category.name}'")
            category_map[category_data["slug"]] = category

    # Resources
    for resource_data in RESOURCES:
        existing = (
            db.session.query(BookableResource)
            .filter_by(slug=resource_data["slug"])
            .first()
        )
        if existing and not force:
            print(f"  Exists: resource '{existing.name}'")
            continue

        if existing and force:
            resource = existing
        else:
            resource = BookableResource()

        resource.name = resource_data["name"]
        resource.slug = resource_data["slug"]
        resource.description = resource_data["description"]
        resource.resource_type = resource_data["resource_type"]
        resource.capacity = resource_data["capacity"]
        resource.slot_duration_minutes = resource_data["slot_duration_minutes"]
        resource.price = resource_data["price"]
        resource.price_unit = resource_data["price_unit"]
        resource.availability = resource_data["availability"]
        resource.custom_fields_schema = resource_data["custom_fields_schema"]
        resource.config = resource_data["config"]
        resource.is_active = True

        # Attach categories
        resource.categories = []
        for category_slug in resource_data["categories"]:
            category = category_map.get(category_slug)
            if category:
                resource.categories.append(category)

        db.session.add(resource)
        db.session.flush()
        print(f"  Created: resource '{resource.name}' ({resource.resource_type})")

    db.session.commit()

    # Summary
    category_count = db.session.query(BookableResourceCategory).count()
    resource_count = db.session.query(BookableResource).count()
    booking_count = db.session.query(Booking).count()
    print("\n=== Done ===")
    print(f"  Categories: {category_count}")
    print(f"  Resources:  {resource_count}")
    print(f"  Bookings:   {booking_count}")


def main():
    parser = argparse.ArgumentParser(description="Populate booking demo data")
    parser.add_argument("--force", action="store_true", help="Overwrite existing data")
    parser.add_argument("--check", action="store_true", help="Check if data exists")
    arguments = parser.parse_args()

    app = create_app()
    with app.app_context():
        if arguments.check:
            count = db.session.query(BookableResource).count()
            sys.exit(1 if count > 0 else 0)
        populate(force=arguments.force)


if __name__ == "__main__":
    main()
