"""Repository for BookableResourceType."""
from plugins.booking.booking.models.resource_type import BookableResourceType


class ResourceTypeRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self, active_only=True):
        query = self.session.query(BookableResourceType)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookableResourceType.sort_order).all()

    def find_by_id(self, type_id):
        return self.session.get(BookableResourceType, type_id)

    def find_by_slug(self, slug):
        return (
            self.session.query(BookableResourceType)
            .filter_by(slug=slug)
            .first()
        )

    def save(self, resource_type):
        self.session.add(resource_type)
        self.session.flush()
        return resource_type

    def delete(self, resource_type):
        self.session.delete(resource_type)
        self.session.flush()
