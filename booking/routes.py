"""Booking plugin routes — public + admin."""
import os
from datetime import date, datetime, timedelta
from flask import Blueprint, Response, current_app, jsonify, request, g

from vbwd.extensions import db
from vbwd.middleware.auth import require_auth, require_admin, require_permission

from plugins.booking.booking.repositories.resource_category_repository import (
    ResourceCategoryRepository,
)
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
)
from plugins.booking.booking.repositories.custom_schema_repository import (
    CustomSchemaRepository,
)
from plugins.booking.booking.repositories.booking_repository import (
    BookingRepository,
)
from plugins.booking.booking.services.availability_service import (
    AvailabilityService,
)
from plugins.booking.booking.services.booking_service import (
    BookingService,
    BookingError,
)
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)

booking_bp = Blueprint("booking", __name__)


def _booking_service() -> BookingService:
    from flask import current_app

    return BookingService(
        booking_repository=BookingRepository(db.session),
        resource_repository=ResourceRepository(db.session),
        availability_service=AvailabilityService(BookingRepository(db.session)),
        invoice_service=BookingInvoiceService(db.session),
        event_bus=current_app.extensions.get("event_bus"),
    )


def _resource_repo() -> ResourceRepository:
    return ResourceRepository(db.session)


def _category_repo() -> ResourceCategoryRepository:
    return ResourceCategoryRepository(db.session)


def _schema_repo() -> CustomSchemaRepository:
    return CustomSchemaRepository(db.session)


def _availability_service() -> AvailabilityService:
    return AvailabilityService(BookingRepository(db.session))


# ── Public routes (auth required) ─────────────────────────────────────────────


# User-relevant policy defaults — returned when the plugin instance is
# absent (unreachable in prod, but keeps unit tests deterministic and
# prevents a NoneType crash in a half-booted dev environment).
_PUBLIC_CONFIG_DEFAULTS = {
    "cancellation_grace_period_hours": 24,
    "min_lead_time_hours": 1,
    "max_advance_booking_days": 90,
    "default_slot_duration_minutes": 60,
}


@booking_bp.route("/api/v1/booking/config", methods=["GET"])
def public_booking_config():
    """Return the policy values fe-user needs to gate cancel/reschedule UI.

    Public on purpose — these values are not secrets and every unauthenticated
    catalogue visitor may render against them.
    """
    plugin_manager = getattr(current_app, "plugin_manager", None)
    booking_plugin = (
        plugin_manager.get_plugin("booking") if plugin_manager is not None else None
    )
    if booking_plugin is None:
        return jsonify({"error": "booking plugin not available"}), 503

    return jsonify(
        {
            key: booking_plugin.get_config(key, default)
            for key, default in _PUBLIC_CONFIG_DEFAULTS.items()
        }
    )


@booking_bp.route("/api/v1/booking/categories", methods=["GET"])
def list_categories():
    categories = _category_repo().find_all(active_only=True)
    return jsonify({"categories": [category.to_dict() for category in categories]})


@booking_bp.route("/api/v1/booking/resources", methods=["GET"])
def list_resources():
    category = request.args.get("category")
    resource_type = request.args.get("type")

    repo = _resource_repo()
    if category:
        resources = repo.find_by_category(category)
    elif resource_type:
        resources = repo.find_by_type(resource_type)
    else:
        resources = repo.find_all(active_only=True)

    return jsonify({"resources": [resource.to_dict() for resource in resources]})


@booking_bp.route("/api/v1/booking/resources/<slug>", methods=["GET"])
def get_resource(slug):
    resource = _resource_repo().find_by_slug(slug)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404
    return jsonify(resource.to_dict())


@booking_bp.route("/api/v1/booking/resources/<slug>/availability", methods=["GET"])
def get_availability(slug):
    resource = _resource_repo().find_by_slug(slug)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date parameter required"}), 400

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format (use YYYY-MM-DD)"}), 400

    slots = _availability_service().get_available_slots(resource, target_date)
    return jsonify({"date": date_str, "slots": slots})


