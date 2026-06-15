"""Unit: S89.1 Slice B load-test bulk seed for ``bookings`` (MagicMock repo).

``bookings`` is UUID-keyed and FK-heavy, so it overrides the seed seam rather
than reusing the slug-prefix path. This test pins the two risk points without a
DB:

* ``_loadtest_natural_key`` is a **deterministic UUID5** per index (the same
  index always maps to the same booking id ⇒ idempotency + ``--reset`` by id).
* ``_seed_row`` returns a VALID reservation — the deterministic id, the one
  shared ``loadtest-`` resource, the reused user id, and a deterministic
  non-overlapping slot.
* ``bulk_seed`` inserts through the repo's ``bulk_add`` (batched, not per-row),
  and is idempotent (an already-present deterministic id is skipped).

Engineering requirements (binding, restated): TDD-first; SOLID/DI/DRY; Liskov
(the override preserves the base seed contract); clean code; no overengineering.
Quality guard: ``bin/pre-commit-check.sh --plugin booking --full``.
"""
import uuid
from datetime import timedelta
from typing import List, Optional

from plugins.booking.booking.models.booking import Booking
from plugins.booking.booking.services.data_exchange.booking_exchangers import (
    _BookingsExchanger,
)

_SEED_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _FakeResource:
    """Stand-in for the one shared load-test ``BookableResource``."""

    def __init__(self) -> None:
        self.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        self.slug = _BookingsExchanger._SEED_RESOURCE_SLUG


class _FakeRepo:
    """Minimal repo honouring the seed's ``bulk_add`` hook (no DB)."""

    def __init__(self) -> None:
        self.added: List[Booking] = []
        self.bulk_calls = 0

    def bulk_add(self, instances: List[Booking]) -> None:
        self.bulk_calls += 1
        self.added.extend(instances)

    def add(self, instance: Booking) -> None:  # pragma: no cover - fallback
        self.added.append(instance)


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def _make_exchanger(
    repo: _FakeRepo, *, existing_ids: Optional[List[str]] = None
) -> _BookingsExchanger:
    exchanger = _BookingsExchanger(
        entity_key="bookings",
        label="Bookings",
        cluster="sales",
        natural_key="id",
        model_class=Booking,
        repository=repo,
        session=_FakeSession(),
        public_fields=["id", "resource_id", "user_id", "start_at", "end_at"],
        view_permission="booking.bookings.view",
        manage_permission="booking.bookings.manage",
    )
    # Stub the two DB-touching prerequisites so the unit test needs no DB: one
    # shared in-memory resource (reused on every call) + a fixed user id.
    shared_resource = _FakeResource()
    exchanger._ensure_seed_resource = lambda: shared_resource
    exchanger._resolve_seed_user_id = lambda: _SEED_USER_ID
    existing = set(existing_ids or [])
    exchanger._existing_loadtest_keys = lambda: set(existing)
    return exchanger


def test_loadtest_natural_key_is_a_deterministic_uuid() -> None:
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo)

    first = exchanger._loadtest_natural_key(7)
    again = exchanger._loadtest_natural_key(7)
    other = exchanger._loadtest_natural_key(8)

    # Stable per index (idempotency depends on this) and a parseable UUID.
    assert first == again
    assert first != other
    assert uuid.UUID(first)


def test_seed_row_is_a_valid_reservation() -> None:
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo)
    natural_value = exchanger._loadtest_natural_key(3)

    row = exchanger._seed_row(3, natural_value)

    assert row["id"] == natural_value
    assert row["resource_id"] == _FakeResource().id
    assert row["user_id"] == _SEED_USER_ID
    assert row["status"] == "confirmed"
    assert row["quantity"] == 1
    # A valid, non-zero-length slot of exactly one slot-duration.
    assert row["end_at"] - row["start_at"] == timedelta(
        minutes=_BookingsExchanger._SEED_SLOT_MINUTES
    )


def test_consecutive_indices_get_non_overlapping_slots() -> None:
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo)

    first = exchanger._seed_row(0, exchanger._loadtest_natural_key(0))
    second = exchanger._seed_row(1, exchanger._loadtest_natural_key(1))

    # Slot 1 starts exactly when slot 0 ends — adjacent, never overlapping.
    assert second["start_at"] == first["end_at"]


def test_build_instance_uses_the_one_shared_resource_and_user() -> None:
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo)

    booking = exchanger._build_instance(
        exchanger._seed_row(0, exchanger._loadtest_natural_key(0))
    )

    assert isinstance(booking, Booking)
    assert booking.resource_id == _FakeResource().id
    assert booking.user_id == _SEED_USER_ID


def test_bulk_seed_creates_count_rows_via_bulk_add() -> None:
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo)

    result = exchanger.bulk_seed(10, batch_size=4)

    assert result.created == 10
    assert result.skipped == 0
    assert len(repo.added) == 10
    # Batched insert path was used (not a single giant transaction / per-row add).
    assert repo.bulk_calls >= 1
    assert all(isinstance(item, Booking) for item in repo.added)


def test_bulk_seed_is_idempotent_by_deterministic_id() -> None:
    # Every deterministic id already present ⇒ all skipped, nothing added.
    existing = _all_loadtest_ids(10)
    repo = _FakeRepo()
    exchanger = _make_exchanger(repo, existing_ids=existing)

    result = exchanger.bulk_seed(10)

    assert result.created == 0
    assert result.skipped == 10
    assert repo.added == []


def _all_loadtest_ids(count: int) -> List[str]:
    probe = _make_exchanger(_FakeRepo())
    return [probe._loadtest_natural_key(index) for index in range(count)]
