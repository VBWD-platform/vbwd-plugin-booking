# vbwd-plugin-booking

Backend booking plugin — appointments, rooms, spaces, seats.

## Structure

```
plugins/booking/
├── __init__.py           # BookingPlugin(BasePlugin)
├── config.json           # Default configuration
├── populate_db.py        # Demo data (idempotent)
├── booking/              # Source code
│   ├── models/
│   ├── repositories/
│   ├── services/
│   └── routes.py
├── migrations/versions/
└── tests/
    ├── unit/
    └── integration/
```

## Development

```bash
docker compose run --rm test pytest plugins/booking/tests/unit/ -v
docker compose run --rm test pytest plugins/booking/tests/integration/ -v
```
