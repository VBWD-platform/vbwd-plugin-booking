"""Add booking_resource_slot_block table.

Revision ID: 20260322_slot_blocks
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

revision = "20260322_slot_blocks"
down_revision = "20260321_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "booking_resource_slot_block" not in inspector.get_table_names():
        op.create_table(
            "booking_resource_slot_block",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "resource_id",
                UUID(as_uuid=True),
                sa.ForeignKey("booking_resource.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("date", sa.Date, nullable=False),
            sa.Column("start_time", sa.String(5), nullable=False),
            sa.Column("end_time", sa.String(5), nullable=False),
            sa.Column("reason", sa.String(255), nullable=True),
            sa.Column(
                "blocked_by",
                UUID(as_uuid=True),
                sa.ForeignKey("user.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("version", sa.Integer, default=0),
        )
        op.create_index(
            "ix_slot_block_resource_date",
            "booking_resource_slot_block",
            ["resource_id", "date"],
        )


def downgrade() -> None:
    op.drop_table("booking_resource_slot_block")
