"""Repository for BookingCustomSchema."""
from plugins.booking.booking.models.custom_schema import BookingCustomSchema


class CustomSchemaRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self, active_only=True):
        query = self.session.query(BookingCustomSchema)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(BookingCustomSchema.sort_order).all()

    def find_by_id(self, schema_id):
        return self.session.get(BookingCustomSchema, schema_id)

    def find_by_slug(self, slug):
        return (
            self.session.query(BookingCustomSchema)
            .filter_by(slug=slug)
            .first()
        )

    def save(self, schema):
        self.session.add(schema)
        self.session.flush()
        return schema

    def delete(self, schema):
        self.session.delete(schema)
        self.session.flush()
