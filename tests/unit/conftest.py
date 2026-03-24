"""Unit test conftest — import models so SQLAlchemy mapper resolves all names."""
import plugins.booking.booking.models.custom_schema  # noqa: F401
import plugins.booking.booking.models.resource  # noqa: F401
import plugins.booking.booking.models.resource_category  # noqa: F401
import plugins.booking.booking.models.booking  # noqa: F401
import plugins.booking.booking.models.resource_image  # noqa: F401
import plugins.booking.booking.models.slot_block  # noqa: F401
