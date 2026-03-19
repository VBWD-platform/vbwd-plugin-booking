"""BookingExportRule model — event-driven and cron-driven export rules."""
from vbwd.extensions import db
from vbwd.models.base import BaseModel


class BookingExportRule(BaseModel):
    """Export rule that fires on events or cron schedule."""

    __tablename__ = "booking_export_rule"

    name = db.Column(db.String(255), nullable=False)
    trigger_type = db.Column(db.String(50), nullable=False)  # "event" or "cron"
    event_type = db.Column(db.String(100), nullable=True, index=True)
    cron_expression = db.Column(db.String(100), nullable=True)
    cron_export_scope = db.Column(db.String(50), nullable=True)
    cron_entity = db.Column(db.String(50), nullable=True)
    cron_status_filter = db.Column(db.String(255), nullable=True)
    export_type = db.Column(
        db.String(50), nullable=False
    )  # "webhook", "csv_file", "xml_file"
    config = db.Column(db.JSON, nullable=False, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(50), nullable=True)
    last_error = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "trigger_type": self.trigger_type,
            "event_type": self.event_type,
            "cron_expression": self.cron_expression,
            "cron_export_scope": self.cron_export_scope,
            "cron_entity": self.cron_entity,
            "cron_status_filter": self.cron_status_filter,
            "export_type": self.export_type,
            "config": self.config,
            "is_active": self.is_active,
            "last_triggered_at": (
                self.last_triggered_at.isoformat() if self.last_triggered_at else None
            ),
            "last_status": self.last_status,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<BookingExportRule(name='{self.name}', trigger='{self.trigger_type}')>"
