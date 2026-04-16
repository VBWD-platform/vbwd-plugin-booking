"""Test fixtures for booking plugin tests."""
import pytest
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
)

os.environ["FLASK_ENV"] = "testing"
os.environ["TESTING"] = "true"
os.environ["TEST_DATA_SEED"] = "true"


def _test_db_url() -> str:
    base = os.getenv("DATABASE_URL", "postgresql://vbwd:vbwd@postgres:5432/vbwd")
    prefix, _, dbname = base.rpartition("/")
    dbname = dbname.split("?")[0]
    return f"{prefix}/{dbname}_test"


def _ensure_test_db(url: str) -> None:
    from sqlalchemy import create_engine, text

    main_url = url.rsplit("/", 1)[0] + "/postgres"
    dbname = url.rsplit("/", 1)[1].split("?")[0]
    engine = create_engine(main_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def app():
    from vbwd.app import create_app

    url = _test_db_url()
    _ensure_test_db(url)
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": url,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_STORAGE_URL": "memory://",
    }
    app = create_app(test_config)
    from vbwd.extensions import limiter

    limiter.reset()
    yield app

    with app.app_context():
        from vbwd.extensions import db as _db

        _db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from vbwd.extensions import db

    # Import booking models so create_all() creates their tables
    import plugins.booking.booking.models.custom_schema  # noqa: F401
    import plugins.booking.booking.models.resource  # noqa: F401
    import plugins.booking.booking.models.resource_category  # noqa: F401
    import plugins.booking.booking.models.booking  # noqa: F401
    import plugins.booking.booking.models.resource_image  # noqa: F401
    import plugins.booking.booking.models.slot_block  # noqa: F401

    try:
        import plugins.cms.src.models  # noqa: F401
    except ImportError:
        pass

    try:
        import plugins.email.src.models.email_template  # noqa: F401
    except ImportError:
        pass

    with app.app_context():
        db.create_all()
        # Seed admin user so integration tests can log in
        from vbwd.testing.test_data_seeder import TestDataSeeder

        seeder = TestDataSeeder(db.session)
        seeder.seed()

        # Deduplicate event bus subscribers (module singleton accumulates across tests)
        from vbwd.events.bus import event_bus

        for event_name in list(event_bus._subscribers.keys()):
            seen = set()
            unique = []
            for callback in event_bus._subscribers[event_name]:
                key = f"{callback.__module__}.{callback.__qualname__}"
                if key not in seen:
                    seen.add(key)
                    unique.append(callback)
            event_bus._subscribers[event_name] = unique

        yield db

        db.session.rollback()
        db.session.remove()
        db.drop_all()
