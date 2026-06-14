"""S85.1 — booking price storage migration (D4/D5).

Widens ``booking_resource.price`` from ``Numeric(10, 2)`` to ``double precision``
(``db.Float``) — prices are full precision and never rounded in code (D4) — and
drops the redundant ``currency`` column (D5); the single source of truth for the
operating currency is the global ``default_currency`` core setting (S84).

Anchors on the booking plugin's own current head so the chain resolves with the
booking plugin alone. ``downgrade`` re-narrows to ``Numeric(10, 2)`` and re-adds
``currency``.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260613_booking_price_float"
down_revision = "20260612_book_res_disp_mode"
branch_labels = None
depends_on = None

RESOURCE_TABLE = "booking_resource"


def upgrade() -> None:
    op.alter_column(
        RESOURCE_TABLE,
        "price",
        type_=sa.Float(),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
        postgresql_using="price::double precision",
    )
    op.drop_column(RESOURCE_TABLE, "currency")


def downgrade() -> None:
    op.add_column(
        RESOURCE_TABLE,
        sa.Column("currency", sa.String(length=3), nullable=True, server_default="EUR"),
    )
    op.alter_column(
        RESOURCE_TABLE,
        "price",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Float(),
        existing_nullable=False,
        postgresql_using="price::numeric(10,2)",
    )
