"""S72.3 — resource↔tax M2M join table.

Creates ``booking_resource_tax`` linking ``booking_resource`` to the CORE tax
catalog (``vbwd_tax``). The ``tax_id`` FK is ``ON DELETE RESTRICT`` so deleting a
tax that is assigned to a resource is rejected by the database (a clean block,
never a silent cascade); ``resource_id`` is ``ON DELETE CASCADE`` so deleting a
resource tidies its own links.

Anchors on booking's own current head (``20260531_booking_prefix``) so the
plugin chain stays linear and resolvable. ``vbwd_tax`` ships in the core
monolith, so the referenced table is always present.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260612_booking_resource_tax"
down_revision = "20260531_booking_prefix"
branch_labels = None
depends_on = None

TABLE = "booking_resource_tax"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "resource_id",
            UUID(as_uuid=True),
            sa.ForeignKey("booking_resource.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tax_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vbwd_tax.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
