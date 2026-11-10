"""Cross-cutting constants for the booking plugin.

The vendor money path is DECOUPLED from the central marketplace plugin: booking
stamps the buyer invoice line's ``extra_data`` with this LOCAL key under the
selling vendor's user id, and ``marketplace`` credits the vendor from it on
``invoice.paid`` — no plugin ever imports the other. ``VENDOR_ID_KEY`` is a
local copy of the documented ``MARKETPLACE_VENDOR_ID_KEY`` convention, pinned to
the literal by a contract test (DRY without inverting the dependency arrow).
"""

VENDOR_ID_KEY = "vendor_id"

# The public bookable-resource detail route: fe-user ``/booking/:slug`` and the
# theme_booking mount ``/booking/<slug>``. A FIXED route (unlike the
# configurable ``booking_form_slug`` registration form, which is not a resource
# page), shared by every producer of resource links (search, sitemap).
PUBLIC_RESOURCE_PATH_PREFIX = "/booking"


def public_resource_path(slug: str) -> str:
    """The root-relative public URL of the bookable resource ``slug``."""
    return f"{PUBLIC_RESOURCE_PATH_PREFIX}/{slug}"
