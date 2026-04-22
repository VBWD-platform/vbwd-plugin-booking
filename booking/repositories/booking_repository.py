"""Repository for Booking."""
from datetime import datetime

from sqlalchemy import and_
from vbwd.utils.datetime_utils import utcnow

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

    def find_by_user_paginated(
        self,
        user_id,
        status_filter: str = "all",
        page: int = 1,
        per_page: int = 20,
    ):
        """Return (bookings, total) for a user with status filter + pagination.

        status_filter:
          - "upcoming": status in {pending, confirmed} AND end_at >= now,
            sorted start_at ascending.
          - "past": everything not classed as upcoming (cancelled, completed,
            or any booking whose end_at is in the past), sorted start_at
            descending.
          - "all": no filter, sorted start_at descending.

        Pagination is 1-indexed. `per_page` is clamped by the caller at the
        route layer (max 100) — the repo trusts the values handed in.
        """
        now = utcnow()
        query = self.session.query(Booking).filter(Booking.user_id == user_id)

        if status_filter == "upcoming":
            query = query.filter(
                Booking.status.in_(["pending", "confirmed"]),
                Booking.end_at >= now,
            ).order_by(Booking.start_at.asc())
        elif status_filter == "past":
            query = query.filter(
                (Booking.status.in_(["cancelled", "completed"]))
                | (Booking.end_at < now)
            ).order_by(Booking.start_at.desc())
        else:
            query = query.order_by(Booking.start_at.desc())

        total_count = query.count()
        offset = max(0, (page - 1) * per_page)
        page_bookings = query.offset(offset).limit(per_page).all()
        return page_bookings, total_count

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

    def count_by_resource_and_slot(
        self, resource_id, start_at, end_at, *, exclude_booking_id=None
    ):
        """Count active bookings overlapping a time slot (for capacity check).

        `exclude_booking_id` lets reschedule callers exclude the booking
        they're moving so it isn't counted as its own competitor when the
        new slot overlaps the old one (e.g. single-capacity resource moving
        ±30 minutes).
        """
        query = self.session.query(Booking).filter(
            and_(
                Booking.resource_id == resource_id,
                Booking.start_at < end_at,
                Booking.end_at > start_at,
                Booking.status.in_(["confirmed", "pending"]),
            )
        )
        if exclude_booking_id is not None:
            query = query.filter(Booking.id != exclude_booking_id)
        return query.count()

    def find_past_confirmed(self):
        """Find confirmed bookings whose end_at is in the past."""
        return (
            self.session.query(Booking)
            .filter(
                and_(
                    Booking.status == "confirmed",
                    Booking.end_at < utcnow(),
                )
            )
            .all()
        )

    def find_by_invoice_id(self, invoice_id):
        """Find all bookings linked to a specific invoice."""
        return self.session.query(Booking).filter_by(invoice_id=invoice_id).all()

    def save(self, booking):
        self.session.add(booking)
        self.session.commit()
        return booking

    def delete(self, booking):
        self.session.delete(booking)
        self.session.commit()
