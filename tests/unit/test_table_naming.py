"""Oracle: the booking reservation table is `booking_reservation` (sprint S43.3)."""
from plugins.booking.booking.models.booking import Booking


def test_booking_table_is_plugin_prefixed():
    assert Booking.__tablename__ == "booking_reservation"
    assert Booking.__tablename__.startswith("booking_")
