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

## Documentation

Full platform documentation lives at **[vbwd.cc/docs](https://vbwd.cc/docs)**.

- [Plugin system](https://vbwd.cc/docs-plugin-system) — how backend plugins are registered, enabled, and configured
- [Booking](https://vbwd.cc/docs-core-booking) — documentation for this plugin's domain
- [Architecture](https://vbwd.cc/docs-architecture) — platform layering and the core-agnosticism rule
- [Getting started](https://vbwd.cc/docs-getting-started) — install a VBWD instance and enable plugins
