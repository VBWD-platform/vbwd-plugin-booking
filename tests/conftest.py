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

    # Build the full schema exactly ONCE for the whole session, resetting the
    # public schema first (clearing any table or ENUM type left by a prior
    # crashed run or a sibling suite sharing this ``*_test`` DB). A per-test
    # create_all()/drop_all() strands standalone PG ENUM types and races other
    # suites on the shared catalog — see vbwd/testing/integration_db.py. Each
    # test then isolates by TRUNCATE-ing data, not by dropping the schema.
    with app.app_context():
        from vbwd.extensions import db as _db

        _import_schema_models()
        from vbwd.testing.integration_db import reset_schema_and_create_all

        reset_schema_and_create_all(_db)

    yield app

    with app.app_context():
        from vbwd.extensions import db as _db

        _db.engine.dispose()


def _import_schema_models():
    """Import every model whose table the session schema must contain.

    Load-bearing for create_all(): SQLAlchemy only emits DDL for mapped
    classes that have been imported. cms/email are optional peers.
    """
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


def _seed_canonical_roles(db) -> None:
    """Re-seed the ``vbwd_user_role`` catalog so the User.role FK resolves.

    The role catalog is a core enum-backed table; integration ``TRUNCATE``
    empties it, so the canonical rows are restored before any User is created.
    """
    from sqlalchemy import inspect

    table_names = inspect(db.engine).get_table_names(schema="public")
    if "vbwd_user_role" not in table_names:
        return

    from vbwd.models.user_role import RoleDefinition, canonical_role_rows

    if not db.session.query(RoleDefinition).first():
        db.session.bulk_insert_mappings(RoleDefinition, canonical_role_rows())
        db.session.commit()


def _seed_default_currency(db) -> None:
    """Seed the baseline EUR currency so the ``PriceFactory`` resolves a code."""
    from decimal import Decimal
    from uuid import uuid4

    from vbwd.models.currency import Currency

    if not db.session.query(Currency).filter_by(code="EUR").first():
        db.session.add(
            Currency(
                id=uuid4(),
                code="EUR",
                name="Euro",
                symbol="€",
                exchange_rate=Decimal("1.0"),
                decimal_places=2,
            )
        )
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from vbwd.extensions import db

    with app.app_context():
        # Isolate each test by clearing data (not schema) — the schema was built
        # once in the session ``app`` fixture.
        from vbwd.testing.integration_db import truncate_all_tables

        truncate_all_tables(db)

        # The core ``vbwd_user.role`` FK references ``vbwd_user_role``; the
        # truncate above empties that catalog, so re-seed the canonical role
        # rows before any User (incl. the seeder's admin) is created. Mirrors
        # the subscription conftest.
        _seed_canonical_roles(db)

        # Seed admin user so integration tests can log in
        from vbwd.testing.test_data_seeder import TestDataSeeder

        seeder = TestDataSeeder(db.session)
        seeder.seed()

        # S85.2: booking pricing now goes through the core PriceFactory, which
        # resolves the default currency from the catalog (S84). Seed the
        # baseline EUR row through the model so the factory has a code.
        _seed_default_currency(db)

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
