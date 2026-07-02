"""Vendor-mode — add ``booking_resource.vendor_id`` (nullable, indexed FK).

Adds the owning vendor's ``vbwd_user`` id to bookable resources. ``NULL`` is a
platform-owned resource (the classic single-owner booking). The FK is
``ON DELETE SET NULL`` so removing a user reverts their resources to the
platform rather than cascading a catalog delete; a btree index backs the
vendor's "my resources" filter.

Anchors on the booking plugin's own current head so the chain resolves with the
booking plugin alone (core stays standalone-resolvable).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260701_booking_resource_vendor_id"
down_revision = "20260613_booking_price_float"
branch_labels = None
depends_on = None

_TABLE = "booking_resource"
_COLUMN = "vendor_id"
_INDEX = "ix_booking_resource_vendor_id"
_FK = "fk_booking_resource_vendor_id_user"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column(_COLUMN, UUID(as_uuid=True), nullable=True))
    op.create_index(_INDEX, _TABLE, [_COLUMN])
    op.create_foreign_key(
        _FK,
        _TABLE,
        "vbwd_user",
        [_COLUMN],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
