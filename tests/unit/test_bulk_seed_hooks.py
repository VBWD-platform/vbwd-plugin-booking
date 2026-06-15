"""Unit: S89.1 booking scale hooks (thin slice).

The ``bookings`` *seed* override is a deliberate follow-slice (see the module
docstring of ``booking_exchangers``): ``Booking``'s natural key is the UUID
``id`` (no settable ``loadtest-`` slug) and a booking requires a non-null core
``user_id`` FK + a valid resource + slot — it does not fit the slug-prefix seam
without bending it. This slice ships only the reusable scale hooks on the
repository adapter, which speed the slug-keyed ``booking_resources`` /
``booking_categories`` exports + ``--reset``. This test pins those hooks and
their UUID-natural-key safety.

Engineering requirements (binding, restated): TDD-first; SOLID/DI/DRY; Liskov;
clean code; no overengineering. Quality guard: ``bin/pre-commit-check.sh
--plugin booking --full``.
"""
from unittest.mock import MagicMock

from plugins.booking.booking.services.data_exchange.booking_exchangers import (
    _SessionModelRepository,
)
from plugins.booking.booking.models.resource import BookableResource


def test_bulk_add_uses_unit_of_work_add_all() -> None:
    session = MagicMock()
    repo = _SessionModelRepository(session, BookableResource, "slug")
    instances = [object(), object()]

    repo.bulk_add(instances)

    session.add_all.assert_called_once_with(instances)
    session.flush.assert_called_once_with()


def test_iter_rows_pages_with_yield_per() -> None:
    session = MagicMock()
    repo = _SessionModelRepository(session, BookableResource, "slug")

    repo.iter_rows(500)

    session.query.return_value.yield_per.assert_called_once_with(500)


def test_prefix_find_returns_empty_on_non_text_natural_key() -> None:
    # A UUID-keyed model (bookings) cannot match a string prefix; the hook must
    # return "no load-test rows" rather than crash the seed/reset caller.
    session = MagicMock()
    session.query.return_value.filter.side_effect = Exception("uuid like unsupported")
    repo = _SessionModelRepository(session, BookableResource, "id")

    assert repo.find_natural_keys_with_prefix("loadtest-") == []


def test_prefix_delete_returns_zero_on_non_text_natural_key() -> None:
    session = MagicMock()
    session.query.return_value.filter.side_effect = Exception("uuid like unsupported")
    repo = _SessionModelRepository(session, BookableResource, "id")

    assert repo.delete_natural_keys_with_prefix("loadtest-") == 0
