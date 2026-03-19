"""Unit tests for ExportRuleService."""
import os
import tempfile
from unittest.mock import MagicMock, patch

from plugins.booking.booking.services.export_rule_service import ExportRuleService


def _make_rule(export_type="webhook", config=None, name="Test Rule"):
    rule = MagicMock()
    rule.name = name
    rule.export_type = export_type
    rule.config = config or {}
    rule.last_triggered_at = None
    rule.last_status = None
    rule.last_error = None
    return rule


class TestWebhookExport:
    @patch("plugins.booking.booking.services.export_rule_service.httpx")
    def test_webhook_sends_post(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        repo = MagicMock()
        service = ExportRuleService(repo)
        rule = _make_rule(
            "webhook", {"url": "https://example.com/hook", "timeout_seconds": 5}
        )

        service.execute_rule(rule, {"event": "booking.created", "booking_id": "123"})

        mock_httpx.post.assert_called_once()
        assert rule.last_status == "success"

    @patch("plugins.booking.booking.services.export_rule_service.httpx")
    def test_webhook_records_failure(self, mock_httpx):
        mock_httpx.post.side_effect = Exception("Connection refused")

        repo = MagicMock()
        service = ExportRuleService(repo)
        rule = _make_rule(
            "webhook", {"url": "https://example.com/hook", "retry_count": 0}
        )

        service.execute_rule(rule, {"event": "test"})

        assert rule.last_status == "failed"
        assert "Connection refused" in rule.last_error

    @patch("plugins.booking.booking.services.export_rule_service.httpx")
    def test_webhook_retries_on_failure(self, mock_httpx):
        mock_httpx.post.side_effect = [
            Exception("fail"),
            Exception("fail"),
            MagicMock(),
        ]

        repo = MagicMock()
        service = ExportRuleService(repo)
        rule = _make_rule(
            "webhook", {"url": "https://example.com/hook", "retry_count": 2}
        )

        service.execute_rule(rule, {"event": "test"})

        assert mock_httpx.post.call_count == 3
        assert rule.last_status == "success"


class TestCsvExport:
    def test_csv_creates_file_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.csv")
            repo = MagicMock()
            service = ExportRuleService(repo)
            rule = _make_rule(
                "csv_file",
                {
                    "file_path": file_path,
                    "columns": ["booking_id", "status"],
                    "include_header": True,
                },
            )

            service.execute_rule(rule, {"booking_id": "123", "status": "confirmed"})

            assert os.path.exists(file_path)
            content = open(file_path).read()
            assert "booking_id,status" in content
            assert "123,confirmed" in content

    def test_csv_appends_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.csv")
            repo = MagicMock()
            service = ExportRuleService(repo)
            rule = _make_rule(
                "csv_file",
                {"file_path": file_path, "columns": ["id"], "include_header": True},
            )

            service.execute_rule(rule, {"id": "1"})
            service.execute_rule(rule, {"id": "2"})

            lines = open(file_path).read().strip().split("\n")
            assert len(lines) == 3  # header + 2 rows

    def test_csv_path_interpolates_year_month(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "export_{year}_{month}.csv")
            repo = MagicMock()
            service = ExportRuleService(repo)
            rule = _make_rule(
                "csv_file",
                {"file_path": file_path, "columns": ["id"]},
            )

            service.execute_rule(rule, {"id": "1"})

            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert "2026" in files[0]


class TestXmlExport:
    def test_xml_writes_valid_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.xml")
            repo = MagicMock()
            service = ExportRuleService(repo)
            rule = _make_rule(
                "xml_file",
                {
                    "file_path": file_path,
                    "root_element": "bookings",
                    "item_element": "booking",
                    "fields": ["id", "status"],
                },
            )

            service.execute_rule(rule, {"id": "123", "status": "confirmed"})

            content = open(file_path).read()
            assert "<bookings>" in content
            assert "<booking>" in content
            assert "<id>123</id>" in content


class TestEventRuleExecution:
    def test_executes_active_rules_for_event(self):
        rule1 = _make_rule("webhook", {"url": "https://a.com", "timeout_seconds": 5})
        rule2 = _make_rule("webhook", {"url": "https://b.com", "timeout_seconds": 5})
        repo = MagicMock()
        repo.find_active_by_event.return_value = [rule1, rule2]

        service = ExportRuleService(repo)
        with patch(
            "plugins.booking.booking.services.export_rule_service.httpx"
        ) as mock_httpx:
            mock_httpx.post.return_value = MagicMock()
            service.execute_event_rules("booking.created", {"booking_id": "123"})

        assert mock_httpx.post.call_count == 2

    def test_inactive_rules_not_returned(self):
        repo = MagicMock()
        repo.find_active_by_event.return_value = []

        service = ExportRuleService(repo)
        with patch(
            "plugins.booking.booking.services.export_rule_service.httpx"
        ) as mock_httpx:
            service.execute_event_rules("booking.created", {})

        mock_httpx.post.assert_not_called()
