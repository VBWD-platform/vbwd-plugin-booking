"""Create booking tables.

Revision ID: 20260319_booking
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260319_booking"
down_revision = None
branch_labels = ("booking",)
depends_on = None


def upgrade() -> None:
    # booking_resource_category
    op.create_table(
        "booking_resource_category",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, default=0),
        sa.ForeignKeyConstraint(["parent_id"], ["booking_resource_category.id"]),
    )
    op.create_index(
        "ix_booking_resource_category_slug", "booking_resource_category", ["slug"]
    )

    # booking_resource
    op.create_table(
        "booking_resource",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("slot_duration_minutes", sa.Integer, nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("price_unit", sa.String(50), server_default="per_slot"),
        sa.Column("availability", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("custom_fields_schema", sa.JSON, nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, default=0),
    )
    op.create_index("ix_booking_resource_slug", "booking_resource", ["slug"])
    op.create_index("ix_booking_resource_type", "booking_resource", ["resource_type"])

    # booking_resource_category_link
    op.create_table(
        "booking_resource_category_link",
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["booking_resource.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["booking_resource_category.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("resource_id", "category_id"),
    )

    # booking
    op.create_table(
        "booking",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=True),
        sa.Column("start_at", sa.DateTime, nullable=False),
        sa.Column("end_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="confirmed"),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("custom_fields", sa.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("admin_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, default=0),
        sa.ForeignKeyConstraint(["resource_id"], ["booking_resource.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["user_invoice.id"]),
    )
    op.create_index("ix_booking_resource_id", "booking", ["resource_id"])
    op.create_index("ix_booking_user_id", "booking", ["user_id"])
    op.create_index("ix_booking_invoice_id", "booking", ["invoice_id"])
    op.create_index("ix_booking_start_at", "booking", ["start_at"])


def downgrade() -> None:
    op.drop_table("booking")
    op.drop_table("booking_resource_category_link")
    op.drop_table("booking_resource")
    op.drop_table("booking_resource_category")
