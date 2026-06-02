"""Integration: POST /api/v1/booking/checkout applies a BOOKING-scope coupon.

Mirrors the shop/subscription checkout-coupon tests: a valid BOOKING coupon adds
a negative discount line + reduces the booking invoice; an invalid one is
rejected with no invoice.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.invoice import UserInvoice
from vbwd.models.user import User


@pytest.fixture
def discount_ready(db):
    # The discount plugin is an optional, opt-in collaborator of booking
    # checkout. This cross-plugin coupon test only runs when discount is
    # installed (full local suite); in isolated plugin CI it is absent, so skip.
    pytest.importorskip("plugins.discount.discount.models")
    import plugins.discount.discount.models  # noqa: F401

    db.create_all()
    from vbwd.services.checkout_price_adjustment_registry import (
        clear_price_adjustments,
        register_price_adjustment,
    )
    from plugins.discount.discount.checkout_adjustment import (
        checkout_price_adjustment,
    )

    register_price_adjustment("discount", checkout_price_adjustment)
    yield
    clear_price_adjustments()


def _make_user(db):
    user = User(
        id=uuid4(),
        email=f"book-{uuid4().hex[:8]}@example.com",
        password_hash="x",
        status=UserStatus.ACTIVE,
        role=UserRole.USER,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _make_resource(db, price="100.00"):
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Tennis Court",
        slug=f"court-{uuid4().hex[:8]}",
        capacity=10,
        price=Decimal(price),
        currency="EUR",
    )
    db.session.add(resource)
    db.session.commit()
    return resource


def _make_coupon(db, *, code, scope, dtype, value):
    from plugins.discount.discount.models.coupon import Coupon
    from plugins.discount.discount.models.discount import DiscountRule
    from plugins.discount.discount.repositories.coupon_repository import (
        CouponRepository,
    )
    from plugins.discount.discount.repositories.discount_repository import (
        DiscountRepository,
    )

    discount = DiscountRepository(db.session).save(
        DiscountRule(
            id=uuid4(),
            name=f"D {code}",
            slug=f"d-{code.lower()}",
            discount_type=dtype,
            value=Decimal(value),
            scope=scope,
            is_active=True,
            priority=10,
        )
    )
    CouponRepository(db.session).save(
        Coupon(id=uuid4(), code=code, discount_id=discount.id, is_active=True)
    )


def _auth(monkeypatch, user):
    from unittest.mock import MagicMock

    import vbwd.middleware.auth as auth_mod

    repo = MagicMock()
    repo.find_by_id.return_value = user
    svc = MagicMock()
    svc.verify_token.return_value = str(user.id)
    monkeypatch.setattr(auth_mod, "UserRepository", lambda *a, **k: repo)
    monkeypatch.setattr(auth_mod, "AuthService", lambda *a, **k: svc)


def _slot():
    start = datetime(2026, 7, 1, 10, 0)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


def test_booking_checkout_with_coupon_reduces_total(
    db, client, discount_ready, monkeypatch
):
    from plugins.discount.discount.models.discount import DiscountScope, DiscountType

    user = _make_user(db)
    resource = _make_resource(db, price="100.00")
    _make_coupon(
        db,
        code="BOOK20",
        scope=DiscountScope.BOOKING,
        dtype=DiscountType.PERCENTAGE,
        value="20.00",
    )
    _auth(monkeypatch, user)
    start_at, end_at = _slot()

    resp = client.post(
        "/api/v1/booking/checkout",
        json={
            "resource_slug": resource.slug,
            "start_at": start_at,
            "end_at": end_at,
            "coupon_code": "BOOK20",
        },
        headers={"Authorization": "Bearer valid"},
    )

    assert resp.status_code == 201, resp.get_json()
    invoice = db.session.get(UserInvoice, resp.get_json()["invoice_id"])
    assert invoice.amount == Decimal("80.00")


def test_booking_checkout_zero_price_auto_pays(db, client, monkeypatch):
    """Pay Zero: a €0 booking is captured on checkout — invoice ends PAID and
    the booking is created, with no payment step."""
    from vbwd.models.enums import InvoiceStatus
    from plugins.booking.booking.models.booking import Booking

    user = _make_user(db)
    resource = _make_resource(db, price="0.00")
    _auth(monkeypatch, user)
    start_at, end_at = _slot()

    resp = client.post(
        "/api/v1/booking/checkout",
        json={
            "resource_slug": resource.slug,
            "start_at": start_at,
            "end_at": end_at,
        },
        headers={"Authorization": "Bearer valid"},
    )

    assert resp.status_code == 201, resp.get_json()
    invoice = db.session.get(UserInvoice, resp.get_json()["invoice_id"])
    assert invoice.total_amount == Decimal("0.00")
    assert invoice.status == InvoiceStatus.PAID
    booking = db.session.query(Booking).filter_by(invoice_id=invoice.id).first()
    assert booking is not None
    assert booking.status == "confirmed"


def test_booking_checkout_rejects_invalid_coupon(
    db, client, discount_ready, monkeypatch
):
    user = _make_user(db)
    resource = _make_resource(db, price="100.00")
    _auth(monkeypatch, user)
    start_at, end_at = _slot()

    resp = client.post(
        "/api/v1/booking/checkout",
        json={
            "resource_slug": resource.slug,
            "start_at": start_at,
            "end_at": end_at,
            "coupon_code": "NOPE",
        },
        headers={"Authorization": "Bearer valid"},
    )

    assert resp.status_code == 400, resp.get_json()
    assert db.session.query(UserInvoice).filter_by(user_id=user.id).count() == 0
