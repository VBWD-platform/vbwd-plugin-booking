"""S85.2 — booking invoice charges ``Price.brutto`` and records the breakdown.

``BookingInvoiceService`` derives the charged amount from
``PriceFactory(...).brutto`` (D8). The line item persists the netto + per-tax
breakdown (in ``extra_data``; invoice money columns stay ``Numeric(10,2)`` and
round at issue time). Flipping the global ``prices_mode_in_db`` changes the
recorded amount for the SAME stored double.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from vbwd.models.enums import UserRole, UserStatus
from vbwd.models.tax import Tax
from vbwd.models.user import User
from vbwd.services.core_settings_store import update_core_settings
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.services.booking_invoice_service import (
    BookingInvoiceService,
)


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


def _taxed_resource(db, stored_price):
    tax = Tax(name="VAT", code=f"VAT_{uuid4().hex[:6]}", rate=Decimal("19.00"))
    resource = BookableResource(
        id=uuid4(),
        name="Tennis Court",
        slug=f"court-{uuid4().hex[:8]}",
        capacity=10,
        price=float(stored_price),
    )
    db.session.add_all([tax, resource])
    db.session.flush()
    resource.taxes = [tax]
    db.session.commit()
    return resource


def _service(app, db):
    return BookingInvoiceService(
        db.session,
        price_factory=app.container.price_factory(),
    )


def _invoice_for(app, db, resource):
    start = datetime.utcnow() + timedelta(days=1)
    invoice = _service(app, db).create_checkout_invoice(
        user_id=_make_user(db).id,
        resource=resource,
        start_at=start,
        end_at=start + timedelta(hours=1),
        quantity=1,
    )
    db.session.commit()
    return invoice


def test_netto_mode_charges_gross_total(app, db):
    update_core_settings({"prices_mode_in_db": "NETTO"})
    resource = _taxed_resource(db, Decimal("100.00"))

    invoice = _invoice_for(app, db, resource)

    assert Decimal(str(invoice.total_amount)).quantize(Decimal("0.01")) == Decimal(
        "119.00"
    )


def test_brutto_mode_charges_stored_double_as_gross(app, db):
    update_core_settings({"prices_mode_in_db": "BRUTTO"})
    resource = _taxed_resource(db, Decimal("119.00"))

    invoice = _invoice_for(app, db, resource)

    assert Decimal(str(invoice.total_amount)).quantize(Decimal("0.01")) == Decimal(
        "119.00"
    )
    update_core_settings({"prices_mode_in_db": "NETTO"})


def test_mode_flip_changes_charged_total_for_same_double(app, db):
    update_core_settings({"prices_mode_in_db": "NETTO"})
    netto_invoice = _invoice_for(app, db, _taxed_resource(db, Decimal("100.00")))
    netto_total = Decimal(str(netto_invoice.total_amount))

    update_core_settings({"prices_mode_in_db": "BRUTTO"})
    brutto_invoice = _invoice_for(app, db, _taxed_resource(db, Decimal("100.00")))
    brutto_total = Decimal(str(brutto_invoice.total_amount))

    assert netto_total != brutto_total
    update_core_settings({"prices_mode_in_db": "NETTO"})


def test_line_item_records_net_and_tax_breakdown(app, db):
    update_core_settings({"prices_mode_in_db": "NETTO"})
    resource = _taxed_resource(db, Decimal("100.00"))

    invoice = _invoice_for(app, db, resource)

    from vbwd.models.invoice_line_item import InvoiceLineItem

    line = db.session.query(InvoiceLineItem).filter_by(invoice_id=invoice.id).first()
    breakdown = line.extra_data["price_breakdown"]
    net = Decimal(str(breakdown["netto"]))
    tax_sum = sum(Decimal(str(tax["amount"])) for tax in breakdown["taxes"])
    gross = Decimal(str(line.total_price))
    assert (net + tax_sum).quantize(Decimal("0.01")) == gross.quantize(Decimal("0.01"))
