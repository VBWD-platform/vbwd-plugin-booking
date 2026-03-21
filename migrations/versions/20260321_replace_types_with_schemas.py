"""Replace resource types with custom schemas.

Revision ID: 20260321_schemas
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

revision = "20260321_schemas"
down_revision = "20260319_booking"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # 1. Create booking_custom_schema table
    if not _table_exists("booking_custom_schema"):
        op.create_table(
            "booking_custom_schema",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False, unique=True),
            sa.Column("fields", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("sort_order", sa.Integer, default=0),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("version", sa.Integer, default=0),
        )
        op.create_index(
            "ix_booking_custom_schema_slug", "booking_custom_schema", ["slug"]
        )

    # 2. Add custom_schema_id FK to booking_resource
    if not _column_exists("booking_resource", "custom_schema_id"):
        op.add_column(
            "booking_resource",
            sa.Column(
                "custom_schema_id",
                UUID(as_uuid=True),
                sa.ForeignKey("booking_custom_schema.id"),
                nullable=True,
            ),
        )

    # 3. Drop resource_type column if it exists (from original 20260319 migration)
    if _column_exists("booking_resource", "resource_type"):
        op.drop_index(
            "ix_booking_resource_type",
            table_name="booking_resource",
            if_exists=True,
        )
        op.drop_column("booking_resource", "resource_type")

    # 4. Drop booking_resource_type table if it exists (from deleted migration)
    if _table_exists("booking_resource_type"):
        op.drop_table("booking_resource_type")


def downgrade() -> None:
    # Recreate resource_type column
    if not _column_exists("booking_resource", "resource_type"):
        op.add_column(
            "booking_resource",
            sa.Column("resource_type", sa.String(100), nullable=True),
        )
        op.create_index(
            "ix_booking_resource_type", "booking_resource", ["resource_type"]
        )

    # Drop custom_schema_id FK
    if _column_exists("booking_resource", "custom_schema_id"):
        op.drop_column("booking_resource", "custom_schema_id")

    # Drop booking_custom_schema table
    if _table_exists("booking_custom_schema"):
        op.drop_table("booking_custom_schema")
