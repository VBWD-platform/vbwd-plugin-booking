"""ExportRuleService — execute event-driven and cron-driven export rules."""
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from plugins.booking.booking.repositories.export_rule_repository import (
    ExportRuleRepository,
)

logger = logging.getLogger(__name__)


class ExportRuleService:
    def __init__(self, export_rule_repository: ExportRuleRepository):
        self.export_rule_repository = export_rule_repository

    def execute_rule(self, rule, event_data: dict) -> None:
        """Execute an export rule with the given event data."""
        try:
            if rule.export_type == "webhook":
                self._send_webhook(rule, event_data)
            elif rule.export_type == "csv_file":
                self._append_csv(rule, event_data)
            elif rule.export_type == "xml_file":
                self._write_xml(rule, event_data)

            rule.last_triggered_at = datetime.utcnow()
            rule.last_status = "success"
            rule.last_error = None
        except Exception as error:
            rule.last_triggered_at = datetime.utcnow()
            rule.last_status = "failed"
            rule.last_error = str(error)
            logger.error("Export rule '%s' failed: %s", rule.name, error)

    def execute_event_rules(self, event_name: str, event_data: dict) -> None:
        """Find and execute all active rules for an event."""
        rules = self.export_rule_repository.find_active_by_event(event_name)
        for rule in rules:
            payload = {
                "event": event_name,
                "timestamp": datetime.utcnow().isoformat(),
                **event_data,
            }
            self.execute_rule(rule, payload)

    def _send_webhook(self, rule, event_data: dict) -> None:
        """Send HTTP POST to configured webhook URL."""
        config = rule.config
        url = config.get("url", "")
        headers = config.get("headers", {})
        timeout = config.get("timeout_seconds", 10)
        retry_count = config.get("retry_count", 0)

        last_error = None
        for attempt in range(1 + retry_count):
            try:
                response = httpx.post(
                    url,
                    json=event_data,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return
            except Exception as error:
                last_error = error
                if attempt < retry_count:
                    logger.warning(
                        "Webhook retry %d/%d for rule '%s': %s",
                        attempt + 1,
                        retry_count,
                        rule.name,
                        error,
                    )

        raise last_error

    def _append_csv(self, rule, event_data: dict) -> None:
        """Append a row to a CSV file."""
        config = rule.config
        now = datetime.utcnow()
        file_path = config.get("file_path", "/app/exports/export.csv").format(
            year=now.year,
            month=f"{now.month:02d}",
            day=f"{now.day:02d}",
        )
        columns = config.get("columns", list(event_data.keys()))

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        write_header = not os.path.exists(file_path)

        with open(file_path, "a") as csv_file:
            if write_header and config.get("include_header", True):
                csv_file.write(",".join(columns) + "\n")
            row = ",".join(str(event_data.get(column, "")) for column in columns)
            csv_file.write(row + "\n")

    def _write_xml(self, rule, event_data: dict) -> None:
        """Write event data as XML."""
        config = rule.config
        now = datetime.utcnow()
        file_path = config.get("file_path", "/app/exports/export.xml").format(
            year=now.year,
            month=f"{now.month:02d}",
            day=f"{now.day:02d}",
        )
        root_element = config.get("root_element", "exports")
        item_element = config.get("item_element", "item")
        fields = config.get("fields", list(event_data.keys()))

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if os.path.exists(file_path):
            tree = ET.parse(file_path)
            root = tree.getroot()
        else:
            root = ET.Element(root_element)
            tree = ET.ElementTree(root)

        item = ET.SubElement(root, item_element)
        for field in fields:
            child = ET.SubElement(item, field)
            child.text = str(event_data.get(field, ""))

        tree.write(file_path, encoding="unicode", xml_declaration=True)
