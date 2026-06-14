# flake8: noqa: E501
"""Booking demo catalog seed — the single home for the booking seed logic (S88).

``seed_catalog(session)`` is registered into core's demo-data registry from the
plugin's ``on_enable`` so ``flask reset-demo`` seeds booking schemas, categories,
resources, CMS content, and email templates through the same agnostic seam every
other plugin uses. The standalone ``plugins/booking/populate_db.py`` is a thin
wrapper over this function (DRY).

Idempotent: every row is upserted by slug, so a re-run creates nothing new.
"""
import logging
from decimal import Decimal

from vbwd.services.demo_tax_linker import link_demo_tax

logger = logging.getLogger(__name__)


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


def seed_catalog(session, force=False) -> dict:
    """Seed booking schemas, categories, resources, CMS content, and email
    templates through ``session``. Idempotent.

    Returns a small stats dict for the reset-demo summary.
    """
    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )
    from plugins.booking.booking.models.resource import BookableResource
    from plugins.booking.booking.models.custom_schema import BookingCustomSchema

    # Schemas (replace resource types)
    schema_map = {}
    for schema_data in SCHEMAS:
        existing = (
            session.query(BookingCustomSchema)
            .filter_by(slug=schema_data["slug"])
            .first()
        )
        if existing and not force:
            schema_map[schema_data["slug"]] = existing
        else:
            schema = existing if (existing and force) else BookingCustomSchema()
            schema.name = schema_data["name"]
            schema.slug = schema_data["slug"]
            schema.fields = schema_data["fields"]
            schema.sort_order = schema_data["sort_order"]
            schema.is_active = True
            session.add(schema)
            session.flush()
            schema_map[schema_data["slug"]] = schema

    # Categories
    category_map = {}
    for category_data in CATEGORIES:
        existing = (
            session.query(BookableResourceCategory)
            .filter_by(slug=category_data["slug"])
            .first()
        )
        if existing and not force:
            category_map[category_data["slug"]] = existing
        else:
            category = existing if (existing and force) else BookableResourceCategory()
            category.name = category_data["name"]
            category.slug = category_data["slug"]
            category.description = category_data["description"]
            category.sort_order = category_data["sort_order"]
            category.is_active = True
            session.add(category)
            session.flush()
            category_map[category_data["slug"]] = category

    # Resources
    for resource_data in RESOURCES:
        existing = (
            session.query(BookableResource)
            .filter_by(slug=resource_data["slug"])
            .first()
        )
        if existing and not force:
            continue

        resource = existing if (existing and force) else BookableResource()
        resource.name = resource_data["name"]
        resource.slug = resource_data["slug"]
        resource.description = resource_data["description"]
        schema = schema_map.get(resource_data["resource_type"])
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

        resource.categories = []
        for category_slug in resource_data["categories"]:
            category = category_map.get(category_slug)
            if category:
                resource.categories.append(category)

        session.add(resource)
        session.flush()

    session.commit()

    _link_resource_taxes(session)
    _populate_cms_content(session)
    _populate_checkout_page()
    _populate_email_templates(session)

    return {
        "booking_resources": session.query(BookableResource).count(),
        "booking_categories": session.query(BookableResourceCategory).count(),
    }


def _link_resource_taxes(session) -> None:
    """Link the canonical demo VAT to every demo resource (S85.4).

    Runs independently of resource creation: resources are skipped on a re-run,
    but the tax link must still be ensured. Idempotent (the core linker does not
    double-link) and a no-op when the canonical VAT is absent. The tax is
    resolved by code through the core linker — no cross-plugin import.
    """
    from plugins.booking.booking.models.resource import BookableResource

    resources = []
    for resource_data in RESOURCES:
        resource = (
            session.query(BookableResource)
            .filter_by(slug=resource_data["slug"])
            .first()
        )
        if resource is not None:
            resources.append(resource)

    link_demo_tax(session, resources)


