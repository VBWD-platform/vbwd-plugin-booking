"""Integration tests for the full booking lifecycle (event-driven).

Covers:
- Checkout flow: POST /api/v1/booking/checkout → invoice created
- Event-driven booking creation: invoice.paid → booking record
- User booking list and detail
- Booking cancellation
- Invoice refund → booking auto-cancelled
- Capacity enforcement
- Admin direct booking creation

All dates are relative (future Monday) to prevent test failures on specific days.
- Admin booking list + dashboard
- Public resource and availability endpoints
"""
import uuid
from datetime import date, timedelta

import pytest


def _future_date(days_ahead: int = 14) -> str:
    """Return a future weekday date string (YYYY-MM-DD), always a Monday."""
    target = date.today() + timedelta(days=days_ahead)
    # Shift to next Monday if not already Monday
    days_until_monday = (7 - target.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    target = target + timedelta(days=days_until_monday)
    return target.isoformat()


# Pre-compute dates for each test to avoid collisions
DAY1 = _future_date(14)  # Public endpoints
DAY2 = _future_date(21)  # Checkout
DAY3 = _future_date(28)  # Event-driven creation
DAY4 = _future_date(35)  # User ops slot 1
DAY5 = _future_date(42)  # Refund
DAY6 = _future_date(49)  # Capacity
DAY7 = _future_date(56)  # Admin
DAY8 = _future_date(63)  # Authorize tests


@pytest.fixture(autouse=True)
def _tokens(client, db):
    """Log in both admin and test user, return tokens."""
    admin_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminPass123@"},
    )
    if admin_resp.status_code != 200:
        pytest.skip("Admin user not available")

    user_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "TestPass123@"},
    )
    if user_resp.status_code != 200:
        pytest.skip("Test user not available")

    return {
        "admin": admin_resp.get_json().get("access_token")
        or admin_resp.get_json().get("token"),
        "user": user_resp.get_json().get("access_token")
        or user_resp.get_json().get("token"),
    }


@pytest.fixture
def admin_headers(_tokens):
    return {"Authorization": f"Bearer {_tokens['admin']}"}


@pytest.fixture
def user_headers(_tokens):
    return {"Authorization": f"Bearer {_tokens['user']}"}


@pytest.fixture
def test_resource(client, db, admin_headers):
    """Create a resource with schedule for integration tests."""
    slug = f"e2e-resource-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={
            "name": "E2E Test Resource",
            "slug": slug,
            "capacity": 2,
            "price": "50.00",
            "currency": "EUR",
            "slot_duration_minutes": 30,
            "availability": {
                "schedule": {
                    "mon": [{"start": "09:00", "end": "17:00"}],
                    "tue": [{"start": "09:00", "end": "17:00"}],
                    "wed": [{"start": "09:00", "end": "17:00"}],
                    "thu": [{"start": "09:00", "end": "17:00"}],
                    "fri": [{"start": "09:00", "end": "17:00"}],
                    "sat": [],
                    "sun": [],
                },
            },
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.get_json()


# ── Public endpoints ─────────────────────────────────────────────────────────


