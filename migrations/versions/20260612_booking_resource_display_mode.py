"""S72.4 — per-resource netto/brutto price-display override.

Adds a nullable ``price_display_mode VARCHAR(8)`` column to ``booking_resource``.
``NULL`` inherits the global ``prices_display_mode`` core setting;
``"netto"``/``"brutto"`` override it.

Anchors on the booking plugin's own prior head (the S72.3 resource↔tax join) so
the migration resolves with the booking plugin alone (no cross-plugin anchor).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260612_book_res_disp_mode"
down_revision = "20260612_booking_resource_tax"
branch_labels = None
depends_on = None

TABLE = "booking_resource"
COLUMN = "price_display_mode"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
