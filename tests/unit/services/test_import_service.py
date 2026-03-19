"""Unit tests for ImportService."""
from unittest.mock import MagicMock

from plugins.booking.booking.services.import_service import ImportService


class TestImportCategories:
    def test_creates_new_category_from_csv(self):
        category_repo = MagicMock()
        category_repo.find_by_slug.return_value = None
        service = ImportService(category_repo, MagicMock())

        csv_content = "name,slug,description\nMedical,medical,Doctors"
        result = service.import_categories(csv_content, "csv")

        assert result["created"] == 1
        assert result["updated"] == 0
        category_repo.save.assert_called_once()

    def test_updates_existing_category(self):
        existing = MagicMock()
        existing.name = "Old Name"
        category_repo = MagicMock()
        category_repo.find_by_slug.return_value = existing
        service = ImportService(category_repo, MagicMock())

        csv_content = "name,slug\nNew Name,medical"
        result = service.import_categories(csv_content, "csv")

        assert result["created"] == 0
        assert result["updated"] == 1
        assert existing.name == "New Name"

    def test_reports_error_for_missing_slug(self):
        category_repo = MagicMock()
        service = ImportService(category_repo, MagicMock())

        csv_content = "name,slug\nNoSlug,"
        result = service.import_categories(csv_content, "csv")

        assert result["created"] == 0
        assert len(result["errors"]) == 1

    def test_import_json_format(self):
        category_repo = MagicMock()
        category_repo.find_by_slug.return_value = None
        service = ImportService(category_repo, MagicMock())

        json_content = '[{"name": "Events", "slug": "events"}]'
        result = service.import_categories(json_content, "json")

        assert result["created"] == 1


class TestImportResources:
    def test_creates_new_resource(self):
        resource_repo = MagicMock()
        resource_repo.find_by_slug.return_value = None
        service = ImportService(MagicMock(), resource_repo)

        csv_content = (
            "name,slug,resource_type,price\nDr. Smith,dr-smith,specialist,50.00"
        )
        result = service.import_resources(csv_content, "csv")

        assert result["created"] == 1
        resource_repo.save.assert_called_once()

    def test_updates_existing_resource(self):
        existing = MagicMock()
        existing.name = "Old"
        resource_repo = MagicMock()
        resource_repo.find_by_slug.return_value = existing
        service = ImportService(MagicMock(), resource_repo)

        csv_content = "name,slug,price\nUpdated,dr-smith,75.00"
        result = service.import_resources(csv_content, "csv")

        assert result["updated"] == 1
        assert existing.name == "Updated"

    def test_reports_error_for_missing_slug(self):
        resource_repo = MagicMock()
        service = ImportService(MagicMock(), resource_repo)

        csv_content = "name,slug\nNoSlug,"
        result = service.import_resources(csv_content, "csv")

        assert len(result["errors"]) == 1
