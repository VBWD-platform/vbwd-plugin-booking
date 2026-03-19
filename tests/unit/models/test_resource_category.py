"""Unit tests for BookableResourceCategory model."""
from plugins.booking.booking.models.resource_category import BookableResourceCategory


class TestBookableResourceCategory:
    def test_create_category(self):
        category = BookableResourceCategory()
        category.name = "Medical"
        category.slug = "medical"
        category.description = "Medical appointments"

        assert category.name == "Medical"
        assert category.slug == "medical"

    def test_default_values(self):
        category = BookableResourceCategory()
        assert category.is_active is None or category.is_active is True
        assert category.sort_order is None or category.sort_order == 0

    def test_nested_category_parent_id(self):
        import uuid

        parent_id = uuid.uuid4()
        category = BookableResourceCategory()
        category.name = "Dentistry"
        category.slug = "dentistry"
        category.parent_id = parent_id

        assert category.parent_id == parent_id

    def test_config_stores_capture_policy(self):
        category = BookableResourceCategory()
        category.name = "Hotels"
        category.slug = "hotels"
        category.config = {
            "capture_policy": {
                "trigger": "before_start",
                "days_before_start": 10,
            },
            "cancellation_policy": {
                "tiers": [
                    {"days_before_start": 10, "refund_percent": 100},
                    {"days_before_start": 5, "refund_percent": 50},
                    {"days_before_start": 2, "refund_percent": 0},
                ],
            },
        }

        assert category.config["capture_policy"]["trigger"] == "before_start"
        assert len(category.config["cancellation_policy"]["tiers"]) == 3

    def test_to_dict(self):
        import uuid
        from datetime import datetime

        category = BookableResourceCategory()
        category.id = uuid.uuid4()
        category.name = "Workspace"
        category.slug = "workspace"
        category.description = "Coworking spaces"
        category.is_active = True
        category.sort_order = 2
        category.created_at = datetime(2026, 3, 19, 10, 0, 0)
        category.updated_at = datetime(2026, 3, 19, 10, 0, 0)

        result = category.to_dict()

        assert result["name"] == "Workspace"
        assert result["slug"] == "workspace"
        assert result["is_active"] is True
        assert result["parent_id"] is None
