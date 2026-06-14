"""S85.1 — the booking price-storage migration is wired into the plugin's chain.

It anchors on the booking plugin's prior head (no cross-plugin anchor), widens
``booking_resource.price`` to ``Float``, and drops the redundant ``currency``.
"""
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # plugins/booking
MIGRATION = PLUGIN_ROOT / "migrations/versions/20260613_booking_price_float.py"

ALEMBIC_VERSION_NUM_MAXLEN = 32


def test_migration_exists_and_chains_off_booking_prior_head():
    src = MIGRATION.read_text()
    revision = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    down = re.search(r'^down_revision = "([^"]+)"', src, re.M).group(1)
    assert revision == "20260613_booking_price_float"
    # Anchors on booking's own prior head (the resource display-mode migration).
    assert down == "20260612_book_res_disp_mode"
    assert len(revision) <= ALEMBIC_VERSION_NUM_MAXLEN


def test_migration_widens_price_to_float_and_drops_currency():
    src = MIGRATION.read_text()
    assert "sa.Float()" in src
    assert 'drop_column(RESOURCE_TABLE, "currency")' in src
