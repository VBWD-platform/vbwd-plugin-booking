"""Add booking_resource_image table.

Revision ID: 20260321_images
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

revision = "20260321_images"
down_revision = "20260321_schemas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "booking_resource_image" not in inspector.get_table_names():
        op.create_table(
            "booking_resource_image",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "resource_id",
                UUID(as_uuid=True),
                sa.ForeignKey("booking_resource.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "cms_image_id",
                UUID(as_uuid=True),
                sa.ForeignKey("cms_image.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("is_primary", sa.Boolean, default=False),
            sa.Column("sort_order", sa.Integer, default=0),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("version", sa.Integer, default=0),
            sa.UniqueConstraint("resource_id", "cms_image_id"),
        )
        op.create_index(
            "ix_booking_resource_image_resource_id",
            "booking_resource_image",
            ["resource_id"],
        )


def downgrade() -> None:
    op.drop_table("booking_resource_image")
