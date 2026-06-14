#!/usr/bin/env python3
"""Populate booking demo data — thin wrapper over the shared seed (S88).

The seed logic lives in ``plugins/booking/booking/demo_seed.py``
(``seed_catalog``), which ``flask reset-demo`` runs through core's demo-data
registry. This module keeps the standalone CLI entrypoint working by delegating
to that single source.

Usage: python plugins/booking/populate_db.py [--force]
"""
import argparse
import sys

sys.path.insert(0, "/app")

from vbwd.app import create_app  # noqa: E402
from vbwd.extensions import db  # noqa: E402
from plugins.booking.booking.demo_seed import seed_catalog  # noqa: E402


def populate(force=False):
    stats = seed_catalog(db.session, force=force)
    print("=== Booking Plugin — Demo Data ===")
    print(f"  Categories: {stats['booking_categories']}")
    print(f"  Resources:  {stats['booking_resources']}")


def main():
    parser = argparse.ArgumentParser(description="Populate booking demo data")
    parser.add_argument("--force", action="store_true", help="Overwrite existing data")
    parser.add_argument("--check", action="store_true", help="Check if data exists")
    arguments = parser.parse_args()

    app = create_app()
    with app.app_context():
        if arguments.check:
            from plugins.booking.booking.models.resource import BookableResource

            count = db.session.query(BookableResource).count()
            sys.exit(1 if count > 0 else 0)
        populate(force=arguments.force)


if __name__ == "__main__":
    main()
