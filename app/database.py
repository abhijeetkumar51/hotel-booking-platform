"""Database connection management and schema initialization."""

import contextlib
import logging

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import Config

logger = logging.getLogger(__name__)

# Module-level connection pool
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool(config: Config) -> None:
    """Initialize the database connection pool."""
    global _pool
    if _pool is not None:
        return
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    logger.info("Database connection pool initialized.")


def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed.")


@contextlib.contextmanager
def get_connection():
    """Get a connection from the pool as a context manager."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool first.")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def check_connection() -> bool:
    """Check if database is reachable."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Enable btree_gist extension for exclusion constraint
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS rooms (
    id              SERIAL PRIMARY KEY,
    room_number     VARCHAR(10)  NOT NULL UNIQUE,
    room_type       VARCHAR(50)  NOT NULL,
    price_per_night NUMERIC(10,2) NOT NULL CHECK (price_per_night > 0),
    capacity        INTEGER      NOT NULL CHECK (capacity > 0),
    description     TEXT         DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reservations (
    id                SERIAL PRIMARY KEY,
    booking_reference VARCHAR(12)  NOT NULL UNIQUE,
    room_id           INTEGER      NOT NULL REFERENCES rooms(id),
    guest_name        VARCHAR(200) NOT NULL,
    guest_email       VARCHAR(200) NOT NULL,
    check_in          DATE         NOT NULL,
    check_out         DATE         NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'confirmed'
                      CHECK (status IN ('confirmed', 'cancelled')),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),

    CONSTRAINT check_dates CHECK (check_out > check_in),

    -- Exclusion constraint: no two confirmed reservations for the same room
    -- can have overlapping date ranges.  Uses daterange with '[)' (inclusive
    -- start, exclusive end) so that one guest's check_out day can equal
    -- another guest's check_in day.
    EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (status = 'confirmed')
);

-- Seed default rooms if table is empty
INSERT INTO rooms (room_number, room_type, price_per_night, capacity, description)
SELECT * FROM (VALUES
    ('101', 'standard',  99.99, 2, 'Standard room with queen bed'),
    ('102', 'standard',  99.99, 2, 'Standard room with twin beds'),
    ('201', 'deluxe',   149.99, 2, 'Deluxe room with king bed and city view'),
    ('202', 'deluxe',   149.99, 3, 'Deluxe family room with king bed and sofa bed'),
    ('301', 'suite',    249.99, 4, 'Luxury suite with separate living area')
) AS seed(room_number, room_type, price_per_night, capacity, description)
WHERE NOT EXISTS (SELECT 1 FROM rooms);
"""


def init_schema() -> None:
    """Create tables and seed data if needed."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    logger.info("Database schema initialized.")
