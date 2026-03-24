# flake8: noqa: E501
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
from plugins.booking.booking.models.custom_schema import (  # noqa: E402
    BookingCustomSchema,
)
from plugins.booking.booking.models.booking import Booking  # noqa: E402


SCHEMAS = [
    {
        "name": "Specialist",
        "slug": "specialist",
        "sort_order": 0,
        "fields": [
            {"id": "symptoms", "label": "Symptoms", "type": "text", "required": True},
            {
                "id": "insurance",
                "label": "Insurance ID",
                "type": "string",
                "required": False,
            },
        ],
    },
    {
        "name": "Room",
        "slug": "room",
        "sort_order": 1,
        "fields": [
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
    },
    {
        "name": "Space",
        "slug": "space",
        "sort_order": 2,
        "fields": [
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
    },
    {
        "name": "Seat",
        "slug": "seat",
        "sort_order": 3,
        "fields": [],
    },
    {
        "name": "Class",
        "slug": "class",
        "sort_order": 4,
        "fields": [],
    },
]

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

    # Schemas (replace resource types)
    schema_map = {}
    for schema_data in SCHEMAS:
        existing = (
            db.session.query(BookingCustomSchema)
            .filter_by(slug=schema_data["slug"])
            .first()
        )
        if existing and not force:
            print(f"  Exists: schema '{existing.name}'")
            schema_map[schema_data["slug"]] = existing
        else:
            if existing and force:
                schema = existing
            else:
                schema = BookingCustomSchema()
            schema.name = schema_data["name"]
            schema.slug = schema_data["slug"]
            schema.fields = schema_data["fields"]
            schema.sort_order = schema_data["sort_order"]
            schema.is_active = True
            db.session.add(schema)
            db.session.flush()
            print(f"  Created: schema '{schema.name}'")
            schema_map[schema_data["slug"]] = schema

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
        # Assign schema by slug
        schema_slug = resource_data["resource_type"]
        schema = schema_map.get(schema_slug)
        if schema:
            resource.custom_schema_id = schema.id
        resource.capacity = resource_data["capacity"]
        resource.slot_duration_minutes = resource_data["slot_duration_minutes"]
        resource.price = resource_data["price"]
        resource.price_unit = resource_data["price_unit"]
        resource.availability = resource_data["availability"]
        resource.custom_fields_schema = resource_data.get("custom_fields_schema")
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
        print(f"  Created: resource '{resource.name}' (schema: {schema_slug})")

    db.session.commit()

    # CMS Layouts, Widgets, Pages (same pattern as GHRM populate_ghrm.py)
    try:
        from plugins.cms.src.models.cms_layout import CmsLayout
        from plugins.cms.src.models.cms_widget import CmsWidget
        from plugins.cms.src.models.cms_layout_widget import CmsLayoutWidget
        from plugins.cms.src.models.cms_page import CmsPage
        from plugins.cms.src.models.cms_category import CmsCategory

        def _get_or_create(model, slug, **kwargs):
            obj = db.session.query(model).filter_by(slug=slug).first()
            if obj:
                return obj, False
            obj = model(slug=slug, **kwargs)
            db.session.add(obj)
            db.session.flush()
            return obj, True

        def _assign_widget(layout, widget, area_name, sort_order=0):
            exists = (
                db.session.query(CmsLayoutWidget)
                .filter_by(
                    layout_id=layout.id,
                    widget_id=widget.id,
                    area_name=area_name,
                )
                .first()
            )
            if not exists:
                db.session.add(
                    CmsLayoutWidget(
                        layout_id=layout.id,
                        widget_id=widget.id,
                        area_name=area_name,
                        sort_order=sort_order,
                    )
                )
                db.session.flush()
                return True
            return False

        # ── CMS Category ────────────────────────────────────────────────────

        print("\n=== CMS Category ===")
        cms_cat, created = _get_or_create(
            CmsCategory,
            "booking",
            name="Booking",
            sort_order=60,
        )
        print(f"  {'Created' if created else 'Exists'}: cms_category booking")

        # ── Layouts ─────────────────────────────────────────────────────────

        CATALOGUE_LAYOUT_SLUG = "booking-catalogue"
        DETAIL_LAYOUT_SLUG = "booking-resource-detail"
        FORM_LAYOUT_SLUG = "booking-form"
        SUCCESS_LAYOUT_SLUG = "booking-success"
        CANCEL_LAYOUT_SLUG = "booking-cancel"

        catalogue_areas = [
            {"name": "header", "type": "header", "label": "Header"},
            {"name": "breadcrumbs", "type": "vue", "label": ""},
            {"name": "booking-catalogue", "type": "vue", "label": "Booking Catalogue"},
            {"name": "footer", "type": "footer", "label": "Footer"},
        ]
        detail_areas = [
            {"name": "header", "type": "header", "label": "Header"},
            {"name": "breadcrumbs", "type": "vue", "label": ""},
            {
                "name": "booking-resource-detail",
                "type": "vue",
                "label": "Resource Detail",
            },
            {"name": "footer", "type": "footer", "label": "Footer"},
        ]
        form_areas = [
            {"name": "header", "type": "header", "label": "Header"},
            {"name": "breadcrumbs", "type": "vue", "label": ""},
            {"name": "booking-form", "type": "vue", "label": "Booking Form"},
            {"name": "footer", "type": "footer", "label": "Footer"},
        ]
        success_areas = [
            {"name": "header", "type": "header", "label": "Header"},
            {"name": "booking-success", "type": "vue", "label": "Booking Success"},
            {"name": "footer", "type": "footer", "label": "Footer"},
        ]
        cancel_areas = [
            {"name": "header", "type": "header", "label": "Header"},
            {"name": "booking-cancel", "type": "vue", "label": "Booking Cancel"},
            {"name": "footer", "type": "footer", "label": "Footer"},
        ]

        print("\n=== CMS Layouts ===")

        layout_catalogue, created = _get_or_create(
            CmsLayout,
            CATALOGUE_LAYOUT_SLUG,
            name="Booking Catalogue",
            areas=catalogue_areas,
            sort_order=20,
            is_active=True,
        )
        if not created:
            layout_catalogue.areas = catalogue_areas
            db.session.flush()
        print(f"  {'Created' if created else 'Exists'}: {CATALOGUE_LAYOUT_SLUG}")

        layout_detail, created = _get_or_create(
            CmsLayout,
            DETAIL_LAYOUT_SLUG,
            name="Booking Resource Detail",
            areas=detail_areas,
            sort_order=21,
            is_active=True,
        )
        if not created:
            layout_detail.areas = detail_areas
            db.session.flush()
        print(f"  {'Created' if created else 'Exists'}: {DETAIL_LAYOUT_SLUG}")

        layout_form, created = _get_or_create(
            CmsLayout,
            FORM_LAYOUT_SLUG,
            name="Booking Form",
            areas=form_areas,
            sort_order=22,
            is_active=True,
        )
        if not created:
            layout_form.areas = form_areas
            db.session.flush()
        print(f"  {'Created' if created else 'Exists'}: {FORM_LAYOUT_SLUG}")

        layout_success, created = _get_or_create(
            CmsLayout,
            SUCCESS_LAYOUT_SLUG,
            name="Booking Success",
            areas=success_areas,
            sort_order=23,
            is_active=True,
        )
        if not created:
            layout_success.areas = success_areas
            db.session.flush()
        print(f"  {'Created' if created else 'Exists'}: {SUCCESS_LAYOUT_SLUG}")

        layout_cancel, created = _get_or_create(
            CmsLayout,
            CANCEL_LAYOUT_SLUG,
            name="Booking Cancel",
            areas=cancel_areas,
            sort_order=24,
            is_active=True,
        )
        if not created:
            layout_cancel.areas = cancel_areas
            db.session.flush()
        print(f"  {'Created' if created else 'Exists'}: {CANCEL_LAYOUT_SLUG}")

        # ── Widgets ─────────────────────────────────────────────────────────

        print("\n=== CMS Widgets ===")

        WIDGETS = [
            {
                "slug": "booking-catalogue",
                "name": "Booking Catalogue",
                "widget_type": "vue-component",
                "content_json": {
                    "component": "BookingCatalogue",
                    "items_per_page": 12,
                },
            },
            {
                "slug": "booking-resource-detail",
                "name": "Booking Resource Detail",
                "widget_type": "vue-component",
                "content_json": {
                    "component": "BookingResourceDetail",
                    "items_per_page": 1,
                },
            },
            {
                "slug": "booking-form",
                "name": "Booking Form",
                "widget_type": "vue-component",
                "content_json": {
                    "component": "BookingForm",
                    "items_per_page": 1,
                },
            },
            {
                "slug": "booking-success",
                "name": "Booking Success",
                "widget_type": "vue-component",
                "content_json": {
                    "component": "BookingSuccess",
                    "items_per_page": 1,
                },
            },
            {
                "slug": "booking-cancel",
                "name": "Booking Cancel",
                "widget_type": "vue-component",
                "content_json": {
                    "component": "BookingCancel",
                    "items_per_page": 1,
                },
            },
        ]

        breadcrumbs_widget = (
            db.session.query(CmsWidget).filter_by(slug="breadcrumbs").first()
        )

        widget_map = {}
        for widget_data in WIDGETS:
            widget, created = _get_or_create(
                CmsWidget,
                widget_data["slug"],
                name=widget_data["name"],
                widget_type=widget_data["widget_type"],
                content_json=widget_data["content_json"],
                is_active=True,
            )
            widget_map[widget_data["slug"]] = widget
            print(f"  {'Created' if created else 'Exists'}: {widget_data['slug']}")

        # ── Layout → Widget assignments ─────────────────────────────────────

        print("\n=== Layout Widget Assignments ===")

        header_nav = db.session.query(CmsWidget).filter_by(slug="header-nav").first()
        footer_nav = db.session.query(CmsWidget).filter_by(slug="footer-nav").first()

        # Catalogue layout
        if header_nav:
            added = _assign_widget(layout_catalogue, header_nav, "header", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {CATALOGUE_LAYOUT_SLUG} / header → header-nav"
            )
        else:
            print("  ! header-nav not found — run populate_cms first")

        if breadcrumbs_widget:
            added = _assign_widget(
                layout_catalogue, breadcrumbs_widget, "breadcrumbs", 3
            )
            print(
                f"  {'Assigned' if added else 'Exists'}: {CATALOGUE_LAYOUT_SLUG} / breadcrumbs → breadcrumbs"
            )

        added = _assign_widget(
            layout_catalogue, widget_map["booking-catalogue"], "booking-catalogue", 0
        )
        print(
            f"  {'Assigned' if added else 'Exists'}: {CATALOGUE_LAYOUT_SLUG} / booking-catalogue → booking-catalogue"
        )

        if footer_nav:
            added = _assign_widget(layout_catalogue, footer_nav, "footer", 0)
            status = "Assigned" if added else "Exists"
            print(f"  {status}: {CATALOGUE_LAYOUT_SLUG} / footer → footer-nav")

        # Detail layout
        if header_nav:
            added = _assign_widget(layout_detail, header_nav, "header", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {DETAIL_LAYOUT_SLUG} / header → header-nav"
            )

        if breadcrumbs_widget:
            added = _assign_widget(layout_detail, breadcrumbs_widget, "breadcrumbs", 3)
            print(
                f"  {'Assigned' if added else 'Exists'}: {DETAIL_LAYOUT_SLUG} / breadcrumbs → breadcrumbs"
            )

        added = _assign_widget(
            layout_detail,
            widget_map["booking-resource-detail"],
            "booking-resource-detail",
            0,
        )
        status = "Assigned" if added else "Exists"
        widget_name = "booking-resource-detail"
        print(f"  {status}: {DETAIL_LAYOUT_SLUG} / {widget_name} → {widget_name}")

        if footer_nav:
            added = _assign_widget(layout_detail, footer_nav, "footer", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {DETAIL_LAYOUT_SLUG} / footer → footer-nav"
            )

        # Form layout
        if header_nav:
            added = _assign_widget(layout_form, header_nav, "header", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {FORM_LAYOUT_SLUG} / header → header-nav"
            )

        if breadcrumbs_widget:
            added = _assign_widget(layout_form, breadcrumbs_widget, "breadcrumbs", 3)
            print(
                f"  {'Assigned' if added else 'Exists'}: {FORM_LAYOUT_SLUG} / breadcrumbs → breadcrumbs"
            )

        added = _assign_widget(
            layout_form, widget_map["booking-form"], "booking-form", 0
        )
        status = "Assigned" if added else "Exists"
        print(f"  {status}: {FORM_LAYOUT_SLUG} / booking-form → booking-form")

        if footer_nav:
            added = _assign_widget(layout_form, footer_nav, "footer", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {FORM_LAYOUT_SLUG} / footer → footer-nav"
            )

        # Success layout
        if header_nav:
            added = _assign_widget(layout_success, header_nav, "header", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {SUCCESS_LAYOUT_SLUG} / header → header-nav"
            )

        added = _assign_widget(
            layout_success, widget_map["booking-success"], "booking-success", 0
        )
        status = "Assigned" if added else "Exists"
        print(f"  {status}: {SUCCESS_LAYOUT_SLUG} / booking-success → booking-success")

        if footer_nav:
            added = _assign_widget(layout_success, footer_nav, "footer", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {SUCCESS_LAYOUT_SLUG} / footer → footer-nav"
            )

        # Cancel layout
        if header_nav:
            added = _assign_widget(layout_cancel, header_nav, "header", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {CANCEL_LAYOUT_SLUG} / header → header-nav"
            )

        added = _assign_widget(
            layout_cancel, widget_map["booking-cancel"], "booking-cancel", 0
        )
        status = "Assigned" if added else "Exists"
        print(f"  {status}: {CANCEL_LAYOUT_SLUG} / booking-cancel → booking-cancel")

        if footer_nav:
            added = _assign_widget(layout_cancel, footer_nav, "footer", 0)
            print(
                f"  {'Assigned' if added else 'Exists'}: {CANCEL_LAYOUT_SLUG} / footer → footer-nav"
            )

        # ── CMS Pages ───────────────────────────────────────────────────────

        print("\n=== CMS Pages ===")

        # Template page for catalogue (used by CmsPage.vue to resolve layout)
        page_catalogue, created = _get_or_create(
            CmsPage,
            "booking",
            name="Booking Catalogue",
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=0,
            category_id=cms_cat.id,
            layout_id=layout_catalogue.id,
            meta_title="Booking",
            meta_description="Browse and book resources — appointments, rooms, spaces",
            robots="index,follow",
        )
        print(f"  {'Created' if created else 'Exists'}: /booking")

        # Template page for resource detail
        page_detail, created = _get_or_create(
            CmsPage,
            "booking-resource-detail",
            name="Booking Resource Detail Template",
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=1,
            category_id=cms_cat.id,
            layout_id=layout_detail.id,
            meta_title="Resource Detail",
            robots="noindex",
        )
        print(f"  {'Created' if created else 'Exists'}: /booking-resource-detail")

        # Template page for booking form
        page_form, created = _get_or_create(
            CmsPage,
            FORM_LAYOUT_SLUG,
            name="Booking Form",
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=2,
            category_id=cms_cat.id,
            layout_id=layout_form.id,
            meta_title="Book Now",
            robots="noindex",
        )
        print(f"  {'Created' if created else 'Exists'}: /{FORM_LAYOUT_SLUG}")

        # Booking success page
        page_success, created = _get_or_create(
            CmsPage,
            SUCCESS_LAYOUT_SLUG,
            name="Booking Success",
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=3,
            category_id=cms_cat.id,
            layout_id=layout_success.id,
            meta_title="Booking Confirmed",
            robots="noindex",
        )
        print(f"  {'Created' if created else 'Exists'}: /{SUCCESS_LAYOUT_SLUG}")

        # Booking cancel page
        page_cancel, created = _get_or_create(
            CmsPage,
            CANCEL_LAYOUT_SLUG,
            name="Booking Cancelled",
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=4,
            category_id=cms_cat.id,
            layout_id=layout_cancel.id,
            meta_title="Payment Cancelled",
            robots="noindex",
        )
        print(f"  {'Created' if created else 'Exists'}: /{CANCEL_LAYOUT_SLUG}")

        db.session.commit()
    except ImportError:
        print("  ! CMS plugin not installed — skipping CMS setup")

    # Email templates for booking events
    try:
        from plugins.email.src.models.email_template import EmailTemplate

        BOOKING_TEMPLATES = [
            {
                "event_type": "booking.created",
                "subject": "Booking confirmed — {{ resource_name }}",
                "html_body": (
                    '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
                    '<h1 style="color:#27ae60;">Booking confirmed</h1>'
                    "<p>Hi {{ user_name }},</p>"
                    "<p>Your booking for <strong>{{ resource_name }}</strong> has been confirmed.</p>"
                    "<ul><li>Start: {{ start_at }}</li><li>End: {{ end_at }}</li></ul>"
                    '<p><a href="{{ booking_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View Booking</a></p>'
                    "</body></html>"
                ),
                "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} is confirmed.\nStart: {{ start_at }}\nEnd: {{ end_at }}\n\nView: {{ booking_url }}",
                "is_active": True,
            },
            {
                "event_type": "booking.cancelled",
                "subject": "Booking cancelled — {{ resource_name }}",
                "html_body": (
                    '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
                    '<h1 style="color:#e74c3c;">Booking cancelled</h1>'
                    "<p>Hi {{ user_name }},</p>"
                    "<p>Your booking for <strong>{{ resource_name }}</strong> has been cancelled.</p>"
                    "</body></html>"
                ),
                "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} has been cancelled.",
                "is_active": True,
            },
            {
                "event_type": "booking.cancelled_by_provider",
                "subject": "Booking cancelled by provider — {{ resource_name }}",
                "html_body": (
                    '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
                    '<h1 style="color:#e74c3c;">Booking cancelled by provider</h1>'
                    "<p>Hi {{ user_name }},</p>"
                    "<p>Your booking for <strong>{{ resource_name }}</strong> was cancelled by the provider.</p>"
                    "<p>Reason: {{ reason }}</p>"
                    "<p>A full refund will be issued.</p>"
                    "</body></html>"
                ),
                "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} was cancelled.\nReason: {{ reason }}\n\nA full refund will be issued.",
                "is_active": True,
            },
            {
                "event_type": "booking.completed",
                "subject": "Booking completed — {{ resource_name }}",
                "html_body": (
                    '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
                    '<h1 style="color:#2c3e50;">Booking completed</h1>'
                    "<p>Hi {{ user_name }},</p>"
                    "<p>Your booking for <strong>{{ resource_name }}</strong> has been completed. Thank you!</p>"
                    "</body></html>"
                ),
                "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} has been completed. Thank you!",
                "is_active": True,
            },
        ]

        print("\n=== Email Templates ===")
        for tpl_data in BOOKING_TEMPLATES:
            existing = (
                db.session.query(EmailTemplate)
                .filter_by(event_type=tpl_data["event_type"])
                .first()
            )
            if existing:
                print(f"  Exists: {tpl_data['event_type']}")
            else:
                tpl = EmailTemplate(
                    event_type=tpl_data["event_type"],
                    subject=tpl_data["subject"],
                    html_body=tpl_data["html_body"],
                    text_body=tpl_data["text_body"],
                    is_active=tpl_data["is_active"],
                )
                db.session.add(tpl)
                print(f"  Created: {tpl_data['event_type']}")
        db.session.commit()
    except ImportError:
        print("  ! Email plugin not installed — skipping email templates")

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
