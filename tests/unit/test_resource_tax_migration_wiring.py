"""S72.3 — the resource↔tax join-table migration is wired into the booking plugin.

The migration lives in the booking plugin's own ``migrations/versions`` directory,
anchors on booking's own current head (``20260531_booking_prefix``) so the chain
stays linear and resolvable, and creates ``booking_resource_tax`` with an
``ON DELETE RESTRICT`` FK to the CORE ``vbwd_tax`` catalog and an
``ON DELETE CASCADE`` FK to ``booking_resource``.
"""
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # plugins/booking
MIGRATION = PLUGIN_ROOT / "migrations/versions/20260612_booking_resource_tax.py"

ALEMBIC_VERSION_NUM_MAXLEN = 32


def test_migration_exists_and_anchors_on_booking_head():
    src = MIGRATION.read_text()
    revision = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    down = re.search(r'^down_revision = "([^"]+)"', src, re.M).group(1)
    assert revision == "20260612_booking_resource_tax"
    # Anchors on booking's own current head (keeps the chain linear).
    assert down == "20260531_booking_prefix"
    assert len(revision) <= ALEMBIC_VERSION_NUM_MAXLEN


def test_migration_creates_join_table_with_restrict_and_cascade_fks():
    src = MIGRATION.read_text()
    assert "booking_resource_tax" in src
    assert "vbwd_tax.id" in src
    assert "RESTRICT" in src
    assert "booking_resource.id" in src
    assert "CASCADE" in src
