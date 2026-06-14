"""S72.4 follow-up — the public resource LIST exposes the same ``pricing`` block
as the detail route (integration).

Contract (mirrors the shop sibling ``test_product_list_pricing``):
- ``GET /booking/resources`` returns ``{"resources": [...]}`` where each resource
  carries a ``pricing`` block identical in shape/values to the detail route's block
  for the same resource (net/gross + ``effective_display_mode`` +
  ``prices_display_mode``).
- The detail route is unchanged (characterization: the block it returns equals the
  one now produced by the shared helper).
- A resource with a ``netto`` override surfaces ``effective_display_mode == "netto"``
  in the LIST too.
"""
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def _make_resource(db, price_display_mode=None):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="ListRoom",
        slug=f"list-room-{uuid4().hex[:8]}",
        price=Decimal("100.00"),
        is_active=True,
        price_display_mode=price_display_mode,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def test_list_resources_each_item_has_pricing_block(db, client):
    resource = _make_resource(db, price_display_mode=None)

    resp = client.get("/api/v1/booking/resources")

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "resources" in body
    listed = next(r for r in body["resources"] if r["slug"] == resource.slug)
    pricing = listed["pricing"]
    assert pricing["prices_display_mode"] == "brutto"
    assert pricing["effective_display_mode"] == "brutto"
    assert pricing["net_amount"] == "100.00"
    assert pricing["gross_amount"] == "100.00"


def test_list_pricing_matches_detail_block(db, client):
    resource = _make_resource(db, price_display_mode=None)

    list_resp = client.get("/api/v1/booking/resources")
    detail_resp = client.get(f"/api/v1/booking/resources/{resource.slug}")

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200

    listed = next(
        r for r in list_resp.get_json()["resources"] if r["slug"] == resource.slug
    )
    detail = detail_resp.get_json()
    assert listed["pricing"] == detail["pricing"]


def test_list_netto_override_surfaces_effective_netto(db, client):
    resource = _make_resource(db, price_display_mode="netto")

    resp = client.get("/api/v1/booking/resources")

    assert resp.status_code == 200, resp.get_json()
    listed = next(r for r in resp.get_json()["resources"] if r["slug"] == resource.slug)
    pricing = listed["pricing"]
    assert pricing["prices_display_mode"] == "brutto"
    assert pricing["effective_display_mode"] == "netto"
