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

    def _resolve_customer(self) -> dict:
        """Resolve customer name and email from user_id."""
        try:
            from vbwd.models.user import User
            from vbwd.models.user_details import UserDetails

            user = db.session.get(User, self.user_id)
            if not user:
                return {"email": "", "name": ""}

            details = (
                db.session.query(UserDetails).filter_by(user_id=self.user_id).first()
            )
            if details and details.first_name:
                name = f"{details.first_name} {details.last_name or ''}".strip()
            else:
                name = user.email

            return {
                "email": user.email,
                "name": name,
                "phone": getattr(details, "phone", None) or "",
                "company": getattr(details, "company", None) or "",
            }
        except Exception:
            pass
        return {"email": "", "name": "", "phone": "", "company": ""}

    def to_dict(self) -> dict:
        customer = self._resolve_customer()
        return {
            "id": str(self.id),
            "resource_id": str(self.resource_id),
            "user_id": str(self.user_id),
            "customer_email": customer["email"],
            "customer_name": customer["name"],
            "customer_phone": customer.get("phone", ""),
            "customer_company": customer.get("company", ""),
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
