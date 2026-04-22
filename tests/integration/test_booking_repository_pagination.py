"""Unit tests for BookingRepository.find_by_user_paginated — Sprint 28 D1/Q14.

Uses the postgres-backed `db` fixture from the parent conftest because the
Booking model shares FK metadata with other plugins and cannot be created
in isolation on an in-memory DB.
"""
from datetime import timedelta
from uuid import uuid4

from vbwd.utils.datetime_utils import utcnow


def _create_test_user(db):
    """Persist a minimal user — needed because booking.user_id has a FK."""
    from vbwd.models.user import User

    user = User(
        id=uuid4(),
        email=f"booking-pag-{uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _create_test_resource(db):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Room A",
        slug=f"room-a-{uuid4().hex[:8]}",
        capacity=1,
        slot_duration_minutes=60,
        price=50,
        currency="EUR",
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def _create_booking(db, user_id, resource_id, *, start_offset_hours, status):
    from plugins.booking.booking.models.booking import Booking

    start_at = utcnow() + timedelta(hours=start_offset_hours)
    booking = Booking(
        id=uuid4(),
        user_id=user_id,
        resource_id=resource_id,
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status=status,
        quantity=1,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


class TestFindByUserPaginated:
    def test_returns_all_when_status_is_all(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-48, status="completed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-24, status="cancelled"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=24, status="confirmed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=48, status="pending"
        )

        repo = BookingRepository(db.session)
        bookings, total = repo.find_by_user_paginated(
            user_id=user.id, status_filter="all", page=1, per_page=20
        )

        assert total == 4
        assert len(bookings) == 4

    def test_upcoming_returns_future_confirmed_or_pending_only(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-48, status="completed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-24, status="cancelled"
        )
        upcoming_confirmed = _create_booking(
            db, user.id, resource.id, start_offset_hours=24, status="confirmed"
        )
        upcoming_pending = _create_booking(
            db, user.id, resource.id, start_offset_hours=48, status="pending"
        )

        repo = BookingRepository(db.session)
        bookings, total = repo.find_by_user_paginated(
            user_id=user.id, status_filter="upcoming", page=1, per_page=20
        )

        assert total == 2
        returned_ids = {booking.id for booking in bookings}
        assert returned_ids == {upcoming_confirmed.id, upcoming_pending.id}

    def test_past_returns_anything_not_upcoming(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        past_completed = _create_booking(
            db, user.id, resource.id, start_offset_hours=-48, status="completed"
        )
        past_cancelled = _create_booking(
            db, user.id, resource.id, start_offset_hours=-24, status="cancelled"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=24, status="confirmed"
        )

        repo = BookingRepository(db.session)
        bookings, total = repo.find_by_user_paginated(
            user_id=user.id, status_filter="past", page=1, per_page=20
        )

        assert total == 2
        returned_ids = {booking.id for booking in bookings}
        assert returned_ids == {past_completed.id, past_cancelled.id}

    def test_pagination_slices_by_page(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        for offset_hours in range(1, 11):
            _create_booking(
                db,
                user.id,
                resource.id,
                start_offset_hours=offset_hours,
                status="confirmed",
            )

        repo = BookingRepository(db.session)
        page_1, total = repo.find_by_user_paginated(
            user_id=user.id, status_filter="all", page=1, per_page=3
        )
        page_2, _ = repo.find_by_user_paginated(
            user_id=user.id, status_filter="all", page=2, per_page=3
        )
        page_4, _ = repo.find_by_user_paginated(
            user_id=user.id, status_filter="all", page=4, per_page=3
        )

        assert total == 10
        assert len(page_1) == 3
        assert len(page_2) == 3
        assert len(page_4) == 1
        page_1_ids = {booking.id for booking in page_1}
        page_2_ids = {booking.id for booking in page_2}
        assert not page_1_ids & page_2_ids

    def test_past_is_sorted_descending_by_start_at(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-72, status="completed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-24, status="completed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-48, status="cancelled"
        )

        repo = BookingRepository(db.session)
        bookings, _ = repo.find_by_user_paginated(
            user_id=user.id, status_filter="past", page=1, per_page=20
        )

        starts = [booking.start_at for booking in bookings]
        assert starts == sorted(starts, reverse=True)

    def test_upcoming_is_sorted_ascending_by_start_at(self, db):
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )

        user = _create_test_user(db)
        resource = _create_test_resource(db)
        _create_booking(
            db, user.id, resource.id, start_offset_hours=72, status="confirmed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=24, status="confirmed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=48, status="pending"
        )

        repo = BookingRepository(db.session)
        bookings, _ = repo.find_by_user_paginated(
            user_id=user.id, status_filter="upcoming", page=1, per_page=20
        )

        starts = [booking.start_at for booking in bookings]
        assert starts == sorted(starts)
