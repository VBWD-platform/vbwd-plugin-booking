"""Integration tests for booking custom schemas.

Verifies:
- Schema table exists after migration
- Resource type table does NOT exist (dropped by migration)
- Schema CRUD persists across requests
- Resource links to schema and inherits type label + custom fields
- Resource without schema shows "unclassified"
"""
import pytest
import uuid


@pytest.fixture(autouse=True)
def admin_token(client, db):
    """Log in as admin and return JWT token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "AdminPass123@",
        },
    )
    if resp.status_code != 200:
        pytest.skip("Admin user not available in test DB")
    data = resp.get_json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestSchemaMigration:
    """Verify the migration created the right tables and columns."""

    def test_custom_schema_table_exists(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'booking_custom_schema'"
            )
        )
        assert result.scalar() == 1

    def test_resource_type_table_dropped(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'booking_resource_type'"
            )
        )
        assert result.scalar() is None

    def test_resource_has_custom_schema_id_column(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'booking_resource' "
                "AND column_name = 'custom_schema_id'"
            )
        )
        assert result.scalar() == 1

    def test_resource_type_column_dropped(self, db):
        from sqlalchemy import text

        result = db.session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'booking_resource' "
                "AND column_name = 'resource_type'"
            )
        )
        assert result.scalar() is None


class TestSchemaCrud:
    """Schema CRUD persists across requests."""

    def test_create_schema(self, client, db, auth_headers):
        slug = f"test-schema-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={
                "name": "Test Schema",
                "slug": slug,
                "fields": [
                    {
                        "id": "field1",
                        "label": "Field One",
                        "type": "string",
                        "required": True,
                    },
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["slug"] == slug
        assert len(data["fields"]) == 1
        assert data["fields"][0]["label"] == "Field One"

    def test_create_then_get_schema(self, client, db, auth_headers):
        slug = f"test-get-{uuid.uuid4().hex[:8]}"
        create_resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={"name": "Get Test", "slug": slug, "fields": []},
            headers=auth_headers,
        )
        schema_id = create_resp.get_json()["id"]

        get_resp = client.get(
            f"/api/v1/admin/booking/schemas/{schema_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.get_json()["slug"] == slug

    def test_update_schema_fields(self, client, db, auth_headers):
        slug = f"test-update-{uuid.uuid4().hex[:8]}"
        create_resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={"name": "Update Test", "slug": slug, "fields": []},
            headers=auth_headers,
        )
        schema_id = create_resp.get_json()["id"]

        update_resp = client.put(
            f"/api/v1/admin/booking/schemas/{schema_id}",
            json={
                "fields": [
                    {
                        "id": "new_field",
                        "label": "New Field",
                        "type": "integer",
                        "required": False,
                    },
                ],
            },
            headers=auth_headers,
        )
        assert update_resp.status_code == 200
        assert len(update_resp.get_json()["fields"]) == 1

    def test_delete_schema(self, client, db, auth_headers):
        slug = f"test-delete-{uuid.uuid4().hex[:8]}"
        create_resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={"name": "Delete Test", "slug": slug, "fields": []},
            headers=auth_headers,
        )
        schema_id = create_resp.get_json()["id"]

        delete_resp = client.delete(
            f"/api/v1/admin/booking/schemas/{schema_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["deleted"] is True

    def test_list_schemas(self, client, db, auth_headers):
        resp = client.get(
            "/api/v1/admin/booking/schemas",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "schemas" in resp.get_json()

    def test_public_list_schemas(self, client, db):
        resp = client.get("/api/v1/booking/schemas")
        assert resp.status_code == 200
        assert "schemas" in resp.get_json()

    def test_create_schema_requires_auth(self, client, db):
        resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={"name": "No Auth", "slug": "no-auth", "fields": []},
        )
        assert resp.status_code == 401


class TestResourceSchemaRelation:
    """Resource inherits type label and custom fields from schema."""

    def test_resource_with_schema_returns_schema_slug_as_type(
        self, client, db, auth_headers
    ):
        # Create schema
        schema_resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={
                "name": "Doctor",
                "slug": f"doctor-{uuid.uuid4().hex[:8]}",
                "fields": [
                    {
                        "id": "symptoms",
                        "label": "Symptoms",
                        "type": "text",
                        "required": True,
                    },
                ],
            },
            headers=auth_headers,
        )
        schema_data = schema_resp.get_json()

        # Create resource with schema
        resource_resp = client.post(
            "/api/v1/admin/booking/resources",
            json={
                "name": "Dr. Test",
                "slug": f"dr-test-{uuid.uuid4().hex[:8]}",
                "custom_schema_id": schema_data["id"],
                "capacity": 1,
                "price": "50.00",
            },
            headers=auth_headers,
        )
        assert resource_resp.status_code == 201
        resource_data = resource_resp.get_json()
        assert resource_data["resource_type"] == schema_data["slug"]
        assert resource_data["resource_type_name"] == "Doctor"
        assert resource_data["custom_fields_schema"][0]["id"] == "symptoms"

    def test_resource_without_schema_shows_unclassified(self, client, db, auth_headers):
        resource_resp = client.post(
            "/api/v1/admin/booking/resources",
            json={
                "name": "Untyped Resource",
                "slug": f"untyped-{uuid.uuid4().hex[:8]}",
                "capacity": 1,
                "price": "10.00",
            },
            headers=auth_headers,
        )
        assert resource_resp.status_code == 201
        data = resource_resp.get_json()
        assert data["resource_type"] == "unclassified"
        assert data["resource_type_name"] == "Unclassified"

    def test_schema_fields_update_propagates_to_resource(
        self, client, db, auth_headers
    ):
        # Create schema with 1 field
        schema_slug = f"propagate-{uuid.uuid4().hex[:8]}"
        schema_resp = client.post(
            "/api/v1/admin/booking/schemas",
            json={
                "name": "Propagation Test",
                "slug": schema_slug,
                "fields": [
                    {
                        "id": "f1",
                        "label": "Field 1",
                        "type": "string",
                        "required": False,
                    },
                ],
            },
            headers=auth_headers,
        )
        schema_id = schema_resp.get_json()["id"]

        # Create resource
        resource_resp = client.post(
            "/api/v1/admin/booking/resources",
            json={
                "name": "Propagation Resource",
                "slug": f"prop-res-{uuid.uuid4().hex[:8]}",
                "custom_schema_id": schema_id,
                "capacity": 1,
                "price": "20.00",
            },
            headers=auth_headers,
        )
        resource_id = resource_resp.get_json()["id"]

        # Update schema — add second field
        client.put(
            f"/api/v1/admin/booking/schemas/{schema_id}",
            json={
                "fields": [
                    {
                        "id": "f1",
                        "label": "Field 1",
                        "type": "string",
                        "required": False,
                    },
                    {
                        "id": "f2",
                        "label": "Field 2",
                        "type": "boolean",
                        "required": True,
                    },
                ],
            },
            headers=auth_headers,
        )

        # Fetch resource — should now have 2 fields
        get_resp = client.get(
            f"/api/v1/admin/booking/resources/{resource_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        fields = get_resp.get_json()["custom_fields_schema"]
        assert len(fields) == 2
        assert fields[1]["id"] == "f2"
