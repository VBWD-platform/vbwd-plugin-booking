"""Integration: booking ``seed_catalog(session)`` is the single seed home (S88).

Proves the session-taking function (which ``flask reset-demo`` runs through
core's demo-data registry) seeds schemas/categories/resources and is idempotent.
"""
from plugins.booking.booking.demo_seed import seed_catalog
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.models.resource_category import (
    BookableResourceCategory,
)


def test_seed_catalog_seeds_resources_and_categories(db):
    stats = seed_catalog(db.session)

    assert stats["booking_resources"] > 0
    assert stats["booking_categories"] > 0
    assert (
        db.session.query(BookableResource).filter_by(slug="dr-smith").first()
        is not None
    )


def test_seed_catalog_is_idempotent(db):
    seed_catalog(db.session)
    first_resources = db.session.query(BookableResource).count()
    first_categories = db.session.query(BookableResourceCategory).count()

    seed_catalog(db.session)
    assert db.session.query(BookableResource).count() == first_resources
    assert db.session.query(BookableResourceCategory).count() == first_categories
