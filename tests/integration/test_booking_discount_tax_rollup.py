"""S96.1 — booking checkout discount keeps the invoice tax split correct.

The pre-S96 route overwrote ``invoice.subtotal = invoice.tax_amount =
invoice.total_amount = brutto - discount`` after adding the coupon line, which
collapsed netto = tax = brutto and left ``tax_amount`` stale. This pins the
correct oracle (D-DiscountTax): the discount reduces NETTO, tax is recomputed on
the discounted netto, the per-line ``tax_breakdown`` is preserved, and the
invariant ``subtotal + tax_amount == total_amount`` holds.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.invoice import UserInvoice
from vbwd.models.invoice_line_item import InvoiceLineItem
from vbwd.models.tax import Tax
from vbwd.models.user import User
from vbwd.services.core_settings_store import update_core_settings


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


def _make_taxed_resource(db, *, price="100.00", rate="19.00"):
    from plugins.booking.booking.models.resource import BookableResource

    tax = Tax(name="VAT", code=f"VAT_{uuid4().hex[:6]}", rate=Decimal(rate))
    resource = BookableResource(
        id=uuid4(),
        name="Tennis Court",
        slug=f"court-{uuid4().hex[:8]}",
        capacity=10,
        price=float(Decimal(price)),
    )
    db.session.add_all([tax, resource])
    db.session.flush()
    resource.taxes = [tax]
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


def test_discounted_taxed_booking_keeps_tax_split_invariant(
    db, client, discount_ready, monkeypatch
):
    from plugins.discount.discount.models.discount import DiscountScope, DiscountType

    update_core_settings({"prices_mode_in_db": "NETTO"})
    user = _make_user(db)
    # netto 100, 19% → brutto 119.00
    resource = _make_taxed_resource(db, price="100.00", rate="19.00")
    # A fixed 11.90 € (gross) coupon: equivalent to 10.00 € net + 1.90 € tax.
    _make_coupon(
        db,
        code="BOOK1190",
        scope=DiscountScope.BOOKING,
        dtype=DiscountType.FIXED_AMOUNT,
        value="11.90",
    )
    _auth(monkeypatch, user)
    start_at, end_at = _slot()

    resp = client.post(
        "/api/v1/booking/checkout",
        json={
            "resource_slug": resource.slug,
            "start_at": start_at,
            "end_at": end_at,
            "coupon_code": "BOOK1190",
        },
        headers={"Authorization": "Bearer valid"},
    )

    assert resp.status_code == 201, resp.get_json()
    invoice = db.session.get(UserInvoice, resp.get_json()["invoice_id"])

    subtotal = Decimal(str(invoice.subtotal))
    tax_amount = Decimal(str(invoice.tax_amount))
    total_amount = Decimal(str(invoice.total_amount))

    # Invariant: netto + Σtax == brutto.
    assert (subtotal + tax_amount).quantize(Decimal("0.01")) == total_amount.quantize(
        Decimal("0.01")
    )
    # Total reduced by the full gross discount: 119.00 - 11.90 == 107.10.
    assert total_amount.quantize(Decimal("0.01")) == Decimal("107.10")
    # D-DiscountTax: discount reduces NETTO (100 - 10 == 90).
    assert subtotal.quantize(Decimal("0.01")) == Decimal("90.00")
    # Tax recomputed on discounted netto (19% of 90 == 17.10; 1.90 less).
    assert tax_amount.quantize(Decimal("0.01")) == Decimal("17.10")

    # Per-line tax_breakdown preserved on the resource (non-discount) line.
    lines = db.session.query(InvoiceLineItem).filter_by(invoice_id=invoice.id).all()
    resource_line = next(
        line for line in lines if not (line.extra_data or {}).get("discount")
    )
    assert resource_line.tax_breakdown == [
        {
            "code": resource.taxes[0].code,
            "name": "VAT",
            "rate": 19.0,
            "amount": 19.0,
        }
    ]

    # D-DiscountLineShape: the discount is a negative-amount CUSTOM line item
    # (mirrors shop), not an invoice-level field.
    discount_line = next(
        line for line in lines if (line.extra_data or {}).get("discount")
    )
    assert discount_line.total_price == Decimal("-11.90")
    update_core_settings({"prices_mode_in_db": "NETTO"})


def test_discount_line_tax_breakdown_reconciles_with_invoice(
    db, client, discount_ready, monkeypatch
):
    """S96.1 display reconciliation: per-line tax_breakdown sums to invoice tax.

    The generic invoice view aggregates each line's ``tax_breakdown`` for its
    per-rate rows. So across ALL line items (resource + negative discount line):
      - Σ line.net_amount == invoice.subtotal
      - Σ line.tax_amount == invoice.tax_amount
      - Σ (per-rate tax_breakdown amounts) == invoice.tax_amount (by code+rate)
    The discount line must carry a NEGATIVE per-rate tax_breakdown so the
    aggregated breakdown (19.00 resource − 1.90 discount == 17.10) reconciles
    with invoice.total_amount == 107.10.
    """
    from plugins.discount.discount.models.discount import DiscountScope, DiscountType

    update_core_settings({"prices_mode_in_db": "NETTO"})
    user = _make_user(db)
    resource = _make_taxed_resource(db, price="100.00", rate="19.00")
    _make_coupon(
        db,
        code="BOOKREC",
        scope=DiscountScope.BOOKING,
        dtype=DiscountType.FIXED_AMOUNT,
        value="11.90",
    )
    _auth(monkeypatch, user)
    start_at, end_at = _slot()

    resp = client.post(
        "/api/v1/booking/checkout",
        json={
            "resource_slug": resource.slug,
            "start_at": start_at,
            "end_at": end_at,
            "coupon_code": "BOOKREC",
        },
        headers={"Authorization": "Bearer valid"},
    )

    assert resp.status_code == 201, resp.get_json()
    invoice = db.session.get(UserInvoice, resp.get_json()["invoice_id"])
    lines = db.session.query(InvoiceLineItem).filter_by(invoice_id=invoice.id).all()

    invoice_subtotal = Decimal(str(invoice.subtotal)).quantize(Decimal("0.01"))
    invoice_tax = Decimal(str(invoice.tax_amount)).quantize(Decimal("0.01"))
    invoice_total = Decimal(str(invoice.total_amount)).quantize(Decimal("0.01"))

    # Σ line.net_amount == invoice.subtotal (90.00 = 100.00 + (-10.00)).
    net_sum = sum(
        (Decimal(str(line.net_amount)) for line in lines), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    assert net_sum == invoice_subtotal == Decimal("90.00")

    # Σ line.tax_amount == invoice.tax_amount (17.10 = 19.00 + (-1.90)).
    tax_sum = sum(
        (Decimal(str(line.tax_amount)) for line in lines), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    assert tax_sum == invoice_tax == Decimal("17.10")

    # Σ per-rate tax_breakdown across lines, grouped by code+rate, == invoice tax.
    by_rate: dict[tuple[str, float], Decimal] = {}
    for line in lines:
        for entry in line.tax_breakdown or []:
            key = (entry["code"], entry["rate"])
            by_rate[key] = by_rate.get(key, Decimal("0.00")) + Decimal(
                str(entry["amount"])
            )
    code = resource.taxes[0].code
    assert {k: v.quantize(Decimal("0.01")) for k, v in by_rate.items()} == {
        (code, 19.0): Decimal("17.10")
    }
    assert (
        sum(by_rate.values(), Decimal("0.00")).quantize(Decimal("0.01")) == invoice_tax
    )

    # Reconciles with the gross total.
    assert (invoice_subtotal + invoice_tax) == invoice_total == Decimal("107.10")

    # The discount line carries the negative per-rate breakdown (−1.90 @ 19%).
    discount_line = next(
        line for line in lines if (line.extra_data or {}).get("discount")
    )
    assert discount_line.tax_breakdown == [
        {"code": code, "name": "VAT", "rate": 19.0, "amount": -1.9}
    ]
    assert Decimal(str(discount_line.net_amount)) == Decimal("-10.00")
    assert Decimal(str(discount_line.tax_amount)) == Decimal("-1.90")
    assert discount_line.total_price == Decimal("-11.90")
    assert discount_line.extra_data["coupon_code"] == "BOOKREC"
    update_core_settings({"prices_mode_in_db": "NETTO"})


def test_untaxed_discounted_booking_totals_consistent(
    db, client, discount_ready, monkeypatch
):
    """Regression: an untaxed resource keeps tax_amount == 0 and net == gross."""
    from plugins.discount.discount.models.discount import DiscountScope, DiscountType

    update_core_settings({"prices_mode_in_db": "NETTO"})
    user = _make_user(db)
    from plugins.booking.booking.models.resource import BookableResource

    resource = BookableResource(
        id=uuid4(),
        name="Free Hall",
        slug=f"hall-{uuid4().hex[:8]}",
        capacity=10,
        price=100.0,
    )
    db.session.add(resource)
    db.session.commit()
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
    subtotal = Decimal(str(invoice.subtotal))
    tax_amount = Decimal(str(invoice.tax_amount))
    total_amount = Decimal(str(invoice.total_amount))

    assert tax_amount.quantize(Decimal("0.01")) == Decimal("0.00")
    assert subtotal.quantize(Decimal("0.01")) == Decimal("80.00")
    assert total_amount.quantize(Decimal("0.01")) == Decimal("80.00")
