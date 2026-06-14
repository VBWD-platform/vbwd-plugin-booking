"""S77 — booking registers booking_resource and appends tags + custom fields.

The public resource detail (``GET /api/v1/booking/resources/<slug>``) appends
``tags`` / ``custom_fields`` (+ ``custom_field_defs``) via the core helper — no
model import, no extra round trip. The resource edit page + resource detail read
those keys.
"""
from uuid import uuid4

from vbwd.services.entity_type_registry import get_entity_type, is_registered


def test_booking_resource_entity_type_registered(app):
    assert is_registered("booking_resource")
    registration = get_entity_type("booking_resource")
    assert registration is not None
    assert registration.manage_permission == "booking.resources.manage"


def _make_resource(db):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Room A",
        slug=f"room-{uuid4().hex[:8]}",
        price=100.0,
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def test_resource_detail_appends_empty_tags_and_custom_fields(db, client):
    resource = _make_resource(db)

    body = client.get(f"/api/v1/booking/resources/{resource.slug}").get_json()

    assert body["tags"] == []
    assert body["custom_fields"] == {}
    assert "custom_field_defs" in body


def test_resource_detail_appends_attached_tags(app, db, client):
    resource = _make_resource(db)

    with app.app_context():
        app.container.tags_and_custom_fields().set_tags(
            "booking_resource", resource.id, ["seaview"]
        )

    body = client.get(f"/api/v1/booking/resources/{resource.slug}").get_json()

    assert body["tags"] == ["seaview"]
