"""BookableResource model."""
from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


booking_resource_category_link = db.Table(
    "booking_resource_category_link",
    db.Column(
        "resource_id",
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "category_id",
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource_category.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class BookableResource(BaseModel):
    """A bookable resource — appointment, room, space, or seat."""

    __tablename__ = "booking_resource"

    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    resource_type = db.Column(db.String(100), nullable=False, index=True)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    slot_duration_minutes = db.Column(db.Integer, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR")
    price_unit = db.Column(db.String(50), default="per_slot")
    availability = db.Column(db.JSON, nullable=False, default=dict)
    custom_fields_schema = db.Column(db.JSON, nullable=True)
    image_url = db.Column(db.String(512), nullable=True)
    config = db.Column(db.JSON, nullable=True, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    categories = db.relationship(
        "BookableResourceCategory",
        secondary=booking_resource_category_link,
        backref="resources",
        lazy="selectin",
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "resource_type": self.resource_type,
            "capacity": self.capacity,
            "slot_duration_minutes": self.slot_duration_minutes,
            "price": str(self.price),
            "currency": self.currency,
            "price_unit": self.price_unit,
            "availability": self.availability or {},
            "custom_fields_schema": self.custom_fields_schema,
            "image_url": self.image_url,
            "config": self.config or {},
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "categories": [
                {"id": str(category.id), "name": category.name, "slug": category.slug}
                for category in (self.categories or [])
            ],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<BookableResource(name='{self.name}', type='{self.resource_type}')>"