class TestPublicEndpoints:
    def test_list_resources(self, client, db, test_resource):
        resp = client.get("/api/v1/booking/resources")
        assert resp.status_code == 200
        slugs = [r["slug"] for r in resp.get_json()["resources"]]
        assert test_resource["slug"] in slugs

    def test_get_resource_by_slug(self, client, db, test_resource):
        resp = client.get(f"/api/v1/booking/resources/{test_resource['slug']}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "E2E Test Resource"

    def test_get_resource_not_found(self, client, db):
        resp = client.get("/api/v1/booking/resources/nonexistent-slugf")
        assert resp.status_code == 404

    def test_get_availability(self, client, db, test_resource):
        # Monday {DAY1}
        resp = client.get(
            f"/api/v1/booking/resources/{test_resource['slug']}"
            f"/availability?date={DAY1}"
        )
        assert resp.status_code == 200
        slots = resp.get_json()["slots"]
        assert len(slots) > 0
        assert all(s["available_capacity"] > 0 for s in slots)

    def test_availability_requires_date(self, client, db, test_resource):
        resp = client.get(
            f"/api/v1/booking/resources/{test_resource['slug']}/availability"
        )
        assert resp.status_code == 400


# ── Checkout flow ────────────────────────────────────────────────────────────


class TestCheckoutFlow:
    def test_checkout_creates_invoice(self, client, db, user_headers, test_resource):
        resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY2}T10:00:00",
                "end_at": f"{DAY2}T10:30:00",
            },
            headers=user_headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "invoice_id" in data
        assert "invoice_number" in data
        assert data["invoice_number"].startswith("BK-")

    def test_checkout_requires_auth(self, client, db, test_resource):
        resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY2}T10:00:00",
                "end_at": f"{DAY2}T10:30:00",
            },
        )
        assert resp.status_code == 401

    def test_checkout_validates_required_fields(self, client, db, user_headers):
        resp = client.post(
            "/api/v1/booking/checkout",
            json={"resource_slug": "something"},
            headers=user_headers,
        )
        assert resp.status_code == 400

    def test_checkout_resource_not_found(self, client, db, user_headers):
        resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": "nonexistent",
                "start_at": f"{DAY2}T10:00:00",
                "end_at": f"{DAY2}T10:30:00",
            },
            headers=user_headers,
        )
        assert resp.status_code == 404

    def test_checkout_does_not_create_booking(
        self, client, db, user_headers, test_resource
    ):
        """Checkout creates invoice only — no booking record yet."""
        client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY2}T09:00:00",
                "end_at": f"{DAY2}T09:30:00",
            },
            headers=user_headers,
        )

        bookings_resp = client.get(
            "/api/v1/booking/bookings",
            headers=user_headers,
        )
        bookings = bookings_resp.get_json()["bookings"]
        matching = [
            b
            for b in bookings
            if b["start_at"] == f"{DAY2}T09:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        ]
        assert len(matching) == 0


# ── Event-driven booking creation ────────────────────────────────────────────


class TestEventDrivenBookingCreation:
    def test_invoice_paid_creates_confirmed_booking(
        self, client, db, user_headers, test_resource, app
    ):
        """Full flow: checkout → simulate payment → booking exists."""
        # 1. Checkout
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY3}T10:00:00",
                "end_at": f"{DAY3}T10:30:00",
                "custom_fields": {"reason": "checkup"},
                "notes": "First visit",
            },
            headers=user_headers,
        )
        assert checkout_resp.status_code == 201
        invoice_number = checkout_resp.get_json()["invoice_number"]

        # 2. Simulate payment: mark invoice paid + publish event
        from vbwd.models.invoice import UserInvoice
        from vbwd.events.bus import event_bus

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            assert invoice is not None
            invoice.mark_paid(
                payment_ref="test-ref-001",
                payment_method="mock",
            )
            db.session.flush()

            event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_number,
                    "user_email": "test@example.com",
                    "user_name": "test@example.com",
                    "amount": str(invoice.amount),
                    "paid_date": f"{DAY3}",
                    "invoice_url": f"/invoices/{invoice.id}",
                },
            )
            db.session.commit()

        # 3. Verify booking created
        bookings_resp = client.get(
            "/api/v1/booking/bookings",
            headers=user_headers,
        )
        bookings = bookings_resp.get_json()["bookings"]
        matching = [
            b
            for b in bookings
            if b["start_at"] == f"{DAY3}T10:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        ]
        assert len(matching) == 1
        booking = matching[0]
        assert booking["status"] == "confirmed"
        assert booking["custom_fields"]["reason"] == "checkup"
        assert booking["notes"] == "First visit"
        assert booking["invoice_id"] is not None


# ── User booking list & cancel ────────────────────────────────────────────────


class TestUserBookingOperations:
    def _create_paid_booking(
        self, client, db, user_headers, test_resource, app, slot_time="11:00"
    ):
        """Helper: checkout + simulate payment, return booking."""
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY4}T{slot_time}:00",
                "end_at": f"{DAY4}T{slot_time[:-2]}30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice
        from vbwd.events.bus import event_bus

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_paid(payment_ref="test-pay", payment_method="mock")
            db.session.flush()
            event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_number,
                    "user_email": "test@example.com",
                    "user_name": "test@example.com",
                    "amount": str(invoice.amount),
                    "paid_date": f"{DAY4}",
                    "invoice_url": f"/invoices/{invoice.id}",
                },
            )
            db.session.commit()

        bookings = client.get(
            "/api/v1/booking/bookings", headers=user_headers
        ).get_json()["bookings"]
        return next(
            b
            for b in bookings
            if b["start_at"] == f"{DAY4}T{slot_time}:00"
            and b["resource"]["slug"] == test_resource["slug"]
        )

    def test_user_can_list_bookings(self, client, db, user_headers, test_resource, app):
        self._create_paid_booking(client, db, user_headers, test_resource, app, "11:00")

        resp = client.get("/api/v1/booking/bookings", headers=user_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()["bookings"]) >= 1

    def test_user_can_get_booking_detail(
        self, client, db, user_headers, test_resource, app
    ):
        booking = self._create_paid_booking(
            client, db, user_headers, test_resource, app, "12:00"
        )

        resp = client.get(
            f"/api/v1/booking/bookings/{booking['id']}",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["id"] == booking["id"]

    def test_user_can_cancel_booking(
        self, client, db, user_headers, test_resource, app
    ):
        booking = self._create_paid_booking(
            client, db, user_headers, test_resource, app, "13:00"
        )

        resp = client.post(
            f"/api/v1/booking/bookings/{booking['id']}/cancel",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cancelled"

    def test_cancel_already_cancelled_fails(
        self, client, db, user_headers, test_resource, app
    ):
        booking = self._create_paid_booking(
            client, db, user_headers, test_resource, app, "14:00"
        )
        client.post(
            f"/api/v1/booking/bookings/{booking['id']}/cancel",
            headers=user_headers,
        )
        resp = client.post(
            f"/api/v1/booking/bookings/{booking['id']}/cancel",
            headers=user_headers,
        )
        assert resp.status_code == 400

    def test_user_cannot_see_other_users_booking(
        self, client, db, user_headers, admin_headers, test_resource, app
    ):
        booking = self._create_paid_booking(
            client, db, user_headers, test_resource, app, "15:00"
        )

        resp = client.get(
            f"/api/v1/booking/bookings/{booking['id']}",
            headers=admin_headers,
        )
        assert resp.status_code == 403


# ── Invoice refund → booking cancelled ────────────────────────────────────────


class TestRefundCancellation:
    def test_invoice_refund_cancels_booking(
        self, client, db, user_headers, test_resource, app
    ):
        # 1. Create a paid booking
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY5}T10:00:00",
                "end_at": f"{DAY5}T10:30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice
        from vbwd.events.bus import event_bus

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_paid(payment_ref="ref-refund", payment_method="mock")
            db.session.flush()
            event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_number,
                    "user_email": "test@example.com",
                    "user_name": "test@example.com",
                    "amount": str(invoice.amount),
                    "paid_date": f"{DAY5}",
                    "invoice_url": f"/invoices/{invoice.id}",
                },
            )
            db.session.commit()

        # 2. Get the booking
        bookings = client.get(
            "/api/v1/booking/bookings", headers=user_headers
        ).get_json()["bookings"]
        booking = next(
            b
            for b in bookings
            if b["start_at"] == f"{DAY5}T10:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        )
        assert booking["status"] == "confirmed"

        # 3. Simulate refund
        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            event_bus.publish(
                "invoice.refunded",
                {
                    "invoice_id": invoice_number,
                    "invoice_uuid": str(invoice.id),
                    "user_id": str(invoice.user_id),
                    "amount": str(invoice.amount),
                    "refund_reference": "refund-test-001",
                },
            )
            db.session.commit()

        # 4. Verify booking is cancelled
        detail_resp = client.get(
            f"/api/v1/booking/bookings/{booking['id']}",
            headers=user_headers,
        )
        assert detail_resp.get_json()["status"] == "cancelled"


# ── Capacity enforcement ──────────────────────────────────────────────────────


class TestCapacityEnforcement:
    def test_checkout_respects_capacity(
        self, client, db, user_headers, admin_headers, app
    ):
        """Resource with capacity=1: second checkout should fail."""
        slug = f"cap-test-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/admin/booking/resources",
            json={
                "name": "Single Capacity",
                "slug": slug,
                "capacity": 1,
                "price": "30.00",
                "slot_duration_minutes": 60,
                "availability": {
                    "schedule": {
                        "mon": [{"start": "09:00", "end": "17:00"}],
                        "tue": [{"start": "09:00", "end": "17:00"}],
                        "wed": [{"start": "09:00", "end": "17:00"}],
                        "thu": [{"start": "09:00", "end": "17:00"}],
                        "fri": [{"start": "09:00", "end": "17:00"}],
                        "sat": [],
                        "sun": [],
                    }
                },
            },
            headers=admin_headers,
        )

        # First checkout
        resp1 = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": slug,
                "start_at": f"{DAY6}T10:00:00",
                "end_at": f"{DAY6}T11:00:00",
            },
            headers=user_headers,
        )
        assert resp1.status_code == 201

        # Simulate payment so the slot is occupied
        from vbwd.models.invoice import UserInvoice
        from vbwd.events.bus import event_bus

        invoice_number = resp1.get_json()["invoice_number"]
        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_paid(payment_ref="cap-ref", payment_method="mock")
            db.session.flush()
            event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_number,
                    "user_email": "test@example.com",
                    "user_name": "test@example.com",
                    "amount": str(invoice.amount),
                    "paid_date": f"{DAY6}",
                    "invoice_url": f"/invoices/{invoice.id}",
                },
            )
            db.session.commit()

        # Second checkout on same slot should fail
        resp2 = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": slug,
                "start_at": f"{DAY6}T10:00:00",
                "end_at": f"{DAY6}T11:00:00",
            },
            headers=user_headers,
        )
        assert resp2.status_code == 400
        assert "capacity" in resp2.get_json()["error"].lower()


