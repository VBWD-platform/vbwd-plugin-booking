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
    custom_schema_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("booking_custom_schema.id"),
        nullable=True,
    )
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

    custom_schema = db.relationship(
        "BookingCustomSchema",
        lazy="selectin",
    )

    categories = db.relationship(
        "BookableResourceCategory",
        secondary=booking_resource_category_link,
        backref="resources",
        lazy="selectin",
    )

    def _get_images(self) -> list:
        try:
            from plugins.booking.booking.models.resource_image import (
                BookableResourceImage,
            )

            return (
                db.session.query(BookableResourceImage)
                .filter_by(resource_id=self.id)
                .order_by(BookableResourceImage.sort_order)
                .all()
            )
        except Exception:
            return []

    def _serialize_images(self) -> list:
        return [img.to_dict() for img in self._get_images()]

    def _resolve_primary_image_url(self) -> str | None:
        for img in self._get_images():
            if img.is_primary:
                image_dict = img.to_dict()
                return image_dict.get("url")
        images = self._get_images()
        if images:
            return images[0].to_dict().get("url")
        return self.image_url

    def _serialize_categories(self) -> list:
        categories = list(self.categories)  # type: ignore[call-overload]
        return [
            {"id": str(cat.id), "name": cat.name, "slug": cat.slug}
            for cat in categories
        ]

    def to_dict(self) -> dict:
        # Schema provides both type label and custom fields
        if self.custom_schema:
            resource_type = self.custom_schema.slug
            resource_type_name = self.custom_schema.name
            custom_fields = self.custom_schema.fields or []
            custom_schema_id = str(self.custom_schema_id)
        else:
            resource_type = "unclassified"
            resource_type_name = "Unclassified"
            custom_fields = self.custom_fields_schema
            custom_schema_id = None

        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "resource_type": resource_type,
            "resource_type_name": resource_type_name,
            "custom_schema_id": custom_schema_id,
            "capacity": self.capacity,
            "slot_duration_minutes": self.slot_duration_minutes,
            "price": str(self.price),
            "currency": self.currency,
            "price_unit": self.price_unit,
            "availability": self.availability or {},
            "custom_fields_schema": custom_fields,
            "image_url": self._resolve_primary_image_url(),
            "images": self._serialize_images(),
            "config": self.config or {},
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "categories": self._serialize_categories(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        schema_name = self.custom_schema.slug if self.custom_schema else "unclassified"
        return f"<BookableResource(name='{self.name}', schema='{schema_name}')>"
