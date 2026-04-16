#!/usr/bin/env python
"""Run booking populate_db inside the running Flask app context."""
import sys
import os

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from vbwd.app import create_app  # noqa: E402

app = create_app()
with app.app_context():
    from plugins.booking.populate_db import populate

    populate(app)
