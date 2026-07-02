"""BookableResource model."""
from typing import Optional

from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


# S72.4: a per-resource netto/brutto price-display override. ``None`` inherits
# the global ``prices_display_mode`` core setting; ``"netto"``/``"brutto"``
# override it. Kept in sync with the core ``PRICES_DISPLAY_MODES`` enum.
PRICE_DISPLAY_MODE_OVERRIDES = ("netto", "brutto")


def validate_price_display_mode(value: Optional[str]) -> Optional[str]:
    """Return ``value`` if it is a valid override, else raise ``ValueError``.

    ``None`` (inherit the global setting) and the two enum values are accepted;
    any other value is rejected so the admin route can map it to a 400.
    """
    if value is None or value in PRICE_DISPLAY_MODE_OVERRIDES:
        return value
    raise ValueError(
        "price_display_mode must be one of "
        f"{(None,) + PRICE_DISPLAY_MODE_OVERRIDES}, got {value!r}"
    )


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


# Many-to-many join to the CORE tax catalog (``vbwd_tax``). The ``tax_id`` FK
# uses ``ON DELETE RESTRICT`` so deleting a tax that is assigned to a resource is
# rejected by the database (S72.3) rather than silently dropping the link; the
# ``resource_id`` FK uses ``ON DELETE CASCADE`` so deleting a resource tidies its
# own links.
booking_resource_tax = db.Table(
    "booking_resource_tax",
    db.Column(
        "resource_id",
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tax_id",
        UUID(as_uuid=True),
        db.ForeignKey("vbwd_tax.id", ondelete="RESTRICT"),
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
    # S85.1 (D4/D5): the single price double (full precision, never rounded in
    # code); the currency is the global ``default_currency`` (S84).
    price = db.Column(db.Float, nullable=False)
    price_unit = db.Column(db.String(50), default="per_slot")
    availability = db.Column(db.JSON, nullable=False, default=dict)
    custom_fields_schema = db.Column(db.JSON, nullable=True)
    image_url = db.Column(db.String(512), nullable=True)
    config = db.Column(db.JSON, nullable=True, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    # S72.4: per-resource netto/brutto override. ``NULL`` inherits the global
    # ``prices_display_mode`` core setting; ``"netto"``/``"brutto"`` override it.
    price_display_mode = db.Column(db.String(8), nullable=True)

    # Vendor-mode (marketplace): the owning vendor's ``vbwd_user`` id. ``NULL``
    # is a platform-owned resource (the classic single-owner booking). Indexed
    # for the vendor's "my resources" filter; ``ON DELETE SET NULL`` so removing
    # a user reverts their resources to the platform rather than deleting the
    # catalog rows. The checkout stamp copies this onto the buyer invoice line so
    # the central ``marketplace`` plugin credits the vendor (booking never
    # imports marketplace — the money path is a decoupled literal stamp).
    vendor_id = db.Column(
        db.UUID,
        db.ForeignKey("vbwd_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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

    # Assigned core taxes (M2M). When present these take precedence over the
    # bare net price for pricing (S72.3).
    taxes = db.relationship(
        "Tax",
        secondary=booking_resource_tax,
        lazy="selectin",
    )

    @property
    def raw_price(self) -> float:
        """The stored price as a float (the ``Priceable`` protocol member)."""
        return float(self.price) if self.price is not None else 0.0

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

    def _serialize_taxes(self) -> list:
        """Serialize assigned core taxes to ``{id, code, name, rate}``."""
        taxes = getattr(self, "taxes", None) or []
        return [
            {
                "id": str(tax.id),
                "code": tax.code,
                "name": tax.name,
                "rate": str(tax.rate),
            }
            for tax in taxes
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

        taxes = self._serialize_taxes()
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
            "price": self.raw_price,
            "price_unit": self.price_unit,
            "availability": self.availability or {},
            "custom_fields_schema": custom_fields,
            "image_url": self._resolve_primary_image_url(),
            "images": self._serialize_images(),
            "config": self.config or {},
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "price_display_mode": self.price_display_mode,
            "vendor_id": str(self.vendor_id) if self.vendor_id else None,
            "categories": self._serialize_categories(),
            "tax_ids": [tax["id"] for tax in taxes],
            "taxes": taxes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        schema_name = self.custom_schema.slug if self.custom_schema else "unclassified"
        return f"<BookableResource(name='{self.name}', schema='{schema_name}')>"
