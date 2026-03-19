"""Booking model."""
from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class Booking(BaseModel):
    """A confirmed reservation of a BookableResource by a user."""

    __tablename__ = "booking"

    resource_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    invoice_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("user_invoice.id"),
        nullable=True,
        index=True,
    )
    start_at = db.Column(db.DateTime, nullable=False, index=True)
    end_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="confirmed")
    quantity = db.Column(db.Integer, nullable=False, default=1)
    custom_fields = db.Column(db.JSON, nullable=True, default=dict)
    notes = db.Column(db.Text, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)

    resource = db.relationship("BookableResource", backref="bookings", lazy="selectin")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "resource_id": str(self.resource_id),
            "user_id": str(self.user_id),
            "invoice_id": str(self.invoice_id) if self.invoice_id else None,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "status": self.status,
            "quantity": self.quantity,
            "custom_fields": self.custom_fields or {},
            "notes": self.notes,
            "admin_notes": self.admin_notes,
            "resource": self.resource.to_dict() if self.resource else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Booking(resource_id='{self.resource_id}', status='{self.status}')>"
