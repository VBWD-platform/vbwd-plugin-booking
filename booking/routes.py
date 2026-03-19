"""Booking plugin routes — public + admin."""
from datetime import date, datetime
from flask import Blueprint, jsonify, request

from vbwd.extensions import db
from vbwd.middleware.auth import require_auth, require_admin

from plugins.booking.booking.repositories.resource_category_repository import (
    ResourceCategoryRepository,
)
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
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


def _availability_service() -> AvailabilityService:
    return AvailabilityService(BookingRepository(db.session))


# ── Public routes (auth required) ─────────────────────────────────────────────


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


@booking_bp.route("/api/v1/booking/bookings", methods=["POST"])
@require_auth
def create_booking():
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

    try:
        booking = _booking_service().create_booking(
            user_id=request.user_id,
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


@booking_bp.route("/api/v1/booking/bookings", methods=["GET"])
@require_auth
def list_user_bookings():
    bookings = _booking_service().get_user_bookings(request.user_id)
    return jsonify({"bookings": [booking.to_dict() for booking in bookings]})


@booking_bp.route("/api/v1/booking/bookings/<booking_id>", methods=["GET"])
@require_auth
def get_booking(booking_id):
    booking = _booking_service().get_booking(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if str(booking.user_id) != str(request.user_id):
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


# ── Admin routes ──────────────────────────────────────────────────────────────


@booking_bp.route("/api/v1/admin/booking/categories", methods=["GET"])
@require_admin
def admin_list_categories():
    categories = _category_repo().find_all(active_only=False)
    return jsonify({"categories": [category.to_dict() for category in categories]})


@booking_bp.route("/api/v1/admin/booking/categories", methods=["POST"])
@require_admin
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


@booking_bp.route("/api/v1/admin/booking/categories/<category_id>", methods=["PUT"])
@require_admin
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
@require_admin
def admin_delete_category(category_id):
    category = _category_repo().find_by_id(category_id)
    if not category:
        return jsonify({"error": "Category not found"}), 404
    _category_repo().delete(category)
    db.session.commit()
    return jsonify({"deleted": True})


@booking_bp.route("/api/v1/admin/booking/resources", methods=["GET"])
@require_admin
def admin_list_resources():
    resources = _resource_repo().find_all(active_only=False)
    return jsonify({"resources": [resource.to_dict() for resource in resources]})


@booking_bp.route("/api/v1/admin/booking/resources", methods=["POST"])
@require_admin
def admin_create_resource():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource()
    resource.name = data["name"]
    resource.slug = data["slug"]
    resource.description = data.get("description")
    resource.resource_type = data["resource_type"]
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
@require_admin
def admin_update_resource(resource_id):
    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    data = request.get_json()
    updatable_fields = [
        "name",
        "slug",
        "description",
        "resource_type",
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
@require_admin
def admin_delete_resource(resource_id):
    resource = _resource_repo().find_by_id(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404
    _resource_repo().delete(resource)
    db.session.commit()
    return jsonify({"deleted": True})


@booking_bp.route("/api/v1/admin/booking/bookings", methods=["GET"])
@require_admin
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
@require_admin
def admin_get_booking(booking_id):
    booking = _booking_service().get_booking(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify(booking.to_dict())


@booking_bp.route("/api/v1/admin/booking/bookings/<booking_id>", methods=["PUT"])
@require_admin
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
@require_admin
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
@require_admin
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
@require_admin
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
@require_admin
def admin_list_export_rules():
    rules = _export_rule_repo().find_all()
    return jsonify({"rules": [rule.to_dict() for rule in rules]})


@booking_bp.route("/api/v1/admin/booking/export-rules", methods=["POST"])
@require_admin
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
@require_admin
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
@require_admin
def admin_delete_export_rule(rule_id):
    rule = _export_rule_repo().find_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Export rule not found"}), 404
    _export_rule_repo().delete(rule)
    db.session.commit()
    return jsonify({"deleted": True})


@booking_bp.route("/api/v1/admin/booking/export-rules/<rule_id>/test", methods=["POST"])
@require_admin
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
