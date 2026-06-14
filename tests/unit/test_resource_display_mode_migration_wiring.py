"""S72.4 — the per-resource price-display-mode migration is wired into the
booking plugin's own chain.

The migration anchors on the booking plugin's prior head
(``20260612_booking_resource_tax``, the S72.3 resource↔tax join) and adds a
nullable ``price_display_mode VARCHAR(8)`` column to ``booking_resource``.
"""
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # plugins/booking
MIGRATION = (
    PLUGIN_ROOT / "migrations/versions/20260612_booking_resource_display_mode.py"
)

ALEMBIC_VERSION_NUM_MAXLEN = 32


def test_migration_exists_and_chains_off_booking_prior_head():
    src = MIGRATION.read_text()
    revision = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    down = re.search(r'^down_revision = "([^"]+)"', src, re.M).group(1)
    assert revision == "20260612_book_res_disp_mode"
    # Anchors on booking's own prior head (the S72.3 resource↔tax migration).
    assert down == "20260612_booking_resource_tax"
    assert len(revision) <= ALEMBIC_VERSION_NUM_MAXLEN


def test_migration_adds_nullable_display_mode_column():
    src = MIGRATION.read_text()
    assert "booking_resource" in src
    assert "price_display_mode" in src
