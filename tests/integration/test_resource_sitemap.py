"""Booking resources in the cms sitemap (S154 P2) — real rows, real routes.

* The repository pages PUBLIC (active) resources in SQL, ordered by id, and its
  count matches the paged sequence.
* With cms enabled, app boot registered ``booking-resources``: ``/sitemap.xml``
  lists its chunk and the chunk carries the public ``/booking/<slug>`` URL.
"""
from decimal import Decimal
from uuid import uuid4

import pytest

from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
)


def _resource(db, *, slug, is_active=True):
    resource = BookableResource(
        id=uuid4(),
        name=slug.replace("-", " ").title(),
        slug=slug,
        price=Decimal("10.00"),
        is_active=is_active,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def _walk_public_slugs(repository, page_size):
    slugs = []
    for offset in range(0, repository.count_public_resources(), page_size):
        rows = repository.list_public_resource_slugs(offset, page_size)
        slugs.extend(slug for slug, _updated_at in rows)
    return slugs


def _walk_public_rows(repository):
    total = repository.count_public_resources()
    return dict(repository.list_public_resource_slugs(0, total))


def test_public_resource_paging_filters_inactive_and_orders_by_id(db):
    repository = ResourceRepository(db.session)
    count_before = repository.count_public_resources()
    active = [_resource(db, slug=f"sitemap-room-{index}") for index in range(3)]
    inactive = _resource(db, slug="sitemap-closed-room", is_active=False)

    assert repository.count_public_resources() == count_before + len(active)

    walked = _walk_public_slugs(repository, page_size=2)

    assert len(walked) == repository.count_public_resources()
    assert inactive.slug not in walked
    expected_order = [
        resource.slug for resource in sorted(active, key=lambda item: item.id)
    ]
    assert [slug for slug in walked if slug in expected_order] == expected_order


def test_public_resource_page_carries_updated_at(db):
    repository = ResourceRepository(db.session)
    resource = _resource(db, slug="sitemap-lastmod-room")

    rows = _walk_public_rows(repository)

    assert rows[resource.slug] == resource.updated_at


def test_cms_sitemap_lists_the_booking_resource_chunk(client, db):
    seo_registry = pytest.importorskip("plugins.cms.src.services.seo_registry")
    assert seo_registry.find_sitemap_provider("booking-resources") is not None
    public = _resource(db, slug="sitemap-public-court")
    hidden = _resource(db, slug="sitemap-hidden-court", is_active=False)

    index_response = client.get("/sitemap.xml")
    chunk_response = client.get("/sitemap-booking-resources-1.xml")

    assert index_response.status_code == 200
    assert "sitemap-booking-resources-1.xml" in index_response.get_data(as_text=True)
    assert chunk_response.status_code == 200
    chunk_body = chunk_response.get_data(as_text=True)
    assert f"/booking/{public.slug}</loc>" in chunk_body
    assert f"/booking/{hidden.slug}<" not in chunk_body
