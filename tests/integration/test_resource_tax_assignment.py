"""S72.3 — resource↔tax M2M persistence + FK ON DELETE RESTRICT (integration).

Covers the contract end-to-end against the real schema:
- assigning ``tax_ids`` persists the M2M (replace-set, dedupe),
- ``to_dict()`` reflects assigned ``tax_ids``/``taxes``,
- deleting a tax that is referenced by a resource is blocked by the DB
  (``ON DELETE RESTRICT`` → IntegrityError), not silently cascaded.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from vbwd.models.tax import Tax
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.repositories.resource_repository import ResourceRepository


def _tax(db, code: str, rate: str = "19.00", is_active: bool = True) -> Tax:
    tax = Tax(
        name=f"Tax {code}",
        code=code,
        rate=Decimal(rate),
        is_active=is_active,
    )
    db.session.add(tax)
    db.session.flush()
    return tax


def _resource(db, slug: str) -> BookableResource:
    resource = BookableResource(
        id=uuid4(),
        name=slug.title(),
        slug=slug,
        price=Decimal("100.00"),
        is_active=True,
    )
    db.session.add(resource)
    db.session.flush()
    return resource


def test_assign_taxes_persists_m2m_and_to_dict_reflects_it(db):
    vat = _tax(db, f"VAT_{uuid4().hex[:6]}", "19.00")
    reduced = _tax(db, f"RED_{uuid4().hex[:6]}", "7.00")
    resource = _resource(db, f"res-{uuid4().hex[:6]}")

    resource.taxes = [vat, reduced]
    db.session.commit()

    reloaded = ResourceRepository(db.session).find_by_id(resource.id)
    assert {tax.id for tax in reloaded.taxes} == {vat.id, reduced.id}
    data = reloaded.to_dict()
    assert set(data["tax_ids"]) == {str(vat.id), str(reduced.id)}
    assert {tax["code"] for tax in data["taxes"]} == {vat.code, reduced.code}


def test_replace_set_swaps_assigned_taxes(db):
    first = _tax(db, f"A_{uuid4().hex[:6]}")
    second = _tax(db, f"B_{uuid4().hex[:6]}")
    resource = _resource(db, f"swap-{uuid4().hex[:6]}")

    resource.taxes = [first]
    db.session.commit()

    # Replace-set: the new assignment fully supersedes the old one.
    reloaded = ResourceRepository(db.session).find_by_id(resource.id)
    reloaded.taxes = [second]
    db.session.commit()

    again = ResourceRepository(db.session).find_by_id(resource.id)
    assert {tax.id for tax in again.taxes} == {second.id}


def test_deleting_in_use_tax_is_blocked_by_restrict(db):
    vat = _tax(db, f"INUSE_{uuid4().hex[:6]}")
    resource = _resource(db, f"inuse-{uuid4().hex[:6]}")
    resource.taxes = [vat]
    db.session.commit()

    db.session.delete(vat)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # The resource still references the tax — nothing was cascaded.
    reloaded = ResourceRepository(db.session).find_by_id(resource.id)
    assert {tax.id for tax in reloaded.taxes} == {vat.id}
