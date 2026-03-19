"""BookableResourceCategory model."""
from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class BookableResourceCategory(BaseModel):
    """Category for bookable resources (e.g., Medical, Workspace, Events)."""

    __tablename__ = "booking_resource_category"

    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(512), nullable=True)
    parent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource_category.id"),
        nullable=True,
    )
    config = db.Column(db.JSON, nullable=True, default=dict)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    parent = db.relationship(
        "BookableResourceCategory",
        remote_side="BookableResourceCategory.id",
        backref="children",
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "image_url": self.image_url,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "config": self.config or {},
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<BookableResourceCategory(name='{self.name}', slug='{self.slug}')>"
