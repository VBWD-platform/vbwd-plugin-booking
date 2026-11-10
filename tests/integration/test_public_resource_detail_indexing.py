"""S154 D7 — the PUBLIC resource detail: ``seo_indexable`` and no inactive leak.

* ``GET /api/v1/booking/resources/<slug>`` carries ``seo_indexable`` — the
  ``seo_index_resources`` switch (default on) — so both frontends can render a
  switched-off resource ``noindex,follow``; the payload is otherwise unchanged.
* An inactive resource is not public: the public detail answers 404 (the admin
  endpoint keeps serving it).

Seeded through the ORM session inside the rolled-back ``db`` fixture (as the
sibling resource-detail suites do); config through the live ``config_store``,
restored afterwards.

Engineering requirements (binding, restated): TDD-first · DevOps-first · SOLID ·
DI · DRY (one switch reader, ``resources_indexing_enabled``) · Liskov · clean
code · NO OVERENGINEERING. Guard: ``bin/pre-commit-check.sh --plugin booking
--full``.
"""
from uuid import uuid4

import pytest
from flask import current_app

from plugins.booking.booking.models.resource import BookableResource

SEO_INDEX_RESOURCES_KEY = "seo_index_resources"


@pytest.fixture
def booking_switch(db):
    """Save ``seo_index_resources`` for one test; restore the saved blob after."""
    store = current_app.config_store
    saved = dict(store.get_config("booking") or {})
    store.save_config(
        "booking",
        {key: value for key, value in saved.items() if key != SEO_INDEX_RESOURCES_KEY},
    )

    def save(value):
        store.save_config(
            "booking",
            {**(store.get_config("booking") or {}), SEO_INDEX_RESOURCES_KEY: value},
        )

    yield save
    store.save_config("booking", saved)


def _make_resource(db, is_active=True):
    resource = BookableResource(
        id=uuid4(),
        name="Room D7",
        slug=f"room-d7-{uuid4().hex[:8]}",
        price=100.0,
        is_active=is_active,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def test_resource_is_indexable_by_default(db, client, booking_switch):
    resource = _make_resource(db)

    body = client.get(f"/api/v1/booking/resources/{resource.slug}").get_json()

    assert body["seo_indexable"] is True
    assert body["slug"] == resource.slug


def test_resource_follows_its_switch(db, client, booking_switch):
    resource = _make_resource(db)
    booking_switch(False)

    body = client.get(f"/api/v1/booking/resources/{resource.slug}").get_json()

    assert body["seo_indexable"] is False


def test_inactive_resource_is_not_public(db, client):
    resource = _make_resource(db, is_active=False)

    response = client.get(f"/api/v1/booking/resources/{resource.slug}")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Resource not found"}
