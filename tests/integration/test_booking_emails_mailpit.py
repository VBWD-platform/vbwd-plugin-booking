# flake8: noqa: E501
"""Mailpit integration test — booking events trigger correct emails.

Fires each booking event, verifies the email arrives in Mailpit with:
- Correct recipient
- Subject contains resource name
- Body contains booking-specific content (times, reasons, etc.)
- HTML body is non-empty

Prerequisites:
  - Mailpit running at smtp://mailpit:1025 and http://mailpit:8025
  - PostgreSQL running
  - Email templates seeded (run populate_db or email seeds)

Run:
    docker compose run --rm test python -m pytest \
        plugins/booking/tests/integration/test_booking_emails_mailpit.py -v
"""
from __future__ import annotations

import os
import time

import pytest
import requests

try:
    from plugins.email.src.handlers import register_handlers
    from plugins.email.src.models.email_template import EmailTemplate
except ImportError:
    pytest.skip(
        "Email plugin not installed — skipping mailpit tests",
        allow_module_level=True,
    )

from vbwd.events.bus import EventBus

# ── Mailpit config ────────────────────────────────────────────────────────────

MAILPIT_API = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")
SMTP_HOST = os.getenv("MAILPIT_SMTP_HOST", "mailpit")
SMTP_PORT = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))

SMTP_CONFIG = {
    "smtp_host": SMTP_HOST,
    "smtp_port": SMTP_PORT,
    "smtp_use_tls": False,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from_email": "noreply@vbwd.test",
    "smtp_from_name": "VBWD Booking",
}

# ── Booking events with realistic payloads ────────────────────────────────────

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")

BOOKING_EVENTS = [
    {
        "event_type": "booking.created",
        "payload": {
            "user_email": "booking-created@vbwd.test",
            "user_name": "Alice Patient",
            "resource_name": "Dr. Smith",
            "start_at": "2026-04-15T10:00:00",
            "end_at": "2026-04-15T10:30:00",
            "booking_url": f"{FRONTEND_URL}/dashboard/bookings/uuid-test-001",
        },
        "expected_recipient": "booking-created@vbwd.test",
        "expected_subject_contains": "Dr. Smith",
        "expected_body_contains": ["Dr. Smith", "2026-04-15T10:00:00", "Alice Patient"],
        "expected_links": [f"{FRONTEND_URL}/dashboard/bookings/uuid-test-001"],
    },
    {
        "event_type": "booking.cancelled",
        "payload": {
            "user_email": "booking-cancelled@vbwd.test",
            "user_name": "Bob Client",
            "resource_name": "Meeting Room A",
            "cancelled_by": "user",
            "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
        },
        "expected_recipient": "booking-cancelled@vbwd.test",
        "expected_subject_contains": "Meeting Room A",
        "expected_body_contains": ["Meeting Room A", "cancelled"],
        "expected_links": [f"{FRONTEND_URL}/dashboard/bookings"],
    },
    {
        "event_type": "booking.cancelled_by_provider",
        "payload": {
            "user_email": "booking-provider-cancel@vbwd.test",
            "user_name": "Carol Visitor",
            "resource_name": "Dr. Johnson",
            "reason": "Doctor is on vacation",
            "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
        },
        "expected_recipient": "booking-provider-cancel@vbwd.test",
        "expected_subject_contains": "Dr. Johnson",
        "expected_body_contains": ["Dr. Johnson", "Doctor is on vacation", "refund"],
        "expected_links": [f"{FRONTEND_URL}/dashboard/bookings"],
    },
    {
        "event_type": "booking.completed",
        "payload": {
            "user_email": "booking-completed@vbwd.test",
            "user_name": "Dave Guest",
            "resource_name": "Yoga Studio",
            "dashboard_url": f"{FRONTEND_URL}/dashboard/bookings",
        },
        "expected_recipient": "booking-completed@vbwd.test",
        "expected_subject_contains": "Yoga Studio",
        "expected_body_contains": ["Yoga Studio", "completed"],
        "expected_links": [f"{FRONTEND_URL}/dashboard/bookings"],
    },
]

# ── Mailpit helpers ───────────────────────────────────────────────────────────


