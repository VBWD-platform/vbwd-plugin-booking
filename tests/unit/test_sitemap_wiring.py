"""Booking → cms sitemap wiring (S154 D3: cms is an OPTIONAL dependency).

Booking registers its resource provider into cms's sitemap registry on enable
and removes it on disable; with cms absent, both are silent no-ops so booking
keeps working stand-alone.
"""
import json
import sys
import types
from pathlib import Path

from plugins.booking import BookingPlugin, cms_sitemap_registry

CMS_SEO_REGISTRY_MODULE = "plugins.cms.src.services.seo_registry"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]


class FakeSitemapRegistry(types.SimpleNamespace):
    """The two registry functions + ``SitemapEntry`` booking relies on."""

    def __init__(self):
        super().__init__(providers={})
        self.SitemapEntry = object

    def register_sitemap_provider(self, provider):
        self.providers[provider.name] = provider

    def unregister_sitemap_provider(self, provider):
        self.providers.pop(provider.name, None)


def test_enable_registers_and_disable_unregisters_the_resource_provider():
    registry = FakeSitemapRegistry()
    plugin = BookingPlugin()

    plugin._register_sitemap_provider(registry)

    provider = registry.providers["booking-resources"]
    assert provider._entry_factory is registry.SitemapEntry

    plugin._unregister_sitemap_provider(registry)

    assert registry.providers == {}


def test_registry_is_none_when_cms_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, CMS_SEO_REGISTRY_MODULE, None)

    assert cms_sitemap_registry() is None


def test_wiring_is_a_no_op_without_cms():
    plugin = BookingPlugin()

    plugin._register_sitemap_provider(None)
    plugin._unregister_sitemap_provider(None)


def test_seo_index_resources_ships_in_config_and_admin_config():
    config = json.loads((PLUGIN_ROOT / "config.json").read_text())
    admin_config = json.loads((PLUGIN_ROOT / "admin-config.json").read_text())

    assert config["seo_index_resources"]["default"] is True
    admin_field_keys = {
        field["key"] for tab in admin_config["tabs"] for field in tab["fields"]
    }
    assert "seo_index_resources" in admin_field_keys
