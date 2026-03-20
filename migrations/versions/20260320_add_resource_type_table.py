"""Add booking_resource_type table.

Revision ID: 20260320_resource_type
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260320_resource_type"
down_revision = "20260319_booking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_resource_type",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, default=0),
    )
    op.create_index(
        "ix_booking_resource_type_slug", "booking_resource_type", ["slug"]
    )


def downgrade() -> None:
    op.drop_table("booking_resource_type")
