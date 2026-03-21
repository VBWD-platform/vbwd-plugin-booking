"""Verify test infrastructure: DB tables exist, seeder works, login works."""
import pytest


class TestSetupCheck:
    """Sanity checks that the test DB and fixtures are working."""

    def test_tables_created(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE tablename LIKE 'booking%' "
                "ORDER BY tablename"
            )
        )
        tables = [row[0] for row in result]
        assert "booking_custom_schema" in tables
        assert "booking_resource" in tables

    def test_admin_user_seeded(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text("SELECT email FROM \"user\" WHERE email = 'admin@example.com'")
        )
        assert result.scalar() == "admin@example.com"

    def test_admin_login(self, client, db):
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@example.com",
                "password": "AdminPass123@",
            },
        )
        assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
        data = resp.get_json()
        token = data.get("access_token") or data.get("token")
        assert token is not None, f"No token in response: {data.keys()}"
