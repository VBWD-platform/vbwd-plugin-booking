"""BookableResourceImage model — join entity linking resources to CMS images."""
from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class BookableResourceImage(BaseModel):
    """Links a bookable resource to a CMS image with ordering and primary flag."""

    __tablename__ = "booking_resource_image"

    resource_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cms_image_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("cms_image.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("resource_id", "cms_image_id"),
    )

    def to_dict(self) -> dict:
        result = {
            "id": str(self.id),
            "resource_id": str(self.resource_id),
            "cms_image_id": str(self.cms_image_id),
            "is_primary": self.is_primary,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        # Resolve CMS image fields lazily
        try:
            from plugins.cms.src.models.cms_image import CmsImage

            cms_image = db.session.get(CmsImage, self.cms_image_id)
            if cms_image:
                result["url"] = cms_image.url_path
                result["alt"] = cms_image.alt_text
                result["caption"] = cms_image.caption
        except ImportError:
            pass
        return result

    def __repr__(self) -> str:
        return (
            f"<BookableResourceImage("
            f"resource={self.resource_id}, "
            f"image={self.cms_image_id}, "
            f"primary={self.is_primary})>"
        )
