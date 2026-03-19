"""Repository for Booking."""
from datetime import datetime

from sqlalchemy import and_

from plugins.booking.booking.models.booking import Booking


class BookingRepository:
    def __init__(self, session):
        self.session = session

    def find_by_id(self, booking_id):
        return self.session.get(Booking, booking_id)

    def find_by_user(self, user_id):
        return (
            self.session.query(Booking)
            .filter_by(user_id=user_id)
            .order_by(Booking.start_at.desc())
            .all()
        )

    def find_by_resource_and_date(self, resource_id, date):
        """Find all bookings for a resource on a specific date."""
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(date, datetime.max.time())
        return (
            self.session.query(Booking)
            .filter(
                and_(
                    Booking.resource_id == resource_id,
                    Booking.start_at >= day_start,
                    Booking.start_at <= day_end,
                    Booking.status.in_(["confirmed", "pending"]),
                )
            )
            .order_by(Booking.start_at)
            .all()
        )

    def find_by_resource_and_date_range(self, resource_id, start_date, end_date):
        """Find bookings for a resource within a date range."""
        return (
            self.session.query(Booking)
            .filter(
                and_(
                    Booking.resource_id == resource_id,
                    Booking.start_at >= start_date,
                    Booking.end_at <= end_date,
                    Booking.status.in_(["confirmed", "pending"]),
                )
            )
            .order_by(Booking.start_at)
            .all()
        )

    def count_by_resource_and_slot(self, resource_id, start_at, end_at):
        """Count active bookings overlapping a time slot (for capacity check)."""
        return (
            self.session.query(Booking)
            .filter(
                and_(
                    Booking.resource_id == resource_id,
                    Booking.start_at < end_at,
                    Booking.end_at > start_at,
                    Booking.status.in_(["confirmed", "pending"]),
                )
            )
            .count()
        )

    def save(self, booking):
        self.session.add(booking)
        self.session.flush()
        return booking

    def delete(self, booking):
        self.session.delete(booking)
        self.session.flush()
