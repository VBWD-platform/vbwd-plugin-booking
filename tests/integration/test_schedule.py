"""Integration tests for booking schedule & slot blocking.

Tests:
- Schedule endpoint returns slots with correct statuses
- Block/unblock slot CRUD
- Blocked slots excluded from user-facing availability
- Copy schedule to other resources
"""
import pytest
import uuid


@pytest.fixture(autouse=True)
def admin_token(client, db):
    """Log in as admin and return JWT token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminPass123@"},
    )
    if resp.status_code != 200:
        pytest.skip("Admin user not available in test DB")
    data = resp.get_json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def test_resource(client, db, auth_headers):
    """Create a test resource with a schedule."""
    slug = f"schedule-test-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/admin/booking/resources",
        json={
            "name": "Schedule Test Resource",
            "slug": slug,
            "capacity": 1,
            "price": "50.00",
            "slot_duration_minutes": 30,
            "availability": {
                "schedule": {
                    "mon": [{"start": "09:00", "end": "12:00"}],
                    "tue": [{"start": "09:00", "end": "12:00"}],
                    "wed": [{"start": "09:00", "end": "12:00"}],
                    "thu": [{"start": "09:00", "end": "12:00"}],
                    "fri": [{"start": "09:00", "end": "12:00"}],
                    "sat": [],
                    "sun": [],
                },
                "lead_time_hours": 0,
                "max_advance_days": 365,
            },
            "config": {"buffer_minutes": 10},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.get_json()


class TestScheduleEndpoint:
    """GET /admin/booking/resources/:id/schedule returns slot grid."""

    def test_schedule_returns_slots_for_weekday(
        self, client, db, auth_headers, test_resource
    ):
        # Monday 2026-06-01
        resp = client.get(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/schedule"
            f"?date_from=2026-06-01&date_to=2026-06-01",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["days"]) == 1
        day = data["days"][0]
        assert day["date"] == "2026-06-01"
        assert day["closed"] is False
        assert len(day["slots"]) > 0
        assert all(slot["status"] == "available" for slot in day["slots"])

    def test_schedule_returns_closed_for_weekend(
        self, client, db, auth_headers, test_resource
    ):
        # Saturday 2026-06-06
        resp = client.get(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/schedule"
            f"?date_from=2026-06-06&date_to=2026-06-06",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        day = resp.get_json()["days"][0]
        assert day["closed"] is True
        assert day["slots"] == []

    def test_schedule_shows_blocked_slot(self, client, db, auth_headers, test_resource):
        # Block a slot
        client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/block-slot",
            json={"date": "2026-06-01", "start": "09:00", "end": "09:30"},
            headers=auth_headers,
        )

        # Check schedule
        resp = client.get(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/schedule"
            f"?date_from=2026-06-01&date_to=2026-06-01",
            headers=auth_headers,
        )
        slots = resp.get_json()["days"][0]["slots"]
        first_slot = slots[0]
        assert first_slot["start"] == "09:00"
        assert first_slot["status"] == "blocked"
        assert "block_id" in first_slot


class TestBlockSlot:
    """POST/DELETE block-slot CRUD."""

    def test_block_slot_creates_block(self, client, db, auth_headers, test_resource):
        resp = client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/block-slot",
            json={
                "date": "2026-06-02",
                "start": "10:00",
                "end": "10:30",
                "reason": "Phone booking",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["start_time"] == "10:00"
        assert data["reason"] == "Phone booking"

    def test_unblock_slot_removes_block(self, client, db, auth_headers, test_resource):
        # Create block
        create_resp = client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/block-slot",
            json={"date": "2026-06-02", "start": "11:00", "end": "11:30"},
            headers=auth_headers,
        )
        block_id = create_resp.get_json()["id"]

        # Delete block
        delete_resp = client.delete(
            f"/api/v1/admin/booking/resources/{test_resource['id']}"
            f"/block-slot/{block_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["unblocked"] is True

    def test_block_requires_auth(self, client, db, test_resource):
        resp = client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/block-slot",
            json={"date": "2026-06-02", "start": "09:00", "end": "09:30"},
        )
        assert resp.status_code == 401


class TestBlockedExcludedFromAvailability:
    """Blocked slots must not appear in user-facing availability."""

    def test_blocked_slot_excluded_from_public_availability(
        self, client, db, auth_headers, test_resource
    ):
        slug = test_resource["slug"]

        # Get availability before blocking
        before_resp = client.get(
            f"/api/v1/booking/resources/{slug}/availability?date=2026-06-01"
        )
        before_slots = before_resp.get_json()["slots"]
        before_count = len(before_slots)
        assert before_count > 0

        # Block the first slot
        first_slot = before_slots[0]
        client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/block-slot",
            json={
                "date": "2026-06-01",
                "start": first_slot["start"],
                "end": first_slot["end"],
            },
            headers=auth_headers,
        )

        # Get availability after blocking
        after_resp = client.get(
            f"/api/v1/booking/resources/{slug}/availability?date=2026-06-01"
        )
        after_slots = after_resp.get_json()["slots"]
        assert len(after_slots) == before_count - 1
        assert all(s["start"] != first_slot["start"] for s in after_slots)


class TestCopySchedule:
    """POST copy-schedule copies availability to other resources."""

    def test_copy_schedule_to_target_resource(
        self, client, db, auth_headers, test_resource
    ):
        # Create a target resource with empty schedule
        target_slug = f"copy-target-{uuid.uuid4().hex[:8]}"
        target_resp = client.post(
            "/api/v1/admin/booking/resources",
            json={
                "name": "Copy Target",
                "slug": target_slug,
                "capacity": 1,
                "price": "30.00",
                "slot_duration_minutes": 30,
            },
            headers=auth_headers,
        )
        target_id = target_resp.get_json()["id"]

        # Copy schedule from source to target
        copy_resp = client.post(
            f"/api/v1/admin/booking/resources/{test_resource['id']}/copy-schedule",
            json={"target_resource_ids": [target_id]},
            headers=auth_headers,
        )
        assert copy_resp.status_code == 200
        assert copy_resp.get_json()["copied"] == 1

        # Verify target has schedule
        schedule_resp = client.get(
            f"/api/v1/admin/booking/resources/{target_id}/schedule"
            f"?date_from=2026-06-01&date_to=2026-06-01",
            headers=auth_headers,
        )
        target_day = schedule_resp.get_json()["days"][0]
        assert len(target_day["slots"]) > 0