@booking_bp.route("/api/v1/booking/checkout", methods=["POST"])
@require_auth
def booking_checkout():
    """Create invoice for a booking — booking is created later on invoice.paid."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    required_fields = ["resource_slug", "start_at", "end_at"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    try:
        start_at = datetime.fromisoformat(data["start_at"])
        end_at = datetime.fromisoformat(data["end_at"])
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    resource = _resource_repo().find_by_slug(data["resource_slug"])
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    if not resource.is_active:
        return jsonify({"error": "Resource is not active"}), 400

    # Check capacity
    booked_count = BookingRepository(db.session).count_by_resource_and_slot(
        resource.id, start_at, end_at
    )
    quantity = data.get("quantity", 1)
    available_capacity = resource.capacity - booked_count
    if quantity > available_capacity:
        return (
            jsonify(
                {
                    "error": (
                        f"Not enough capacity: requested {quantity}, "
                        f"available {available_capacity}"
                    )
                }
            ),
            400,
        )

    invoice = BookingInvoiceService(db.session).create_checkout_invoice(
        user_id=g.user_id,
        resource=resource,
        start_at=start_at,
        end_at=end_at,
        quantity=quantity,
        custom_fields=data.get("custom_fields"),
        notes=data.get("notes"),
    )
    db.session.commit()

    return (
        jsonify(
            {
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
            }
        ),
        201,
    )


_LIST_BOOKINGS_MAX_PER_PAGE = 100
_LIST_BOOKINGS_ALLOWED_STATUSES = {"upcoming", "past", "all"}


@booking_bp.route("/api/v1/booking/bookings", methods=["GET"])
@require_auth
def list_user_bookings():
    """
    List the authenticated user's bookings with optional status filter and
    pagination.

    Query params:
      status   — "upcoming" | "past" | "all"  (default "all")
      page     — 1-indexed page number       (default 1)
      per_page — page size, max 100          (default 20)

    Response: { bookings, page, per_page, total, total_pages }
    """
    status_filter = request.args.get("status", "all")
    if status_filter not in _LIST_BOOKINGS_ALLOWED_STATUSES:
        return (
            jsonify(
                {
                    "error": (
                        "Invalid status filter; expected one of "
                        f"{sorted(_LIST_BOOKINGS_ALLOWED_STATUSES)}"
                    )
                }
            ),
            400,
        )

    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        return jsonify({"error": "page must be an integer"}), 400
    try:
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return jsonify({"error": "per_page must be an integer"}), 400
    per_page = max(1, min(per_page, _LIST_BOOKINGS_MAX_PER_PAGE))

    booking_repo = BookingRepository(db.session)
    bookings, total = booking_repo.find_by_user_paginated(
        user_id=g.user_id,
        status_filter=status_filter,
        page=page,
        per_page=per_page,
    )
    total_pages = (total + per_page - 1) // per_page if per_page else 0

    return jsonify(
        {
            "bookings": [booking.to_dict() for booking in bookings],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "status": status_filter,
        }
    )


@booking_bp.route("/api/v1/booking/bookings/<booking_id>", methods=["GET"])
@require_auth
def get_booking(booking_id):
    booking = _booking_service().get_booking(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if str(booking.user_id) != str(g.user_id):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(booking.to_dict())


@booking_bp.route("/api/v1/booking/bookings/<booking_id>/cancel", methods=["POST"])
@require_auth
def cancel_booking(booking_id):
    try:
        booking = _booking_service().cancel_booking(booking_id, cancelled_by="user")
        db.session.commit()
        return jsonify(booking.to_dict())
    except BookingError as error:
        return jsonify({"error": str(error)}), 400


def _company_context() -> dict:
    config = current_app.config
    return {
        "name": config.get("COMPANY_NAME", "VBWD"),
        "tagline": config.get("COMPANY_TAGLINE", ""),
        "address": config.get("COMPANY_ADDRESS", ""),
        "email": config.get("COMPANY_EMAIL", ""),
        "website": config.get("COMPANY_WEBSITE", ""),
    }


def _format_duration(start_at: datetime, end_at: datetime) -> str:
    total_minutes = int((end_at - start_at).total_seconds() // 60)
    if total_minutes < 60:
        return f"{total_minutes} min"
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}min"


def _build_booking_pdf_context(booking, resource, user, invoice=None) -> dict:
    from decimal import Decimal

    price_display = ""
    if resource and resource.price:
        currency = resource.currency or "EUR"
        price_display = f"{Decimal(str(resource.price)):.2f} {currency}"

    is_paid = False
    invoice_number = None
    if invoice is not None:
        invoice_status = (
            invoice.status.value
            if hasattr(invoice.status, "value")
            else str(invoice.status)
        )
        is_paid = invoice_status == "paid"
        invoice_number = getattr(invoice, "invoice_number", None)

    booking_status = (
        booking.status.value
        if hasattr(booking.status, "value")
        else str(booking.status)
    )

    customer_name = ""
    customer_phone = ""
    customer_company = ""
    details = getattr(user, "details", None) if user else None
    if details is not None:
        first_name = getattr(details, "first_name", "") or ""
        last_name = getattr(details, "last_name", "") or ""
        customer_name = (first_name + " " + last_name).strip()
        customer_phone = getattr(details, "phone", "") or ""
        customer_company = getattr(details, "company", "") or ""

    return {
        "company": _company_context(),
        "resource": {
            "name": resource.name if resource else "",
            "description": getattr(resource, "description", "") or ""
            if resource
            else "",
            "location": getattr(resource, "location", "") or "" if resource else "",
        },
        "customer": {
            "name": customer_name,
            "email": getattr(user, "email", "") or "",
            "phone": customer_phone,
            "company": customer_company,
        },
        "booking": {
            "id": str(booking.id),
            "short_id": str(booking.id)[:8],
            "status": booking_status,
            "created_at_display": booking.created_at.strftime("%Y-%m-%d")
            if booking.created_at
            else "",
            "start_date_display": booking.start_at.strftime("%Y-%m-%d"),
            "start_time_display": booking.start_at.strftime("%H:%M"),
            "end_time_display": booking.end_at.strftime("%H:%M"),
            "duration_display": _format_duration(booking.start_at, booking.end_at),
            "quantity": booking.quantity,
            "price_display": price_display,
            "custom_fields": booking.custom_fields or {},
            "notes": booking.notes or "",
            "is_paid": is_paid,
            "invoice_number": invoice_number,
        },
    }


def _load_booking_for_download(booking_id):
    """Shared guard for PDF + iCal endpoints: 404 if missing, 403 if not owner.

    Returns a (booking, user, response_or_none) triple where response_or_none
    is set when the handler should short-circuit with that response.
    """
    service = _booking_service()
    booking = service.get_booking(booking_id)
    if not booking:
        return None, None, (jsonify({"error": "Booking not found"}), 404)
    if str(booking.user_id) != str(g.user_id):
        return None, None, (jsonify({"error": "Forbidden"}), 403)

    from vbwd.repositories.user_repository import UserRepository

    user = UserRepository(db.session).find_by_id(str(booking.user_id))
    return booking, user, None


@booking_bp.route("/api/v1/booking/bookings/<booking_id>/pdf", methods=["GET"])
@require_auth
def download_booking_pdf(booking_id):
    """Stream a PDF rendering of the booking (owner-only)."""
    booking, user, short_circuit = _load_booking_for_download(booking_id)
    if short_circuit is not None:
        return short_circuit

    resource = ResourceRepository(db.session).find_by_id(booking.resource_id)

    invoice = None
    if booking.invoice_id:
        from vbwd.repositories.invoice_repository import InvoiceRepository

        invoice = InvoiceRepository(db.session).find_by_id(str(booking.invoice_id))

    pdf_service = current_app.container.pdf_service()  # type: ignore[attr-defined]

    # Self-heal: if the plugin's on_enable didn't run (tests bypass it), make
    # sure the template path is registered before we ask for the template.
    template_dir = os.path.join(os.path.dirname(__file__), "templates", "pdf")
    pdf_service.register_plugin_template_path(template_dir)

    context = _build_booking_pdf_context(booking, resource, user, invoice)
    pdf_bytes = pdf_service.render("booking.html", context)

    filename = f"booking-{str(booking.id)[:8]}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@booking_bp.route("/api/v1/booking/bookings/<booking_id>/ical", methods=["GET"])
@require_auth
def download_booking_ical(booking_id):
    """Return a VCALENDAR (.ics) entry for the booking (owner-only)."""
    booking, _, short_circuit = _load_booking_for_download(booking_id)
    if short_circuit is not None:
        return short_circuit

    resource = ResourceRepository(db.session).find_by_id(booking.resource_id)
    ics_text = _build_booking_ical(booking, resource)

    filename = f"booking-{str(booking.id)[:8]}.ics"
    return Response(
        ics_text,
        mimetype="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _ical_escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11 TEXT rules."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ical_timestamp(value: datetime) -> str:
    """Format as UTC floating-free timestamp (YYYYMMDDTHHMMSSZ).

    We treat DB values as UTC (the codebase's convention). Downstream
    calendars render in the user's local tz.
    """
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y%m%dT%H%M%SZ")


def _build_booking_ical(booking, resource) -> str:
    """Minimal VCALENDAR with METHOD:PUBLISH and one VEVENT.

    SEQUENCE is derived from booking.version (if BaseModel exposes it),
    so every reschedule bumps the sequence and mature calendar clients
    (Google, Apple) replace the existing entry instead of duplicating.
    """
    company = _company_context()
    organizer_mailto = company.get("email") or "support@example.com"
    organizer_cn = company.get("name") or "VBWD"

    now_utc = datetime.utcnow()
    sequence = getattr(booking, "version", 0) or 0

    booking_status = (
        booking.status.value
        if hasattr(booking.status, "value")
        else str(booking.status)
    )
    ical_status_map = {
        "pending": "TENTATIVE",
        "confirmed": "CONFIRMED",
        "cancelled": "CANCELLED",
        "completed": "CONFIRMED",
    }
    ical_status = ical_status_map.get(booking_status, "CONFIRMED")

    summary = resource.name if resource else "Booking"
    description = getattr(resource, "description", "") if resource else ""
    if booking.notes:
        description = f"{description}\n\n{booking.notes}".strip()

    location = getattr(resource, "location", "") if resource else ""

    host = request.host or "vbwd.local"
    uid = f"{booking.id}@{host}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//vbwd//booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_ical_timestamp(now_utc)}",
        f"DTSTART:{_ical_timestamp(booking.start_at)}",
        f"DTEND:{_ical_timestamp(booking.end_at)}",
        f"SUMMARY:{_ical_escape(summary)}",
        f"DESCRIPTION:{_ical_escape(description)}",
    ]
    if location:
        lines.append(f"LOCATION:{_ical_escape(location)}")
    lines += [
        f"ORGANIZER;CN={_ical_escape(organizer_cn)}:mailto:{organizer_mailto}",
        f"STATUS:{ical_status}",
        f"SEQUENCE:{sequence}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


@booking_bp.route("/api/v1/booking/bookings/<booking_id>", methods=["PATCH"])
@require_auth
def reschedule_booking_route(booking_id):
    """
    Reschedule an upcoming booking in-place.

    Body: { start_at: ISO8601, end_at: ISO8601 }
    Returns:
      200 { booking }          on success
      400 { error }            validation failure (grace period, capacity, status...)
      403 { error }            non-owner
      404 { error }            booking not found
    """
    data = request.get_json(silent=True) or {}
    if "start_at" not in data or "end_at" not in data:
        return jsonify({"error": "start_at and end_at are required"}), 400

    try:
        new_start_at = datetime.fromisoformat(data["start_at"])
        new_end_at = datetime.fromisoformat(data["end_at"])
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    # Short-circuit ownership check so we can return 403 (vs service's 400).
    service = _booking_service()
    existing_booking = service.get_booking(booking_id)
    if not existing_booking:
        return jsonify({"error": "Booking not found"}), 404
    if str(existing_booking.user_id) != str(g.user_id):
        return jsonify({"error": "Forbidden"}), 403

    # Resolve policy values from the booking plugin's config.
    plugin_manager = getattr(current_app, "plugin_manager", None)
    booking_plugin = (
        plugin_manager.get_plugin("booking") if plugin_manager is not None else None
    )
    if booking_plugin is None:
        return jsonify({"error": "booking plugin not available"}), 503

    cancellation_grace_period_hours = booking_plugin.get_config(
        "cancellation_grace_period_hours", 24
    )
    min_lead_time_hours = booking_plugin.get_config("min_lead_time_hours", 1)

    try:
        booking = service.reschedule_booking(
            booking_id=booking_id,
            user_id=g.user_id,
            new_start_at=new_start_at,
            new_end_at=new_end_at,
            cancellation_grace_period_hours=cancellation_grace_period_hours,
            min_lead_time_hours=min_lead_time_hours,
        )
        db.session.commit()
        return jsonify(booking.to_dict())
    except BookingError as error:
        db.session.rollback()
        message = str(error)
        # Full-capacity rejection → 409 (standard for conflict).
        if "capacity" in message.lower() or "unavailable" in message.lower():
            return jsonify({"error": message}), 409
        return jsonify({"error": message}), 400


# ── Admin routes ──────────────────────────────────────────────────────────────


@booking_bp.route("/api/v1/admin/booking/bookings", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.bookings.manage")
def admin_create_booking():
    """Admin-only: create a booking directly (bypasses checkout/payment)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    required_fields = ["resource_slug", "start_at", "end_at", "user_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    try:
        start_at = datetime.fromisoformat(data["start_at"])
        end_at = datetime.fromisoformat(data["end_at"])
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    try:
        booking = _booking_service().create_booking(
            user_id=data["user_id"],
            resource_slug=data["resource_slug"],
            start_at=start_at,
            end_at=end_at,
            quantity=data.get("quantity", 1),
            custom_fields=data.get("custom_fields"),
            notes=data.get("notes"),
        )
        db.session.commit()
        return jsonify(booking.to_dict()), 201
    except BookingError as error:
        return jsonify({"error": str(error)}), 400


@booking_bp.route("/api/v1/admin/booking/categories", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_list_categories():
    categories = _category_repo().find_all(active_only=False)
    return jsonify({"categories": [category.to_dict() for category in categories]})


@booking_bp.route("/api/v1/admin/booking/categories", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_create_category():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("slug"):
        return jsonify({"error": "name and slug required"}), 400

    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )

    category = BookableResourceCategory()
    category.name = data["name"]
    category.slug = data["slug"]
    category.description = data.get("description")
    category.image_url = data.get("image_url")
    category.parent_id = data.get("parent_id")
    category.config = data.get("config", {})
    category.sort_order = data.get("sort_order", 0)
    category.is_active = data.get("is_active", True)

    _category_repo().save(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@booking_bp.route("/api/v1/admin/booking/categories/<category_id>", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_get_category(category_id):
    category = _category_repo().find_by_id(category_id)
    if not category:
        return jsonify({"error": "Category not found"}), 404
    return jsonify(category.to_dict())


@booking_bp.route("/api/v1/admin/booking/categories/<category_id>", methods=["PUT"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_update_category(category_id):
    category = _category_repo().find_by_id(category_id)
    if not category:
        return jsonify({"error": "Category not found"}), 404

    data = request.get_json()
    for field in [
        "name",
        "slug",
        "description",
        "image_url",
        "parent_id",
        "config",
        "sort_order",
        "is_active",
    ]:
        if field in data:
            setattr(category, field, data[field])

    db.session.commit()
    return jsonify(category.to_dict())


@booking_bp.route("/api/v1/admin/booking/categories/<category_id>", methods=["DELETE"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_delete_category(category_id):
    category = _category_repo().find_by_id(category_id)
    if not category:
        return jsonify({"error": "Category not found"}), 404
    _category_repo().delete(category)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Schema admin routes ───────────────────────────────────────────────────────


@booking_bp.route("/api/v1/admin/booking/schemas", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_list_schemas():
    schemas = _schema_repo().find_all(active_only=False)
    return jsonify({"schemas": [schema.to_dict() for schema in schemas]})


@booking_bp.route("/api/v1/admin/booking/schemas", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_create_schema():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("slug"):
        return jsonify({"error": "name and slug required"}), 400

    from plugins.booking.booking.models.custom_schema import BookingCustomSchema

    schema = BookingCustomSchema()
    schema.name = data["name"]
    schema.slug = data["slug"]
    schema.fields = data.get("fields", [])
    schema.sort_order = data.get("sort_order", 0)
    schema.is_active = data.get("is_active", True)

    _schema_repo().save(schema)
    db.session.commit()
    return jsonify(schema.to_dict()), 201


@booking_bp.route("/api/v1/admin/booking/schemas/<schema_id>", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_get_schema(schema_id):
    schema = _schema_repo().find_by_id(schema_id)
    if not schema:
        return jsonify({"error": "Schema not found"}), 404
    return jsonify(schema.to_dict())


@booking_bp.route("/api/v1/admin/booking/schemas/<schema_id>", methods=["PUT"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_update_schema(schema_id):
    schema = _schema_repo().find_by_id(schema_id)
    if not schema:
        return jsonify({"error": "Schema not found"}), 404

    data = request.get_json()
    for field in ["name", "slug", "fields", "sort_order", "is_active"]:
        if field in data:
            setattr(schema, field, data[field])

    db.session.commit()
    return jsonify(schema.to_dict())


@booking_bp.route("/api/v1/admin/booking/schemas/<schema_id>", methods=["DELETE"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_delete_schema(schema_id):
    schema = _schema_repo().find_by_id(schema_id)
    if not schema:
        return jsonify({"error": "Schema not found"}), 404
    _schema_repo().delete(schema)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Public schemas route ─────────────────────────────────────────────────────


@booking_bp.route("/api/v1/booking/schemas", methods=["GET"])
def list_schemas():
    schemas = _schema_repo().find_all(active_only=True)
    return jsonify({"schemas": [schema.to_dict() for schema in schemas]})


@booking_bp.route("/api/v1/admin/booking/resources", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_list_resources():
    resources = _resource_repo().find_all(active_only=False)
    return jsonify({"resources": [resource.to_dict() for resource in resources]})


@booking_bp.route("/api/v1/admin/booking/resources/<resource_id>", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_get_resource(resource_id):
    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404
    return jsonify(resource.to_dict())


@booking_bp.route("/api/v1/admin/booking/resources", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_create_resource():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource()
    resource.name = data["name"]
    resource.slug = data["slug"]
    resource.description = data.get("description")
    resource.custom_schema_id = data.get("custom_schema_id")
    resource.capacity = data.get("capacity", 1)
    resource.slot_duration_minutes = data.get("slot_duration_minutes")
    resource.price = data["price"]
    resource.currency = data.get("currency", "EUR")
    resource.price_unit = data.get("price_unit", "per_slot")
    resource.availability = data.get("availability", {})
    resource.custom_fields_schema = data.get("custom_fields_schema")
    resource.image_url = data.get("image_url")
    resource.config = data.get("config", {})
    resource.is_active = data.get("is_active", True)
    resource.sort_order = data.get("sort_order", 0)

    # Attach categories
    category_ids = data.get("category_ids", [])
    if category_ids:
        for category_id in category_ids:
            category = _category_repo().find_by_id(category_id)
            if category:
                resource.categories.append(category)

    _resource_repo().save(resource)
    db.session.commit()
    return jsonify(resource.to_dict()), 201


@booking_bp.route("/api/v1/admin/booking/resources/<resource_id>", methods=["PUT"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_update_resource(resource_id):
    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    data = request.get_json()
    updatable_fields = [
        "name",
        "slug",
        "description",
        "custom_schema_id",
        "capacity",
        "slot_duration_minutes",
        "price",
        "currency",
        "price_unit",
        "availability",
        "custom_fields_schema",
        "image_url",
        "config",
        "is_active",
        "sort_order",
    ]
    for field in updatable_fields:
        if field in data:
            setattr(resource, field, data[field])

    db.session.commit()
    return jsonify(resource.to_dict())


@booking_bp.route("/api/v1/admin/booking/resources/<resource_id>", methods=["DELETE"])
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_delete_resource(resource_id):
    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404
    _resource_repo().delete(resource)
    db.session.commit()
    return jsonify({"deleted": True})


@booking_bp.route("/api/v1/admin/booking/bookings", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.bookings.view")
def admin_list_bookings():
    from plugins.booking.booking.models.booking import Booking

    query = db.session.query(Booking)

    status = request.args.get("status")
    if status:
        query = query.filter(Booking.status == status)

    resource_id = request.args.get("resource_id")
    if resource_id:
        query = query.filter(Booking.resource_id == resource_id)

    bookings = query.order_by(Booking.start_at.desc()).all()
    return jsonify({"bookings": [booking.to_dict() for booking in bookings]})


@booking_bp.route("/api/v1/admin/booking/bookings/<booking_id>", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.bookings.view")
def admin_get_booking(booking_id):
    booking = _booking_service().get_booking(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify(booking.to_dict())


@booking_bp.route("/api/v1/admin/booking/bookings/<booking_id>", methods=["PUT"])
@require_auth
@require_admin
@require_permission("booking.bookings.manage")
def admin_update_booking(booking_id):
    booking = _booking_service().get_booking(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    data = request.get_json()
    if "status" in data:
        booking.status = data["status"]
    if "admin_notes" in data:
        booking.admin_notes = data["admin_notes"]

    db.session.commit()
    return jsonify(booking.to_dict())


@booking_bp.route("/api/v1/admin/booking/dashboard", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.bookings.view")
def admin_dashboard():
    from plugins.booking.booking.models.booking import Booking
    from sqlalchemy import func

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    today_count = (
        db.session.query(func.count(Booking.id))
        .filter(Booking.start_at >= today_start, Booking.start_at <= today_end)
        .scalar()
    )

    upcoming_count = (
        db.session.query(func.count(Booking.id))
        .filter(
            Booking.start_at > today_end,
            Booking.status.in_(["confirmed", "pending"]),
        )
        .scalar()
    )

    return jsonify(
        {
            "today": today_count,
            "upcoming": upcoming_count,
        }
    )


# ── Export / Import routes ────────────────────────────────────────────────────


def _export_service():
    from plugins.booking.booking.services.export_service import ExportService

    return ExportService(
        category_repository=ResourceCategoryRepository(db.session),
        resource_repository=ResourceRepository(db.session),
        booking_repository=BookingRepository(db.session),
    )


def _import_service():
    from plugins.booking.booking.services.import_service import ImportService

    return ImportService(
        category_repository=ResourceCategoryRepository(db.session),
        resource_repository=ResourceRepository(db.session),
    )


def _export_rule_repo():
    from plugins.booking.booking.repositories.export_rule_repository import (
        ExportRuleRepository,
    )

    return ExportRuleRepository(db.session)


@booking_bp.route("/api/v1/admin/booking/export/<entity>", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_export(entity):
    export_format = request.args.get("format", "csv")
    service = _export_service()

    if entity == "categories":
        data = service.export_categories(export_format)
    elif entity == "resources":
        data = service.export_resources(export_format)
    elif entity == "bookings":
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        status = request.args.get("status")
        data = service.export_bookings(
            export_format,
            date.fromisoformat(date_from) if date_from else None,
            date.fromisoformat(date_to) if date_to else None,
            status,
        )
    else:
        return jsonify({"error": f"Unknown entity: {entity}"}), 400

    content_type = "application/json" if export_format == "json" else "text/csv"
    ext = "json" if export_format == "json" else "csv"
    filename = f"{entity}_{date.today().isoformat()}.{ext}"

    return (
        data,
        200,
        {
            "Content-Type": content_type,
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@booking_bp.route("/api/v1/admin/booking/import/<entity>", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_import(entity):
    if "file" not in request.files:
        return jsonify({"error": "file upload required"}), 400

    uploaded_file = request.files["file"]
    file_content = uploaded_file.read().decode("utf-8")
    import_format = "json" if uploaded_file.filename.endswith(".json") else "csv"

    service = _import_service()
    if entity == "categories":
        result = service.import_categories(file_content, import_format)
    elif entity == "resources":
        result = service.import_resources(file_content, import_format)
    else:
        return jsonify({"error": f"Import not supported for: {entity}"}), 400

    db.session.commit()
    return jsonify(result)


# ── Export Rules CRUD ─────────────────────────────────────────────────────────


@booking_bp.route("/api/v1/admin/booking/export-rules", methods=["GET"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_list_export_rules():
    rules = _export_rule_repo().find_all()
    return jsonify({"rules": [rule.to_dict() for rule in rules]})


@booking_bp.route("/api/v1/admin/booking/export-rules", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_create_export_rule():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    from plugins.booking.booking.models.export_rule import BookingExportRule

    rule = BookingExportRule()
    rule.name = data["name"]
    rule.trigger_type = data["trigger_type"]
    rule.event_type = data.get("event_type")
    rule.cron_expression = data.get("cron_expression")
    rule.cron_export_scope = data.get("cron_export_scope")
    rule.cron_entity = data.get("cron_entity")
    rule.cron_status_filter = data.get("cron_status_filter")
    rule.export_type = data["export_type"]
    rule.config = data.get("config", {})
    rule.is_active = data.get("is_active", True)

    _export_rule_repo().save(rule)
    db.session.commit()
    return jsonify(rule.to_dict()), 201


@booking_bp.route("/api/v1/admin/booking/export-rules/<rule_id>", methods=["PUT"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_update_export_rule(rule_id):
    rule = _export_rule_repo().find_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Export rule not found"}), 404

    data = request.get_json()
    for field in [
        "name",
        "trigger_type",
        "event_type",
        "cron_expression",
        "cron_export_scope",
        "cron_entity",
        "cron_status_filter",
        "export_type",
        "config",
        "is_active",
    ]:
        if field in data:
            setattr(rule, field, data[field])

    db.session.commit()
    return jsonify(rule.to_dict())


@booking_bp.route("/api/v1/admin/booking/export-rules/<rule_id>", methods=["DELETE"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_delete_export_rule(rule_id):
    rule = _export_rule_repo().find_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Export rule not found"}), 404
    _export_rule_repo().delete(rule)
    db.session.commit()
    return jsonify({"deleted": True})


@booking_bp.route("/api/v1/admin/booking/export-rules/<rule_id>/test", methods=["POST"])
@require_auth
@require_admin
@require_permission("booking.configure")
def admin_test_export_rule(rule_id):
    rule = _export_rule_repo().find_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Export rule not found"}), 404

    from plugins.booking.booking.services.export_rule_service import (
        ExportRuleService,
    )

    sample_data = {
        "event": rule.event_type or "booking.test",
        "timestamp": datetime.utcnow().isoformat(),
        "booking_id": "test-booking-id",
        "resource_name": "Test Resource",
        "user_email": "test@example.com",
        "start_at": datetime.utcnow().isoformat(),
        "amount": "50.00",
        "status": "confirmed",
    }

    service = ExportRuleService(_export_rule_repo())
    service.execute_rule(rule, sample_data)
    db.session.commit()

    return jsonify(
        {
            "tested": True,
            "last_status": rule.last_status,
            "last_error": rule.last_error,
        }
    )


# ── Resource Image Gallery routes ────────────────────────────────────────────


def _cms_available():
    try:
        from plugins.cms.src.models.cms_image import CmsImage  # noqa: F401

        return True
    except ImportError:
        return False


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/images", methods=["GET"]
)
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_list_resource_images(resource_id):
    if not _cms_available():
        return jsonify({"error": "CMS plugin required for image gallery"}), 501

    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    images = (
        db.session.query(BookableResourceImage)
        .filter_by(resource_id=resource_id)
        .order_by(BookableResourceImage.sort_order)
        .all()
    )
    return jsonify({"images": [img.to_dict() for img in images]})


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/images", methods=["POST"]
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_upload_resource_image(resource_id):
    if not _cms_available():
        return jsonify({"error": "CMS plugin required for image gallery"}), 501

    if "file" not in request.files:
        return jsonify({"error": "file upload required"}), 400

    uploaded_file = request.files["file"]
    file_data = uploaded_file.read()
    filename = uploaded_file.filename or "image.jpg"
    mime_type = uploaded_file.content_type or "image/jpeg"

    from plugins.cms.src.services.cms_image_service import CmsImageService
    from plugins.cms.src.repositories.cms_image_repository import (
        CmsImageRepository,
    )
    from plugins.cms.src.services.file_storage import LocalFileStorage
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    image_repo = CmsImageRepository(db.session)
    storage = LocalFileStorage(
        base_path="/app/uploads",
        base_url="/uploads",
    )
    cms_service = CmsImageService(image_repo, storage)

    cms_image_data = cms_service.upload_image(file_data, filename, mime_type)

    # Count existing images for sort_order
    existing_count = (
        db.session.query(BookableResourceImage)
        .filter_by(resource_id=resource_id)
        .count()
    )

    resource_image = BookableResourceImage()
    resource_image.resource_id = resource_id
    resource_image.cms_image_id = cms_image_data["id"]
    resource_image.is_primary = existing_count == 0  # First image is primary
    resource_image.sort_order = existing_count

    db.session.add(resource_image)
    db.session.commit()
    return jsonify(resource_image.to_dict()), 201


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/images/<image_id>/primary",
    methods=["POST"],
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_set_primary_image(resource_id, image_id):
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    # Clear all primary flags for this resource
    db.session.query(BookableResourceImage).filter_by(resource_id=resource_id).update(
        {"is_primary": False}
    )

    # Set the target image as primary
    target = (
        db.session.query(BookableResourceImage)
        .filter_by(id=image_id, resource_id=resource_id)
        .first()
    )
    if not target:
        return jsonify({"error": "Image not found"}), 404

    target.is_primary = True
    db.session.commit()
    return jsonify(target.to_dict())


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/images/reorder",
    methods=["POST"],
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_reorder_resource_images(resource_id):
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    data = request.get_json()
    if not data or "order" not in data:
        return jsonify({"error": "order array required"}), 400

    for index, image_id in enumerate(data["order"]):
        db.session.query(BookableResourceImage).filter_by(
            id=image_id, resource_id=resource_id
        ).update({"sort_order": index})

    db.session.commit()
    return jsonify({"reordered": True})


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/images/<image_id>",
    methods=["DELETE"],
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_delete_resource_image(resource_id, image_id):
    from plugins.booking.booking.models.resource_image import (
        BookableResourceImage,
    )

    target = (
        db.session.query(BookableResourceImage)
        .filter_by(id=image_id, resource_id=resource_id)
        .first()
    )
    if not target:
        return jsonify({"error": "Image not found"}), 404

    was_primary = target.is_primary
    db.session.delete(target)
    db.session.flush()

    # If deleted image was primary, promote the first remaining image
    if was_primary:
        first = (
            db.session.query(BookableResourceImage)
            .filter_by(resource_id=resource_id)
            .order_by(BookableResourceImage.sort_order)
            .first()
        )
        if first:
            first.is_primary = True

    db.session.commit()
    return jsonify({"deleted": True})


# ── Schedule & Slot Block routes ─────────────────────────────────────────────


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/schedule", methods=["GET"]
)
@require_auth
@require_admin
@require_permission("booking.resources.view")
def admin_get_schedule(resource_id):
    """Get schedule for a date range: generated slots + bookings + blocks."""
    from plugins.booking.booking.models.slot_block import (
        BookableResourceSlotBlock,
    )
    from plugins.booking.booking.models.booking import Booking

    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    date_from_str = request.args.get("date_from", date.today().isoformat())
    date_to_str = request.args.get(
        "date_to", (date.today() + timedelta(days=6)).isoformat()
    )
    date_from_val = date.fromisoformat(date_from_str)
    date_to_val = date.fromisoformat(date_to_str)

    availability = resource.availability or {}
    schedule = availability.get("schedule", {})
    exceptions = availability.get("exceptions", [])
    config = resource.config or {}
    buffer_minutes = config.get("buffer_minutes", 0)
    slot_duration = resource.slot_duration_minutes

    # Load bookings for the range
    bookings = (
        db.session.query(Booking)
        .filter(
            Booking.resource_id == resource_id,
            Booking.start_at >= datetime.combine(date_from_val, datetime.min.time()),
            Booking.start_at <= datetime.combine(date_to_val, datetime.max.time()),
            Booking.status.in_(["confirmed", "pending"]),
        )
        .all()
    )

    # Load blocks for the range
    blocks = (
        db.session.query(BookableResourceSlotBlock)
        .filter(
            BookableResourceSlotBlock.resource_id == resource_id,
            BookableResourceSlotBlock.date >= date_from_val,
            BookableResourceSlotBlock.date <= date_to_val,
        )
        .all()
    )

    weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = []
    current_date = date_from_val

    while current_date <= date_to_val:
        date_str = current_date.isoformat()
        weekday_name = weekday_names[current_date.weekday()]

        # Check exceptions
        is_closed = False
        exception_slots = None
        for exc in exceptions:
            if exc.get("date") == date_str:
                if exc.get("closed"):
                    is_closed = True
                elif "slots" in exc:
                    exception_slots = exc["slots"]
                break

        if is_closed:
            days.append({"date": date_str, "closed": True, "slots": []})
            current_date += timedelta(days=1)
            continue

        time_windows = exception_slots or schedule.get(weekday_name, [])

        if not time_windows or slot_duration is None:
            days.append(
                {
                    "date": date_str,
                    "closed": not time_windows,
                    "slots": [],
                }
            )
            current_date += timedelta(days=1)
            continue

        # Generate all slots for this day
        day_bookings = [b for b in bookings if b.start_at.date() == current_date]
        day_blocks = [b for b in blocks if b.date == current_date]

        day_slots = []
        slot_td = timedelta(minutes=slot_duration)
        buffer_td = timedelta(minutes=buffer_minutes)

        for window in time_windows:
            w_start = datetime.strptime(window["start"], "%H:%M").time()
            w_end = datetime.combine(
                current_date, datetime.strptime(window["end"], "%H:%M").time()
            )
            current_dt = datetime.combine(current_date, w_start)

            while current_dt + slot_td <= w_end:
                slot_end_dt = current_dt + slot_td
                start_str = current_dt.strftime("%H:%M")
                end_str = slot_end_dt.strftime("%H:%M")

                # Check if booked (overlap: booking overlaps this slot)
                booking_match = next(
                    (
                        b
                        for b in day_bookings
                        if b.start_at < slot_end_dt and b.end_at > current_dt
                    ),
                    None,
                )

                # Check if blocked
                block_match = next(
                    (b for b in day_blocks if b.start_time == start_str),
                    None,
                )

                if booking_match:
                    # Resolve customer name from user_details
                    from vbwd.models.user import User
                    from vbwd.models.user_details import UserDetails

                    booked_user = db.session.get(User, booking_match.user_id)
                    details = (
                        (
                            db.session.query(UserDetails)
                            .filter_by(user_id=booking_match.user_id)
                            .first()
                        )
                        if booked_user
                        else None
                    )
                    if details and details.first_name:
                        customer_name = (
                            f"{details.first_name} {details.last_name or ''}".strip()
                        )
                    elif booked_user:
                        customer_name = booked_user.email
                    else:
                        customer_name = "Unknown"
                    slot_info = {
                        "start": start_str,
                        "end": end_str,
                        "status": "booked",
                        "booking_id": str(booking_match.id),
                        "booking_status": booking_match.status,
                        "customer_name": customer_name,
                    }
                elif block_match:
                    slot_info = {
                        "start": start_str,
                        "end": end_str,
                        "status": "blocked",
                        "block_id": str(block_match.id),
                        "reason": block_match.reason,
                    }
                else:
                    slot_info = {
                        "start": start_str,
                        "end": end_str,
                        "status": "available",
                    }

                day_slots.append(slot_info)
                current_dt += slot_td + buffer_td

        days.append({"date": date_str, "closed": False, "slots": day_slots})
        current_date += timedelta(days=1)

    return jsonify(
        {
            "resource_id": resource_id,
            "date_from": date_from_str,
            "date_to": date_to_str,
            "days": days,
        }
    )


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/block-slot", methods=["POST"]
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_block_slot(resource_id):
    from plugins.booking.booking.models.slot_block import (
        BookableResourceSlotBlock,
    )

    data = request.get_json()
    if not data or not data.get("date") or not data.get("start") or not data.get("end"):
        return jsonify({"error": "date, start, end required"}), 400

    block = BookableResourceSlotBlock()
    block.resource_id = resource_id
    block.date = date.fromisoformat(data["date"])
    block.start_time = data["start"]
    block.end_time = data["end"]
    block.reason = data.get("reason")
    block.blocked_by = g.user_id

    db.session.add(block)
    db.session.commit()
    return jsonify(block.to_dict()), 201


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/block-slot/<block_id>",
    methods=["DELETE"],
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_unblock_slot(resource_id, block_id):
    from plugins.booking.booking.models.slot_block import (
        BookableResourceSlotBlock,
    )

    block = (
        db.session.query(BookableResourceSlotBlock)
        .filter_by(id=block_id, resource_id=resource_id)
        .first()
    )
    if not block:
        return jsonify({"error": "Block not found"}), 404

    db.session.delete(block)
    db.session.commit()
    return jsonify({"unblocked": True})


@booking_bp.route(
    "/api/v1/admin/booking/resources/<resource_id>/copy-schedule",
    methods=["POST"],
)
@require_auth
@require_admin
@require_permission("booking.resources.manage")
def admin_copy_schedule(resource_id):
    source = _resource_repo().find_by_id(resource_id)
    if not source:
        return jsonify({"error": "Source resource not found"}), 404

    data = request.get_json()
    target_ids = data.get("target_resource_ids", [])
    if not target_ids:
        return jsonify({"error": "target_resource_ids required"}), 400

    copied = 0
    for target_id in target_ids:
        target = _resource_repo().find_by_id(target_id)
        if target and str(target.id) != str(source.id):
            target.availability = source.availability
            target.config = {
                **(target.config or {}),
                "buffer_minutes": (source.config or {}).get("buffer_minutes", 0),
            }
            copied += 1

    db.session.commit()
    return jsonify({"copied": copied})
