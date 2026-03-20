"""BookableResourceType model."""
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class BookableResourceType(BaseModel):
    """Admin-managed resource type (e.g., Specialist, Room, Space)."""

    __tablename__ = "booking_resource_type"

    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<BookableResourceType(name='{self.name}', slug='{self.slug}')>"
