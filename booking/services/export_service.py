"""ExportService — manual CSV/JSON export for booking data."""
import csv
import io
import json
from datetime import date

from plugins.booking.booking.repositories.resource_category_repository import (
    ResourceCategoryRepository,
)
from plugins.booking.booking.repositories.resource_repository import (
    ResourceRepository,
)
from plugins.booking.booking.repositories.booking_repository import (
    BookingRepository,
)


class ExportService:
    def __init__(
        self,
        category_repository: ResourceCategoryRepository,
        resource_repository: ResourceRepository,
        booking_repository: BookingRepository,
    ):
        self.category_repository = category_repository
        self.resource_repository = resource_repository
        self.booking_repository = booking_repository

    def export_categories(self, export_format: str = "csv") -> str:
        categories = self.category_repository.find_all(active_only=False)
        records = [category.to_dict() for category in categories]
        if export_format == "json":
            return json.dumps(records, indent=2, default=str)
        return self._to_csv(
            records, ["id", "name", "slug", "description", "is_active", "sort_order"]
        )

    def export_resources(self, export_format: str = "csv") -> str:
        resources = self.resource_repository.find_all(active_only=False)
        records = [resource.to_dict() for resource in resources]
        if export_format == "json":
            return json.dumps(records, indent=2, default=str)
        fields = [
            "id",
            "name",
            "slug",
            "resource_type",
            "capacity",
            "slot_duration_minutes",
            "price",
            "currency",
            "price_unit",
            "is_active",
        ]
        return self._to_csv(records, fields)

    def export_bookings(
        self,
        export_format: str = "csv",
        date_from: date = None,
        date_to: date = None,
        status: str = None,
    ) -> str:
        bookings = self.booking_repository.find_by_user(None)  # all bookings
        records = [booking.to_dict() for booking in bookings]

        if date_from:
            records = [
                record
                for record in records
                if record.get("start_at", "") >= date_from.isoformat()
            ]
        if date_to:
            records = [
                record
                for record in records
                if record.get("start_at", "") <= date_to.isoformat()
            ]
        if status:
            statuses = [s.strip() for s in status.split(",")]
            records = [record for record in records if record.get("status") in statuses]

        if export_format == "json":
            return json.dumps(records, indent=2, default=str)
        fields = [
            "id",
            "resource_id",
            "user_id",
            "start_at",
            "end_at",
            "status",
            "quantity",
            "invoice_id",
        ]
        return self._to_csv(records, fields)

    @staticmethod
    def _to_csv(records: list, fields: list) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
        return output.getvalue()
