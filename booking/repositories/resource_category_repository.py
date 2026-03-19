"""Repository for BookableResourceCategory."""
from plugins.booking.booking.models.resource_category import BookableResourceCategory


class ResourceCategoryRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self, active_only=True):
        query = self.session.query(BookableResourceCategory)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookableResourceCategory.sort_order).all()

    def find_by_id(self, category_id):
        return self.session.get(BookableResourceCategory, category_id)

    def find_by_slug(self, slug):
        return (
            self.session.query(BookableResourceCategory)
            .filter_by(slug=slug)
            .first()
        )

    def save(self, category):
        self.session.add(category)
        self.session.flush()
        return category

    def delete(self, category):
        self.session.delete(category)
        self.session.flush()
