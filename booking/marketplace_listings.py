"""Marketplace vendor-listings provider for the booking vertical.

The central ``marketplace`` plugin owns a registry that aggregates a user's
listings across every enabled vertical (its admin "what does this user sell?"
view). Booking contributes a provider that returns the raw ``BookableResource``
dicts a given vendor owns — mirroring the ``vendor_list_resources`` GET route.

This module never imports the marketplace plugin (the money path stays
decoupled — see ``test_vendor_mode_contract``); the actual registration onto the
marketplace registry is a guarded, soft import done in the plugin's ``on_enable``
(``plugins/booking/__init__.py``), so the per-plugin isolated CI (booking
without marketplace) still enables cleanly. Core names nothing here.
"""
from typing import List
from uuid import UUID

# The listing ``type`` id booking contributes — mirrors the marketplace
# ``LISTING_TYPE_CATALOG`` and the fe-user ``ListingType`` for bookings.
BOOKING_LISTING_TYPE_ID = "booking"


def vendor_listings_provider(user_id: UUID) -> List[dict]:
    """Return the raw ``BookableResource`` dicts owned by ``user_id`` (vendor).

    Resolves ``db.session`` and constructs the repository lazily at call time
    (the call happens inside a Flask request), so there is no app-context work
    at import time. Reuses exactly what ``vendor_list_resources`` reads.
    """
    from vbwd.extensions import db
    from plugins.booking.booking.repositories.resource_repository import (
        ResourceRepository,
    )

    resources = ResourceRepository(db.session).find_by_vendor_id(user_id)
    return [resource.to_dict() for resource in resources]
