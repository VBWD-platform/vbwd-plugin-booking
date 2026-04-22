"""Integration tests for GET /api/v1/booking/bookings/:id/{pdf,ical}."""
from datetime import timedelta
from uuid import uuid4

from vbwd.utils.datetime_utils import utcnow


def _login_and_get_token(client, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    body = response.get_json()
    return body.get("token") or body.get("access_token")


def _register_and_login(client, db, email: str):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPass123!"},
    )
    assert response.status_code in (200, 201), response.data

    from vbwd.models.user import User

    user = db.session.query(User).filter_by(email=email).first()
    user.status = "ACTIVE"
    db.session.commit()
    token = _login_and_get_token(client, email, "StrongPass123!")
    return user, token


def _seed_resource(db):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Studio Room",
        slug=f"studio-{uuid4().hex[:8]}",
        description="A quiet studio.",
        capacity=1,
        slot_duration_minutes=60,
        price=50,
        currency="EUR",
        is_active=True,
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def _seed_booking(
    db, user_id, resource_id, *, start_offset_hours=24, status="confirmed"
):
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


class TestBookingPdfEndpoint:
    def test_owner_gets_pdf_stream(self, client, db):
        email = f"pdf-owner-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _seed_resource(db)
        booking = _seed_booking(db, user.id, resource.id)

        response = client.get(
            f"/api/v1/booking/bookings/{booking.id}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.content_type == "application/pdf"
        assert response.data.startswith(b"%PDF-")
        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert str(booking.id)[:8] in disposition

    def test_non_owner_gets_403(self, client, db):
        owner_email = f"pdf-owner-{uuid4().hex[:8]}@example.com"
        intruder_email = f"pdf-intruder-{uuid4().hex[:8]}@example.com"

        owner, _ = _register_and_login(client, db, owner_email)
        _, intruder_token = _register_and_login(client, db, intruder_email)
        resource = _seed_resource(db)
        booking = _seed_booking(db, owner.id, resource.id)

        response = client.get(
            f"/api/v1/booking/bookings/{booking.id}/pdf",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

        assert response.status_code == 403

    def test_unknown_id_gets_404(self, client, db):
        email = f"pdf-missing-{uuid4().hex[:8]}@example.com"
        _, token = _register_and_login(client, db, email)

        response = client.get(
            f"/api/v1/booking/bookings/{uuid4()}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_requires_auth(self, client, db):
        response = client.get(f"/api/v1/booking/bookings/{uuid4()}/pdf")
        assert response.status_code == 401


class TestBookingIcalEndpoint:
    def test_owner_gets_vcalendar_stream(self, client, db):
        email = f"ical-owner-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _seed_resource(db)
        booking = _seed_booking(db, user.id, resource.id)

        response = client.get(
            f"/api/v1/booking/bookings/{booking.id}/ical",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/calendar")
        text = response.data.decode("utf-8")
        assert text.startswith("BEGIN:VCALENDAR")
        assert "METHOD:PUBLISH" in text
        assert f"UID:{booking.id}" in text
        assert "SUMMARY:Studio Room" in text
        assert "STATUS:CONFIRMED" in text
        assert text.rstrip("\r\n").endswith("END:VCALENDAR")

    def test_cancelled_status_maps_to_ical_cancelled(self, client, db):
        email = f"ical-cancel-{uuid4().hex[:8]}@example.com"
        user, token = _register_and_login(client, db, email)
        resource = _seed_resource(db)
        booking = _seed_booking(db, user.id, resource.id, status="cancelled")

        response = client.get(
            f"/api/v1/booking/bookings/{booking.id}/ical",
            headers={"Authorization": f"Bearer {token}"},
        )

        text = response.data.decode("utf-8")
        assert "STATUS:CANCELLED" in text

    def test_non_owner_gets_403(self, client, db):
        owner_email = f"ical-owner-{uuid4().hex[:8]}@example.com"
        intruder_email = f"ical-intruder-{uuid4().hex[:8]}@example.com"

        owner, _ = _register_and_login(client, db, owner_email)
        _, intruder_token = _register_and_login(client, db, intruder_email)
        resource = _seed_resource(db)
        booking = _seed_booking(db, owner.id, resource.id)

        response = client.get(
            f"/api/v1/booking/bookings/{booking.id}/ical",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

        assert response.status_code == 403