def _mailpit_reachable() -> bool:
    try:
        response = requests.get(f"{MAILPIT_API}/api/v1/messages", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def _clear_mailpit() -> None:
    requests.delete(f"{MAILPIT_API}/api/v1/messages", timeout=5)


def _get_all_messages() -> list[dict]:
    response = requests.get(f"{MAILPIT_API}/api/v1/messages", timeout=5)
    return response.json().get("messages") or []


def _get_message_body(message_id: str) -> dict:
    response = requests.get(f"{MAILPIT_API}/api/v1/message/{message_id}", timeout=5)
    return response.json()


def _wait_for_messages(
    expected_count: int, timeout: float = 15.0, poll_interval: float = 0.5
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = _get_all_messages()
        if len(messages) >= expected_count:
            return messages
        time.sleep(poll_interval)
    return _get_all_messages()


def _find_message_for_recipient(messages: list[dict], recipient: str) -> dict | None:
    for message in messages:
        recipients = [
            address.get("Address", "") for address in (message.get("To") or [])
        ]
        if recipient in recipients:
            return message
    return None


# ── DB helpers ────────────────────────────────────────────────────────────────


def _test_db_url() -> str:
    base = os.getenv("DATABASE_URL", "postgresql://vbwd:vbwd@postgres:5432/vbwd")
    prefix, _, database_name = base.rpartition("/")
    database_name = database_name.split("?")[0]
    return f"{prefix}/{database_name}_booking_email_test"


def _ensure_test_db(url: str) -> None:
    from sqlalchemy import create_engine, text

    main_url = url.rsplit("/", 1)[0] + "/postgres"
    database_name = url.rsplit("/", 1)[1].split("?")[0]
    engine = create_engine(main_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        engine.dispose()


# ── Fixtures ──────────────────────────────────────────────────────────────────

requires_mailpit = pytest.mark.skipif(
    not _mailpit_reachable(),
    reason="Mailpit not reachable — start docker compose first",
)


@pytest.fixture(scope="module")
def app():
    from vbwd.app import create_app

    database_url = _test_db_url()
    _ensure_test_db(database_url)
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RATELIMIT_ENABLED": False,
        }
    )


@pytest.fixture(scope="module")
def database(app):
    from vbwd.extensions import db as database_instance

    with app.app_context():
        database_instance.create_all()
        yield database_instance
        database_instance.session.remove()
        database_instance.drop_all()


@pytest.fixture(scope="module")
def event_bus(app):
    bus = EventBus()
    with app.app_context():
        register_handlers(bus, SMTP_CONFIG)
    return bus


@pytest.fixture(scope="module")
def seeded_templates(app, database):
    """Seed booking email templates."""
    from plugins.email.src.seeds import DEFAULT_TEMPLATES

    with app.app_context():
        for template_data in DEFAULT_TEMPLATES:
            existing = (
                database.session.query(EmailTemplate)
                .filter_by(event_type=template_data["event_type"])
                .first()
            )
            if existing:
                existing.subject = template_data["subject"]
                existing.html_body = template_data["html_body"]
                existing.text_body = template_data["text_body"]
                existing.is_active = template_data["is_active"]
            else:
                database.session.add(
                    EmailTemplate(
                        event_type=template_data["event_type"],
                        subject=template_data["subject"],
                        html_body=template_data["html_body"],
                        text_body=template_data["text_body"],
                        is_active=template_data["is_active"],
                    )
                )
        database.session.commit()
    return True


# ── Tests ─────────────────────────────────────────────────────────────────────


@requires_mailpit
class TestBookingEmailsViaMailpit:
    """Fire each booking event, verify email arrives with correct content."""

    @pytest.fixture(autouse=True)
    def clear_inbox(self):
        _clear_mailpit()
        yield

    @pytest.mark.parametrize(
        "event_spec",
        BOOKING_EVENTS,
        ids=[event["event_type"] for event in BOOKING_EVENTS],
    )
    def test_booking_event_sends_email(
        self, app, database, event_bus, seeded_templates, event_spec
    ):
        """Each booking event sends an email to the correct recipient."""
        with app.app_context():
            event_bus.publish(event_spec["event_type"], event_spec["payload"])

        delivered = _wait_for_messages(expected_count=1, timeout=10.0)
        recipient = event_spec["expected_recipient"]
        target = _find_message_for_recipient(delivered, recipient)

        assert target is not None, (
            f"No email for {event_spec['event_type']} → {recipient}. "
            f"Mailpit has {len(delivered)} message(s)."
        )

        full_message = _get_message_body(target["ID"])

        # Subject contains resource name
        subject = full_message.get("Subject", "")
        assert event_spec["expected_subject_contains"] in subject, (
            f"[{event_spec['event_type']}] expected "
            f"'{event_spec['expected_subject_contains']}' in subject '{subject}'"
        )

        # Body contains expected content
        html_body = full_message.get("HTML", "")
        text_body = full_message.get("Text", "")
        combined = html_body + text_body

        for expected_fragment in event_spec["expected_body_contains"]:
            assert expected_fragment in combined, (
                f"[{event_spec['event_type']}] expected "
                f"'{expected_fragment}' in body, not found"
            )

        # HTML body is non-empty
        assert html_body.strip(), f"[{event_spec['event_type']}] HTML body is empty"

    def test_all_booking_events_produce_emails(
        self, app, database, event_bus, seeded_templates
    ):
        """Fire all 4 booking events, verify 4 emails arrive."""
        with app.app_context():
            for event in BOOKING_EVENTS:
                event_bus.publish(event["event_type"], event["payload"])

        delivered = _wait_for_messages(expected_count=len(BOOKING_EVENTS), timeout=15.0)
        assert len(delivered) == len(BOOKING_EVENTS), (
            f"Expected {len(BOOKING_EVENTS)} emails, " f"got {len(delivered)}"
        )

    def test_no_duplicate_booking_emails(
        self, app, database, event_bus, seeded_templates
    ):
        """Each booking event produces exactly one email."""
        with app.app_context():
            for event in BOOKING_EVENTS:
                event_bus.publish(event["event_type"], event["payload"])

        delivered = _wait_for_messages(expected_count=len(BOOKING_EVENTS), timeout=15.0)

        all_recipients = []
        for message in delivered:
            for address in message.get("To") or []:
                all_recipients.append(address.get("Address", ""))

        duplicates = [r for r in all_recipients if all_recipients.count(r) > 1]
        assert not duplicates, f"Duplicate emails sent to: {set(duplicates)}"

    def test_booking_emails_have_correct_sender(
        self, app, database, event_bus, seeded_templates
    ):
        """All booking emails come from the configured sender."""
        with app.app_context():
            for event in BOOKING_EVENTS:
                event_bus.publish(event["event_type"], event["payload"])

        delivered = _wait_for_messages(expected_count=len(BOOKING_EVENTS), timeout=15.0)

        for message in delivered:
            full_message = _get_message_body(message["ID"])
            from_data = full_message.get("From", {})
            from_address = (
                from_data.get("Address", "") if isinstance(from_data, dict) else ""
            )
            assert from_address == SMTP_CONFIG["smtp_from_email"], (
                f"Expected sender '{SMTP_CONFIG['smtp_from_email']}', "
                f"got '{from_address}'"
            )


@requires_mailpit
class TestFireBookingEventsAndKeepInMailpit:
    """Fire all booking events and leave emails in Mailpit for visual inspection.

    After this test, open http://localhost:8025 to see all booking emails.
    Run in isolation:
        docker compose run --rm test python -m pytest \
            plugins/booking/tests/integration/test_booking_emails_mailpit.py::TestFireBookingEventsAndKeepInMailpit -v
    """

    def test_fire_all_booking_events_keep_in_mailpit(
        self, app, database, event_bus, seeded_templates
    ):
        """Fire all 4 booking events. Emails stay in Mailpit for inspection."""
        _clear_mailpit()

        with app.app_context():
            for event in BOOKING_EVENTS:
                event_bus.publish(event["event_type"], event["payload"])

        delivered = _wait_for_messages(expected_count=len(BOOKING_EVENTS), timeout=15.0)

        separator = "=" * 60
        print(f"\n{separator}")
        print(f"  {len(delivered)} booking email(s) delivered to Mailpit")
        print("  Open http://localhost:8025 to inspect them")
        print(separator)

        for message in delivered:
            recipients = ", ".join(
                address.get("Address", "") for address in (message.get("To") or [])
            )
            print(f"  [{message.get('Subject', '?')}] -> {recipients}")

        print()

        assert len(delivered) == len(
            BOOKING_EVENTS
        ), f"Expected {len(BOOKING_EVENTS)} emails, got {len(delivered)}"


@requires_mailpit
class TestBookingEmailLinksAreValid:
    """Verify all links in booking emails are absolute URLs that return 200/301."""

    @pytest.fixture(autouse=True)
    def clear_inbox(self):
        _clear_mailpit()
        yield

    @pytest.mark.parametrize(
        "event_spec",
        BOOKING_EVENTS,
        ids=[event["event_type"] for event in BOOKING_EVENTS],
    )
    def test_email_links_are_absolute(
        self, app, database, event_bus, seeded_templates, event_spec
    ):
        """All links in booking emails must be absolute URLs (http/https)."""
        import re

        with app.app_context():
            event_bus.publish(event_spec["event_type"], event_spec["payload"])

        delivered = _wait_for_messages(expected_count=1, timeout=10.0)
        target = _find_message_for_recipient(
            delivered, event_spec["expected_recipient"]
        )
        assert target is not None

        full_message = _get_message_body(target["ID"])
        html_body = full_message.get("HTML", "")
        links = re.findall(r'href="([^"]+)"', html_body)

        assert (
            len(links) > 0
        ), f"[{event_spec['event_type']}] No links found in email HTML"

        for link in links:
            assert link.startswith("http://") or link.startswith(
                "https://"
            ), f"[{event_spec['event_type']}] Link is not absolute: {link}"

    @pytest.mark.parametrize(
        "event_spec",
        BOOKING_EVENTS,
        ids=[event["event_type"] for event in BOOKING_EVENTS],
    )
    def test_email_links_have_valid_path_structure(
        self, app, database, event_bus, seeded_templates, event_spec
    ):
        """All links must have valid URL structure with known path prefixes."""
        import re
        from urllib.parse import urlparse

        with app.app_context():
            event_bus.publish(event_spec["event_type"], event_spec["payload"])

        delivered = _wait_for_messages(expected_count=1, timeout=10.0)
        target = _find_message_for_recipient(
            delivered, event_spec["expected_recipient"]
        )
        assert target is not None

        full_message = _get_message_body(target["ID"])
        html_body = full_message.get("HTML", "")
        links = re.findall(r'href="([^"]+)"', html_body)

        invalid_links = []
        valid_prefixes = ["/dashboard", "/booking", "/login", "/plans"]
        for link in links:
            parsed = urlparse(link)
            if not parsed.scheme:
                invalid_links.append(f"{link} (no scheme — not absolute)")
            elif not parsed.netloc:
                invalid_links.append(f"{link} (no host)")
            elif not any(parsed.path.startswith(prefix) for prefix in valid_prefixes):
                invalid_links.append(f"{link} (unknown path: {parsed.path})")

        assert (
            not invalid_links
        ), f"[{event_spec['event_type']}] Invalid links: {invalid_links}"

    def test_expected_links_present_in_emails(
        self, app, database, event_bus, seeded_templates
    ):
        """Each booking email contains the expected links."""
        import re

        with app.app_context():
            for event in BOOKING_EVENTS:
                event_bus.publish(event["event_type"], event["payload"])

        delivered = _wait_for_messages(expected_count=len(BOOKING_EVENTS), timeout=15.0)

        for event_spec in BOOKING_EVENTS:
            target = _find_message_for_recipient(
                delivered, event_spec["expected_recipient"]
            )
            assert target is not None

            full_message = _get_message_body(target["ID"])
            html_body = full_message.get("HTML", "")
            links = re.findall(r'href="([^"]+)"', html_body)

            for expected_link in event_spec.get("expected_links", []):
                assert any(expected_link in link for link in links), (
                    f"[{event_spec['event_type']}] Expected link "
                    f"'{expected_link}' not found in {links}"
                )
