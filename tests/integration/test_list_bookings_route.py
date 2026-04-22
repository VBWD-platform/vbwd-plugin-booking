"""Integration tests for GET /api/v1/booking/bookings (pagination + filter)."""
from datetime import timedelta
from uuid import uuid4

from vbwd.utils.datetime_utils import utcnow


def _login_and_get_token(client, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    body = response.get_json()
    return body.get("token") or body.get("access_token")


def _create_user(db, email, password_hash="x"):
    from vbwd.models.user import User

    user = User(id=uuid4(), email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()
    return user


def _create_resource(db):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Room",
        slug=f"room-{uuid4().hex[:8]}",
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


def _register_and_login(client, db, email):
    """Register an active user via the real /auth/register flow so a usable
    JWT can be obtained. Avoids reaching into password hashing internals."""
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPass123!"},
    )
    assert register_response.status_code in (200, 201), register_response.data

    # Mark the user active so login succeeds (registration defaults may need this).
    from vbwd.models.user import User

    user = db.session.query(User).filter_by(email=email).first()
    user.status = "ACTIVE"
    db.session.commit()

    token = _login_and_get_token(client, email, "StrongPass123!")
    assert token, f"login did not return a token: {register_response.data}"
    return user, token


class TestListBookingsRoute:
    def test_returns_paginated_shape(self, client, db):
        email = f"paginated-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _create_resource(db)

        for offset_hours in range(1, 8):
            _create_booking(
                db,
                user.id,
                resource.id,
                start_offset_hours=offset_hours,
                status="confirmed",
            )

        response = client.get(
            "/api/v1/booking/bookings?status=upcoming&page=1&per_page=3",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["page"] == 1
        assert body["per_page"] == 3
        assert body["total"] == 7
        assert body["total_pages"] == 3
        assert body["status"] == "upcoming"
        assert len(body["bookings"]) == 3

    def test_filters_past_vs_upcoming(self, client, db):
        email = f"filter-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _create_resource(db)

        _create_booking(
            db, user.id, resource.id, start_offset_hours=-48, status="completed"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=-24, status="cancelled"
        )
        _create_booking(
            db, user.id, resource.id, start_offset_hours=48, status="confirmed"
        )

        upcoming_response = client.get(
            "/api/v1/booking/bookings?status=upcoming",
            headers={"Authorization": f"Bearer {token}"},
        )
        past_response = client.get(
            "/api/v1/booking/bookings?status=past",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert upcoming_response.get_json()["total"] == 1
        assert past_response.get_json()["total"] == 2

    def test_rejects_invalid_status(self, client, db):
        email = f"invalid-status-{uuid4().hex[:8]}@example.com"
        _, token = _register_and_login(client, db, email)

        response = client.get(
            "/api/v1/booking/bookings?status=banana",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400

    def test_clamps_per_page_to_max(self, client, db):
        email = f"clamp-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _create_resource(db)
        _create_booking(
            db, user.id, resource.id, start_offset_hours=24, status="confirmed"
        )

        response = client.get(
            "/api/v1/booking/bookings?per_page=500",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.get_json()["per_page"] == 100

    def test_requires_auth(self, client, db):
        response = client.get("/api/v1/booking/bookings")
        assert response.status_code == 401