# ── Admin operations ──────────────────────────────────────────────────────────


class TestAdminOperations:
    def test_admin_create_booking_directly(
        self, client, db, admin_headers, user_headers, test_resource
    ):
        """Admin can bypass checkout and create booking directly."""
        # Get test user id
        from sqlalchemy import text

        result = db.session.execute(
            text("SELECT id FROM \"user\" WHERE email = 'test@example.com'")
        )
        user_id = str(result.scalar())

        resp = client.post(
            "/api/v1/admin/booking/bookings",
            json={
                "resource_slug": test_resource["slug"],
                "user_id": user_id,
                "start_at": f"{DAY7}T09:00:00",
                "end_at": f"{DAY7}T09:30:00",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["status"] == "pending"

    def test_admin_list_bookings(self, client, db, admin_headers, test_resource):
        resp = client.get(
            "/api/v1/admin/booking/bookings",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert "bookings" in resp.get_json()

    def test_admin_dashboard(self, client, db, admin_headers, test_resource):
        resp = client.get(
            "/api/v1/admin/booking/dashboard",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "today" in data
        assert "upcoming" in data

    def test_admin_create_booking_requires_admin(
        self, client, db, user_headers, test_resource
    ):
        resp = client.post(
            "/api/v1/admin/booking/bookings",
            json={
                "resource_slug": test_resource["slug"],
                "user_id": "some-id",
                "start_at": f"{DAY7}T10:00:00",
                "end_at": f"{DAY7}T10:30:00",
            },
            headers=user_headers,
        )
        assert resp.status_code == 403


# ── Authorize / Capture flow ─────────────────────────────────────────────────


class TestAuthorizeAndCapture:
    def test_authorized_invoice_not_paid(
        self, client, db, user_headers, test_resource, app
    ):
        """Simulate authorize → invoice AUTHORIZED, not PAID."""
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY8}T10:00:00",
                "end_at": f"{DAY8}T10:30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice
        from vbwd.models.enums import InvoiceStatus

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_authorized(
                payment_ref="pi_auth_test",
                payment_method="mock",
            )
            invoice.payment_intent_id = "pi_auth_test"
            db.session.commit()
            assert invoice.status == InvoiceStatus.AUTHORIZED
            assert invoice.is_capturable is True

    def test_no_booking_on_authorize(
        self, client, db, user_headers, test_resource, app
    ):
        """AUTHORIZED invoice should NOT create a booking."""
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY8}T10:00:00",
                "end_at": f"{DAY8}T10:30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_authorized(payment_ref="pi_nobook", payment_method="mock")
            invoice.payment_intent_id = "pi_nobook"
            db.session.commit()

        bookings = client.get(
            "/api/v1/booking/bookings", headers=user_headers
        ).get_json()["bookings"]
        matching = [
            b
            for b in bookings
            if b["start_at"] == f"{DAY8}T10:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        ]
        assert len(matching) == 0

    def test_capture_creates_booking(
        self, client, db, user_headers, test_resource, app
    ):
        """Capture AUTHORIZED invoice → booking created via invoice.paid event."""
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY8}T10:00:00",
                "end_at": f"{DAY8}T10:30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice
        from vbwd.events.bus import event_bus

        # Authorize
        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_authorized(payment_ref="pi_cap", payment_method="mock")
            invoice.payment_intent_id = "pi_cap"
            db.session.commit()

        # Capture (simulate: mark paid + emit invoice.paid)
        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_paid(payment_ref="pi_cap", payment_method="mock")
            db.session.flush()

            event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_number,
                    "user_email": "test@example.com",
                    "user_name": "test@example.com",
                    "amount": str(invoice.amount),
                    "paid_date": f"{DAY8}",
                    "invoice_url": f"/invoices/{invoice.id}",
                },
            )
            db.session.commit()

        bookings = client.get(
            "/api/v1/booking/bookings", headers=user_headers
        ).get_json()["bookings"]
        matching = [
            b
            for b in bookings
            if b["start_at"] == f"{DAY8}T10:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        ]
        assert len(matching) == 1
        assert matching[0]["status"] == "confirmed"

    def test_release_cancels_no_booking(
        self, client, db, user_headers, test_resource, app
    ):
        """Release AUTHORIZED → invoice CANCELLED, no booking."""
        checkout_resp = client.post(
            "/api/v1/booking/checkout",
            json={
                "resource_slug": test_resource["slug"],
                "start_at": f"{DAY8}T10:00:00",
                "end_at": f"{DAY8}T10:30:00",
            },
            headers=user_headers,
        )
        invoice_number = checkout_resp.get_json()["invoice_number"]

        from vbwd.models.invoice import UserInvoice
        from vbwd.models.enums import InvoiceStatus

        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_authorized(payment_ref="pi_rel", payment_method="mock")
            invoice.payment_intent_id = "pi_rel"
            db.session.commit()

        # Release
        with app.app_context():
            invoice = (
                db.session.query(UserInvoice)
                .filter_by(invoice_number=invoice_number)
                .first()
            )
            invoice.mark_cancelled()
            db.session.commit()
            assert invoice.status == InvoiceStatus.CANCELLED

        bookings = client.get(
            "/api/v1/booking/bookings", headers=user_headers
        ).get_json()["bookings"]
        matching = [
            b
            for b in bookings
            if b["start_at"] == f"{DAY8}T10:00:00"
            and b["resource"]["slug"] == test_resource["slug"]
        ]
        assert len(matching) == 0
