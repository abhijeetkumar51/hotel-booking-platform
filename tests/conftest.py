"""Pytest configuration and fixtures for the hotel booking tests.

These tests use a REAL PostgreSQL database (the one specified by environment
variables or the defaults in app.config).  The test database is created fresh
for each session and torn down afterwards.

Requirements before running:
  - PostgreSQL server must be running and accepting connections.
  - The role specified by DB_USER must be able to CREATE DATABASE.
"""

import contextlib
import os
import sys

# On Windows, ensure PostgreSQL bin directory is in DLL search path
if sys.platform == "win32":
    for _p in [
        r"C:\Program Files\PostgreSQL\18\bin",
        r"C:\Program Files\PostgreSQL\17\bin",
        r"C:\Program Files\PostgreSQL\16\bin",
    ]:
        if os.path.exists(_p):
            with contextlib.suppress(OSError, AttributeError):
                os.add_dll_directory(_p)

import psycopg2
import pytest

from app.config import TestConfig
from app.database import close_pool, init_pool, init_schema

# ---------------------------------------------------------------------------
# Database lifecycle helpers
# ---------------------------------------------------------------------------

_TEST_DB = os.environ.get("DB_NAME", "hotel_booking_test")


def _admin_conn(dbname: str = "postgres"):
    """Connect to the admin (postgres) database to create/drop test DB."""
    cfg = TestConfig()
    return psycopg2.connect(
        host=cfg.DB_HOST,
        port=cfg.DB_PORT,
        dbname=dbname,
        user=cfg.DB_USER,
        password=cfg.DB_PASSWORD,
    )


def _create_test_db():
    conn = _admin_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {_TEST_DB}")
    conn.close()


def _drop_test_db():
    close_pool()
    conn = _admin_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    """Create and destroy the test database once per test session."""
    _create_test_db()
    config = TestConfig()
    init_pool(config)
    init_schema()
    yield
    _drop_test_db()


@pytest.fixture()
def client(_setup_db):  # noqa: ARG001
    """Provide a Flask test client."""
    from app.main import create_app

    config = TestConfig()
    app = create_app(config)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def clean_reservations():
    """Delete all reservations so each test starts fresh."""
    from app.database import get_connection

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reservations")
    yield
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reservations")
