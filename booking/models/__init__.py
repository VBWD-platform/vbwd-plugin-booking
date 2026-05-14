"""Booking models — eager-import so SQLAlchemy can resolve relationship strings."""
from plugins.booking.booking.models.custom_schema import BookingCustomSchema
from plugins.booking.booking.models.resource_category import BookableResourceCategory
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.models.resource_image import BookableResourceImage
from plugins.booking.booking.models.slot_block import BookableResourceSlotBlock
from plugins.booking.booking.models.booking import Booking
from plugins.booking.booking.models.export_rule import BookingExportRule

__all__ = [
    "BookingCustomSchema",
    "BookableResourceCategory",
    "BookableResource",
    "BookableResourceImage",
    "BookableResourceSlotBlock",
    "Booking",
    "BookingExportRule",
]
