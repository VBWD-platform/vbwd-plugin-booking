"""Booking auto-completion scheduler.

Moved out of ``vbwd/scheduler.py`` in S01 — core must not import from any
plugin. Mirrors the subscription plugin's scheduler shape: ``on_enable``
starts it (guarded against TESTING), nothing in core references it.
"""
import logging

logger = logging.getLogger(__name__)


def run_booking_completion_jobs(app):
    """Auto-complete bookings whose time has passed.

    Imports are local so importing this module never pulls the booking
    repositories at startup (apscheduler invokes the job inside the worker
    thread under an app context).
    """
    with app.app_context():
        from vbwd.extensions import db
        from vbwd.events.bus import event_bus
        from plugins.booking.booking.repositories.booking_repository import (
            BookingRepository,
        )
        from plugins.booking.booking.repositories.resource_repository import (
            ResourceRepository,
        )
        from plugins.booking.booking.services.booking_completion_service import (
            BookingCompletionService,
        )

        service = BookingCompletionService(
            booking_repository=BookingRepository(db.session),
            resource_repository=ResourceRepository(db.session),
            event_bus=event_bus,
        )
        completed = service.complete_past_bookings()
        if completed:
            db.session.commit()
            logger.info("[booking] Auto-completed %d booking(s)", len(completed))


def start_booking_scheduler(app, interval_seconds: int = 900):
    """Start the periodic booking-completion job."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_booking_completion_jobs,
        "interval",
        seconds=interval_seconds,
        args=[app],
        id="booking_completion_jobs",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[booking] Scheduler started (interval=%ds)", interval_seconds)
    return scheduler