def _populate_cms_content(session):
    """Create the booking CMS layouts, widgets, and pages."""
    try:
        from plugins.cms.src.models.cms_layout import CmsLayout
        from plugins.cms.src.models.cms_widget import CmsWidget
        from plugins.cms.src.models.cms_layout_widget import CmsLayoutWidget
        from plugins.cms.src.models.cms_page import CmsPage
        from plugins.cms.src.models.cms_category import CmsCategory
    except ImportError:
        logger.info("[booking] CMS plugin not installed — skipping CMS setup")
        return

    def _get_or_create(model, slug, **kwargs):
        obj = session.query(model).filter_by(slug=slug).first()
        if obj:
            return obj, False
        obj = model(slug=slug, **kwargs)
        session.add(obj)
        session.flush()
        return obj, True

    def _assign_widget(layout, widget, area_name, sort_order=0):
        exists = (
            session.query(CmsLayoutWidget)
            .filter_by(layout_id=layout.id, widget_id=widget.id, area_name=area_name)
            .first()
        )
        if not exists:
            session.add(
                CmsLayoutWidget(
                    layout_id=layout.id,
                    widget_id=widget.id,
                    area_name=area_name,
                    sort_order=sort_order,
                )
            )
            session.flush()

    cms_cat, _ = _get_or_create(CmsCategory, "booking", name="Booking", sort_order=60)

    CATALOGUE_LAYOUT_SLUG = "booking-catalogue"
    DETAIL_LAYOUT_SLUG = "booking-resource-detail"
    FORM_LAYOUT_SLUG = "booking-form"
    SUCCESS_LAYOUT_SLUG = "booking-success"
    CANCEL_LAYOUT_SLUG = "booking-cancel"

    def _nav_areas(content_area, content_label, include_breadcrumbs=True):
        areas = [{"name": "header", "type": "header", "label": "Header"}]
        if include_breadcrumbs:
            areas.append({"name": "breadcrumbs", "type": "vue", "label": ""})
        areas.append({"name": content_area, "type": "vue", "label": content_label})
        areas.append({"name": "footer", "type": "footer", "label": "Footer"})
        return areas

    layout_specs = [
        (
            CATALOGUE_LAYOUT_SLUG,
            "Booking Catalogue",
            "booking-catalogue",
            "Booking Catalogue",
            True,
            20,
        ),
        (
            DETAIL_LAYOUT_SLUG,
            "Booking Resource Detail",
            "booking-resource-detail",
            "Resource Detail",
            True,
            21,
        ),
        (FORM_LAYOUT_SLUG, "Booking Form", "booking-form", "Booking Form", True, 22),
        (
            SUCCESS_LAYOUT_SLUG,
            "Booking Success",
            "booking-success",
            "Booking Success",
            False,
            23,
        ),
        (
            CANCEL_LAYOUT_SLUG,
            "Booking Cancel",
            "booking-cancel",
            "Booking Cancel",
            False,
            24,
        ),
    ]
    layouts = {}
    for slug, name, area, label, has_bc, sort in layout_specs:
        areas = _nav_areas(area, label, include_breadcrumbs=has_bc)
        layout, created = _get_or_create(
            CmsLayout, slug, name=name, areas=areas, sort_order=sort, is_active=True
        )
        if not created:
            layout.areas = areas
            session.flush()
        layouts[slug] = layout

    WIDGETS = [
        (
            "booking-catalogue",
            "Booking Catalogue",
            {"component": "BookingCatalogue", "items_per_page": 12},
        ),
        (
            "booking-resource-detail",
            "Booking Resource Detail",
            {"component": "BookingResourceDetail", "items_per_page": 1},
        ),
        (
            "booking-form",
            "Booking Form",
            {"component": "BookingForm", "items_per_page": 1},
        ),
        (
            "booking-success",
            "Booking Success",
            {"component": "BookingSuccess", "items_per_page": 1},
        ),
        (
            "booking-cancel",
            "Booking Cancel",
            {"component": "BookingCancel", "items_per_page": 1},
        ),
    ]
    widget_map = {}
    for slug, name, content_json in WIDGETS:
        widget, _ = _get_or_create(
            CmsWidget,
            slug,
            name=name,
            widget_type="vue-component",
            content_json=content_json,
            is_active=True,
        )
        widget_map[slug] = widget

    header_nav = session.query(CmsWidget).filter_by(slug="header-nav").first()
    footer_nav = session.query(CmsWidget).filter_by(slug="footer-nav").first()
    breadcrumbs_widget = session.query(CmsWidget).filter_by(slug="breadcrumbs").first()

    # Content widget per layout (area name == widget slug)
    content_widget_by_layout = {
        CATALOGUE_LAYOUT_SLUG: "booking-catalogue",
        DETAIL_LAYOUT_SLUG: "booking-resource-detail",
        FORM_LAYOUT_SLUG: "booking-form",
        SUCCESS_LAYOUT_SLUG: "booking-success",
        CANCEL_LAYOUT_SLUG: "booking-cancel",
    }
    for slug, layout in layouts.items():
        if header_nav:
            _assign_widget(layout, header_nav, "header", 0)
        if breadcrumbs_widget and slug in (
            CATALOGUE_LAYOUT_SLUG,
            DETAIL_LAYOUT_SLUG,
            FORM_LAYOUT_SLUG,
        ):
            _assign_widget(layout, breadcrumbs_widget, "breadcrumbs", 3)
        content_slug = content_widget_by_layout[slug]
        _assign_widget(layout, widget_map[content_slug], content_slug, 0)
        if footer_nav:
            _assign_widget(layout, footer_nav, "footer", 0)

    page_specs = [
        (
            "booking",
            "Booking Catalogue",
            CATALOGUE_LAYOUT_SLUG,
            0,
            "Booking",
            "Browse and book resources — appointments, rooms, spaces",
            "index,follow",
        ),
        (
            "booking-resource-detail",
            "Booking Resource Detail Template",
            DETAIL_LAYOUT_SLUG,
            1,
            "Resource Detail",
            None,
            "noindex",
        ),
        (
            FORM_LAYOUT_SLUG,
            "Booking Form",
            FORM_LAYOUT_SLUG,
            2,
            "Book Now",
            None,
            "noindex",
        ),
        (
            SUCCESS_LAYOUT_SLUG,
            "Booking Success",
            SUCCESS_LAYOUT_SLUG,
            3,
            "Booking Confirmed",
            None,
            "noindex",
        ),
        (
            CANCEL_LAYOUT_SLUG,
            "Booking Cancelled",
            CANCEL_LAYOUT_SLUG,
            4,
            "Payment Cancelled",
            None,
            "noindex",
        ),
    ]
    for slug, name, layout_slug, sort, meta_title, meta_desc, robots in page_specs:
        kwargs = dict(
            name=name,
            language="en",
            content_json={"type": "doc", "content": []},
            is_published=True,
            sort_order=sort,
            category_id=cms_cat.id,
            layout_id=layouts[layout_slug].id,
            meta_title=meta_title,
            robots=robots,
        )
        if meta_desc is not None:
            kwargs["meta_description"] = meta_desc
        _get_or_create(CmsPage, slug, **kwargs)

    if header_nav:
        try:
            from uuid import uuid4
            from plugins.cms.src.models.cms_menu_item import CmsMenuItem

            booking_exists = (
                session.query(CmsMenuItem)
                .filter_by(widget_id=header_nav.id, page_slug="booking")
                .first()
            )
            if not booking_exists:
                existing_count = (
                    session.query(CmsMenuItem)
                    .filter_by(widget_id=header_nav.id)
                    .count()
                )
                session.add(
                    CmsMenuItem(
                        id=uuid4(),
                        widget_id=header_nav.id,
                        label="Booking",
                        page_slug="booking",
                        sort_order=existing_count,
                    )
                )
        except ImportError:
            pass

    session.commit()
    logger.info("[booking] CMS content populated")


