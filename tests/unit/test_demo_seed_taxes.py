"""Unit specs for the booking demo-seed tax linking (S85.4).

The booking catalog seeder must link the canonical demo VAT to its demo
resources so the price disclosure shows gross > net. The link is idempotent and
runs independently of resource creation (resources are skipped on a re-run, but
the tax link must still be ensured), and the tax is resolved by code through the
core linker — no cross-plugin import.
"""
from unittest.mock import MagicMock, patch

from plugins.booking.booking import demo_seed


def test_link_resource_taxes_links_canonical_vat_to_demo_resources():
    """Every present demo resource gets the canonical VAT linked."""
    session = MagicMock()
    resources = {}

    def _filter_by(**kwargs):
        result = MagicMock()
        result.first.return_value = resources.get(kwargs.get("slug"))
        return result

    session.query.return_value.filter_by.side_effect = _filter_by

    demo_slugs = [item["slug"] for item in demo_seed.RESOURCES]
    resources[demo_slugs[0]] = MagicMock(taxes=[])
    resources[demo_slugs[1]] = MagicMock(taxes=[])

    with patch.object(demo_seed, "link_demo_tax") as link_demo_tax:
        demo_seed._link_resource_taxes(session)

    linked = []
    for call in link_demo_tax.call_args_list:
        linked.extend(call.args[1])
    assert set(linked) == {resources[demo_slugs[0]], resources[demo_slugs[1]]}


def test_link_resource_taxes_noop_when_no_resources_present():
    """When no demo resource rows exist the linker is not called with any."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None

    with patch.object(demo_seed, "link_demo_tax") as link_demo_tax:
        demo_seed._link_resource_taxes(session)

    linked = []
    for call in link_demo_tax.call_args_list:
        linked.extend(call.args[1])
    assert linked == []
