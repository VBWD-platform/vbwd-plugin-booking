"""Unit tests for ExportService."""
import json
from unittest.mock import MagicMock

from plugins.booking.booking.services.export_service import ExportService


def _make_category(name="Medical", slug="medical"):
    category = MagicMock()
    category.to_dict.return_value = {
        "id": "cat-1",
        "name": name,
        "slug": slug,
        "description": "Test",
        "is_active": True,
        "sort_order": 0,
    }
    return category


def _make_resource(name="Dr. Smith", slug="dr-smith"):
    resource = MagicMock()
    resource.to_dict.return_value = {
        "id": "res-1",
        "name": name,
        "slug": slug,
        "resource_type": "specialist",
        "capacity": 1,
        "price": "50.00",
        "is_active": True,
    }
    return resource


class TestExportCategories:
    def test_export_csv_returns_header_and_rows(self):
        category_repo = MagicMock()
        category_repo.find_all.return_value = [_make_category()]
        service = ExportService(category_repo, MagicMock(), MagicMock())

        result = service.export_categories("csv")

        assert "name,slug" in result or "id,name" in result
        assert "Medical" in result
        assert "medical" in result

    def test_export_json_returns_valid_json(self):
        category_repo = MagicMock()
        category_repo.find_all.return_value = [_make_category()]
        service = ExportService(category_repo, MagicMock(), MagicMock())

        result = service.export_categories("json")

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert parsed[0]["name"] == "Medical"

    def test_export_empty_returns_header_only(self):
        category_repo = MagicMock()
        category_repo.find_all.return_value = []
        service = ExportService(category_repo, MagicMock(), MagicMock())

        result = service.export_categories("csv")

        lines = result.strip().split("\n")
        assert len(lines) == 1  # header only


class TestExportResources:
    def test_export_csv(self):
        resource_repo = MagicMock()
        resource_repo.find_all.return_value = [_make_resource()]
        service = ExportService(MagicMock(), resource_repo, MagicMock())

        result = service.export_resources("csv")

        assert "Dr. Smith" in result

    def test_export_json(self):
        resource_repo = MagicMock()
        resource_repo.find_all.return_value = [
            _make_resource(),
            _make_resource("Room A", "room-a"),
        ]
        service = ExportService(MagicMock(), resource_repo, MagicMock())

        result = service.export_resources("json")

        parsed = json.loads(result)
        assert len(parsed) == 2
