"""Repository for BookableResource."""
from plugins.booking.booking.models.resource import BookableResource


class ResourceRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self, active_only=True):
        query = self.session.query(BookableResource)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookableResource.sort_order).all()

    def find_by_id(self, resource_id):
        return self.session.get(BookableResource, resource_id)

    def find_by_slug(self, slug):
        return (
            self.session.query(BookableResource)
            .filter_by(slug=slug)
            .first()
        )

    def find_by_category(self, category_slug, active_only=True):
        query = (
            self.session.query(BookableResource)
            .join(BookableResource.categories)
        )
        from plugins.booking.booking.models.resource_category import (
            BookableResourceCategory,
        )

        query = query.filter(BookableResourceCategory.slug == category_slug)
        if active_only:
            query = query.filter(BookableResource.is_active.is_(True))
        return query.order_by(BookableResource.sort_order).all()

    def find_by_type(self, resource_type, active_only=True):
        query = self.session.query(BookableResource).filter_by(
            resource_type=resource_type
        )
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookableResource.sort_order).all()

    def save(self, resource):
        self.session.add(resource)
        self.session.flush()
        return resource

    def delete(self, resource):
        self.session.delete(resource)
        self.session.flush()
