"""S131 — booking catalogue list on the catalogue-list wire contract.

The public ``GET /api/v1/booking/resources`` speaks the agnostic
``{items, total, page, per_page, pages}`` envelope (contract §2), carries
``id`` / ``slug`` / ``name`` / ``tags`` per item (§3), and supports the
``q`` / ``type`` / ``category`` / ``tags`` filters plus booking's ``date-range``
availability facet (``availability_from`` / ``availability_to``).
``GET /api/v1/booking/filters`` returns the §4 facet descriptor.
"""
from datetime import date, timedelta
from uuid import uuid4

_FULL_WEEK_SCHEDULE = {
    "schedule": {
        day: [{"start": "00:00", "end": "23:00"}]
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    },
    "lead_time_hours": 0,
    "max_advance_days": 365,
}


def _make_resource(
    db,
    *,
    name,
    slug=None,
    description=None,
    is_active=True,
    schema=None,
    availability=None,
    categories=None,
):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name=name,
        slug=slug or f"res-{uuid4().hex[:8]}",
        description=description,
        price=100.0,
        capacity=1,
        slot_duration_minutes=60,
        is_active=is_active,
        availability=availability or {},
    )
    if schema is not None:
        resource.custom_schema = schema
    if categories:
        resource.categories = list(categories)
    db.session.add(resource)
    db.session.commit()
    return resource


def _make_schema(db, *, name, slug):
    from plugins.booking.booking.models.custom_schema import BookingCustomSchema

    schema = BookingCustomSchema(id=uuid4(), name=name, slug=slug, is_active=True)
    db.session.add(schema)
    db.session.commit()
    return schema


def _make_category(db, *, name, slug):
    from plugins.booking.booking.models.resource_category import (
        BookableResourceCategory,
    )

    category = BookableResourceCategory(
        id=uuid4(), name=name, slug=slug, is_active=True
    )
    db.session.add(category)
    db.session.commit()
    return category


def _set_tags(app, resource, slugs):
    with app.app_context():
        app.container.tags_and_custom_fields().set_tags(
            "booking_resource", resource.id, slugs
        )


def test_list_returns_contract_envelope(db, client):
    resource = _make_resource(db, name="Envelope Room")

    body = client.get("/api/v1/booking/resources").get_json()

    assert set(["items", "total", "page", "per_page", "pages"]).issubset(body)
    assert "resources" not in body
    item = next(entry for entry in body["items"] if entry["slug"] == resource.slug)
    assert item["id"] == str(resource.id)
    assert item["name"] == "Envelope Room"
    assert item["tags"] == []


def test_item_carries_attached_tags(app, db, client):
    resource = _make_resource(db, name="Tagged Room")
    _set_tags(app, resource, ["seaview"])

    body = client.get("/api/v1/booking/resources").get_json()

    item = next(entry for entry in body["items"] if entry["slug"] == resource.slug)
    assert item["tags"] == ["seaview"]


def test_tags_and_filter_intersects(app, db, client):
    both = _make_resource(db, name="Both Room")
    only_one = _make_resource(db, name="One Room")
    _set_tags(app, both, ["seaview", "balcony"])
    _set_tags(app, only_one, ["seaview"])

    body = client.get("/api/v1/booking/resources?tags=seaview,balcony").get_json()

    slugs = {entry["slug"] for entry in body["items"]}
    assert both.slug in slugs
    assert only_one.slug not in slugs
    assert body["total"] == len([s for s in slugs if s == both.slug])


def test_q_filters_by_name(db, client):
    marker = uuid4().hex[:8]
    match = _make_resource(db, name=f"Alpha {marker} Suite")
    _make_resource(db, name=f"Beta {marker} Suite", description="alpha-free")

    body = client.get(f"/api/v1/booking/resources?q=Alpha {marker}").get_json()

    assert body["total"] == 1
    assert body["items"][0]["slug"] == match.slug


def test_type_filter_uses_custom_schema_slug(db, client):
    schema = _make_schema(db, name="Massage", slug=f"massage-{uuid4().hex[:6]}")
    typed = _make_resource(db, name="Massage Room", schema=schema)
    _make_resource(db, name="Plain Room")

    body = client.get(f"/api/v1/booking/resources?type={schema.slug}").get_json()

    assert body["total"] == 1
    assert body["items"][0]["slug"] == typed.slug
    assert body["items"][0]["resource_type"] == schema.slug


def test_category_filter(db, client):
    category = _make_category(db, name="Spa", slug=f"spa-{uuid4().hex[:6]}")
    in_category = _make_resource(db, name="Spa Room", categories=[category])
    _make_resource(db, name="No Category Room")

    body = client.get(f"/api/v1/booking/resources?category={category.slug}").get_json()

    assert body["total"] == 1
    assert body["items"][0]["slug"] == in_category.slug


def test_availability_window_filter(db, client):
    available = _make_resource(db, name="Open Room", availability=_FULL_WEEK_SCHEDULE)
    _make_resource(db, name="Closed Room", availability={})

    window_from = (date.today() + timedelta(days=2)).isoformat()
    window_to = (date.today() + timedelta(days=3)).isoformat()

    body = client.get(
        f"/api/v1/booking/resources?availability_from={window_from}"
        f"&availability_to={window_to}"
    ).get_json()

    slugs = {entry["slug"] for entry in body["items"]}
    assert available.slug in slugs
    assert body["total"] == 1


def test_availability_invalid_date_is_400(db, client):
    resp = client.get("/api/v1/booking/resources?availability_from=not-a-date")

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_pagination_slices_and_counts(db, client):
    marker = uuid4().hex[:8]
    for index in range(3):
        _make_resource(db, name=f"Page {marker} Room {index}")

    page_one = client.get(
        f"/api/v1/booking/resources?q={marker}&per_page=2&page=1"
    ).get_json()
    page_two = client.get(
        f"/api/v1/booking/resources?q={marker}&per_page=2&page=2"
    ).get_json()

    assert page_one["total"] == 3
    assert page_one["pages"] == 2
    assert page_one["per_page"] == 2
    assert len(page_one["items"]) == 2
    assert len(page_two["items"]) == 1


def test_filters_descriptor_shape(client):
    body = client.get("/api/v1/booking/filters").get_json()

    facets = {facet["key"]: facet for facet in body["facets"]}
    assert facets["type"]["control"] == "select"
    assert facets["category"]["control"] == "select"
    assert facets["category"]["options_endpoint"] == "/api/v1/booking/categories"
    assert facets["tags"]["control"] == "chips"
    assert facets["tags"]["and"] is True
    assert facets["availability"]["control"] == "date-range"


def test_tags_options_endpoint_lists_used_tags(app, db, client):
    resource = _make_resource(db, name="Optioned Room")
    _set_tags(app, resource, ["rooftop"])

    body = client.get("/api/v1/booking/tags").get_json()

    slugs = {tag.get("slug") for tag in body["tags"]}
    assert "rooftop" in slugs
