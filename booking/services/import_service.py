"""ImportService — CSV/JSON import for categories and resources (upsert)."""
import csv
import io
import json
from decimal import Decimal

from plugins.booking.booking.models.resource_category import BookableResourceCategory
from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.repositories.resource_category_repository import (
    ResourceCategoryRepository,
)
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
)


class ImportService:
    def __init__(
        self,
        category_repository: ResourceCategoryRepository,
        resource_repository: ResourceRepository,
    ):
        self.category_repository = category_repository
        self.resource_repository = resource_repository

    def import_categories(self, file_content: str, import_format: str = "csv") -> dict:
        """Import categories from CSV or JSON. Upsert by slug."""
        rows = self._parse(file_content, import_format)
        created, updated, errors = 0, 0, []

        for index, row in enumerate(rows):
            try:
                slug = row.get("slug", "").strip()
                if not slug:
                    errors.append({"row": index + 1, "error": "slug is required"})
                    continue

                existing = self.category_repository.find_by_slug(slug)
                if existing:
                    existing.name = row.get("name", existing.name)
                    existing.description = row.get("description", existing.description)
                    if "sort_order" in row:
                        existing.sort_order = int(row["sort_order"])
                    if "is_active" in row:
                        existing.is_active = str(row["is_active"]).lower() in (
                            "true",
                            "1",
                            "yes",
                        )
                    updated += 1
                else:
                    category = BookableResourceCategory()
                    category.name = row.get("name", slug)
                    category.slug = slug
                    category.description = row.get("description")
                    category.sort_order = int(row.get("sort_order", 0))
                    category.is_active = str(row.get("is_active", "true")).lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                    self.category_repository.save(category)
                    created += 1
            except Exception as error:
                errors.append({"row": index + 1, "error": str(error)})

        return {"created": created, "updated": updated, "errors": errors}

    def import_resources(self, file_content: str, import_format: str = "csv") -> dict:
        """Import resources from CSV or JSON. Upsert by slug."""
        rows = self._parse(file_content, import_format)
        created, updated, errors = 0, 0, []

        for index, row in enumerate(rows):
            try:
                slug = row.get("slug", "").strip()
                if not slug:
                    errors.append({"row": index + 1, "error": "slug is required"})
                    continue

                existing = self.resource_repository.find_by_slug(slug)
                if existing:
                    for field in ["name", "description", "resource_type", "price_unit"]:
                        if field in row:
                            setattr(existing, field, row[field])
                    if "capacity" in row:
                        existing.capacity = int(row["capacity"])
                    if "price" in row:
                        existing.price = Decimal(str(row["price"]))
                    if "is_active" in row:
                        existing.is_active = str(row["is_active"]).lower() in (
                            "true",
                            "1",
                            "yes",
                        )
                    updated += 1
                else:
                    resource = BookableResource()
                    resource.name = row.get("name", slug)
                    resource.slug = slug
                    resource.resource_type = row.get("resource_type", "specialist")
                    resource.capacity = int(row.get("capacity", 1))
                    resource.price = Decimal(str(row.get("price", "0.00")))
                    resource.currency = row.get("currency", "EUR")
                    resource.price_unit = row.get("price_unit", "per_slot")
                    resource.availability = {}
                    resource.is_active = str(row.get("is_active", "true")).lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                    self.resource_repository.save(resource)
                    created += 1
            except Exception as error:
                errors.append({"row": index + 1, "error": str(error)})

        return {"created": created, "updated": updated, "errors": errors}

    @staticmethod
    def _parse(file_content: str, import_format: str) -> list:
        if import_format == "json":
            data = json.loads(file_content)
            return data if isinstance(data, list) else [data]
        reader = csv.DictReader(io.StringIO(file_content))
        return list(reader)
