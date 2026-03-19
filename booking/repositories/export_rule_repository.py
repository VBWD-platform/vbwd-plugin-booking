"""Repository for BookingExportRule."""
from plugins.booking.booking.models.export_rule import BookingExportRule


class ExportRuleRepository:
    def __init__(self, session):
        self.session = session

    def find_all(self):
        return (
            self.session.query(BookingExportRule)
            .order_by(BookingExportRule.created_at.desc())
            .all()
        )

    def find_by_id(self, rule_id):
        return self.session.get(BookingExportRule, rule_id)

    def find_active_by_event(self, event_type):
        return (
            self.session.query(BookingExportRule)
            .filter_by(
                trigger_type="event",
                event_type=event_type,
                is_active=True,
            )
            .all()
        )

    def find_active_cron_rules(self):
        return (
            self.session.query(BookingExportRule)
            .filter_by(trigger_type="cron", is_active=True)
            .all()
        )

    def save(self, rule):
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule):
        self.session.delete(rule)
        self.session.flush()
