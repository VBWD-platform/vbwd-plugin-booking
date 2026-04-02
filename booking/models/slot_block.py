"""BookableResourceSlotBlock model — manually blocked time slots."""
from sqlalchemy.dialects.postgresql import UUID
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class BookableResourceSlotBlock(BaseModel):
    """A manually blocked time slot on a bookable resource.

    Used when admin blocks a slot (e.g., phone booking, break, maintenance).
    Blocked slots are excluded from user-facing availability.
    """

    __tablename__ = "booking_resource_slot_block"

    resource_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("booking_resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)  # "HH:MM"
    end_time = db.Column(db.String(5), nullable=False)  # "HH:MM"
    reason = db.Column(db.String(255), nullable=True)
    blocked_by = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("vbwd_user.id"),
        nullable=True,
    )

    __table_args__ = (
        db.Index(
            "ix_slot_block_resource_date",
            "resource_id",
            "date",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "resource_id": str(self.resource_id),
            "date": self.date.isoformat(),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "reason": self.reason,
            "blocked_by": str(self.blocked_by) if self.blocked_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<SlotBlock(resource={self.resource_id}, "
            f"date={self.date}, {self.start_time}-{self.end_time})>"
        )