def _populate_checkout_page():
    """Seed the checkout-confirmation page BookingRedirect depends on."""
    try:
        from plugins.checkout.populate_db import populate_checkout_cms

        populate_checkout_cms()
    except ImportError:
        logger.info("[booking] checkout plugin not installed — skipping checkout page")


def _populate_email_templates(session):
    """Seed the booking event email templates."""
    try:
        from plugins.email.src.models.email_template import EmailTemplate
    except ImportError:
        logger.info("[booking] Email plugin not installed — skipping templates")
        return

    for tpl_data in BOOKING_EMAIL_TEMPLATES:
        existing = (
            session.query(EmailTemplate)
            .filter_by(event_type=tpl_data["event_type"])
            .first()
        )
        if not existing:
            session.add(
                EmailTemplate(
                    event_type=tpl_data["event_type"],
                    subject=tpl_data["subject"],
                    html_body=tpl_data["html_body"],
                    text_body=tpl_data["text_body"],
                    is_active=tpl_data["is_active"],
                )
            )
    session.commit()
    logger.info("[booking] Email templates populated")


BOOKING_EMAIL_TEMPLATES = [
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
        "event_type": "booking.confirmed",
        "subject": "Payment authorized — {{ resource_name }}",
        "html_body": (
            '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
            '<h1 style="color:#3498db;">Payment authorized</h1>'
            "<p>Hi {{ user_name }},</p>"
            "<p>Your payment for <strong>{{ resource_name }}</strong> has been authorized. Your booking will be confirmed once the service is completed.</p>"
            "<ul><li>Start: {{ start_at }}</li><li>End: {{ end_at }}</li></ul>"
            '<p><a href="{{ booking_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View Booking</a></p>'
            "</body></html>"
        ),
        "text_body": "Hi {{ user_name }},\n\nYour payment for {{ resource_name }} has been authorized.\nStart: {{ start_at }}\nEnd: {{ end_at }}\n\nView: {{ booking_url }}",
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
            '<p><a href="{{ dashboard_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View My Bookings</a></p>'
            "</body></html>"
        ),
        "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} has been cancelled.\n\nView bookings: {{ dashboard_url }}",
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
            '<p><a href="{{ dashboard_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View My Bookings</a></p>'
            "</body></html>"
        ),
        "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} was cancelled.\nReason: {{ reason }}\nA full refund will be issued.\n\nView bookings: {{ dashboard_url }}",
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
            '<p><a href="{{ dashboard_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View My Bookings</a></p>'
            "</body></html>"
        ),
        "text_body": "Hi {{ user_name }},\n\nYour booking for {{ resource_name }} has been completed. Thank you!\n\nView bookings: {{ dashboard_url }}",
        "is_active": True,
    },
    {
        "event_type": "booking.reminder",
        "subject": "Reminder: {{ resource_name }} in {{ hours_until }} hours",
        "html_body": (
            '<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
            '<h1 style="color:#f39c12;">Booking reminder</h1>'
            "<p>Hi {{ user_name }},</p>"
            "<p>Your booking for <strong>{{ resource_name }}</strong> starts in <strong>{{ hours_until }} hours</strong>.</p>"
            "<ul><li>Start: {{ start_at }}</li></ul>"
            '<p><a href="{{ dashboard_url }}" style="background:#3498db;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;">View My Bookings</a></p>'
            "</body></html>"
        ),
        "text_body": "Hi {{ user_name }},\n\nReminder: Your booking for {{ resource_name }} starts in {{ hours_until }} hours.\nStart: {{ start_at }}\n\nView bookings: {{ dashboard_url }}",
        "is_active": True,
    },
]
