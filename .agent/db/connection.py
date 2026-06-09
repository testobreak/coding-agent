# db/connection.py
#
# Central PostgreSQL connection pool.
# Every module imports get_conn() from here — one place to change credentials.
#
# Usage:
#   from db.connection import get_conn
#   with get_conn() as conn:
#       with conn.cursor() as cur:
#           cur.execute(...)
#

import os
import psycopg2
from psycopg2 import pool as pg_pool
from contextlib import contextmanager

# ── credentials ──────────────────────────────────────────────
# Override via environment variables for production.
DB_HOST = os.getenv("AGENT_DB_HOST", "localhost")
DB_PORT = int(os.getenv("AGENT_DB_PORT", "5432"))
DB_NAME = os.getenv("AGENT_DB_NAME", "agent_index")
DB_USER = os.getenv("AGENT_DB_USER", "postgres")
DB_PASS = os.getenv("AGENT_DB_PASS", "admin")

_pool: pg_pool.ThreadedConnectionPool = None


def _get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
        )
    return _pool


@contextmanager
def get_conn():
    """
    Context manager that yields a psycopg2 connection from the pool.
    Commits on success, rolls back on exception, always returns to pool.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def get_raw_conn() -> psycopg2.extensions.connection:
    """Return a raw connection (caller is responsible for close/commit)."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def ensure_database() -> None:
    """
    Create the agent_index database if it doesn't exist yet.
    Must connect to 'postgres' DB first to issue CREATE DATABASE.
    """
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname="postgres",
        user=DB_USER,
        password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{DB_NAME}"')
        print(f"[DB] Created database: {DB_NAME}")
    else:
        print(f"[DB] Database exists: {DB_NAME}")
    cur.close()
    conn.close()


def run_schema(schema_path: str = None) -> None:
    """
    Apply schema.sql to the target database.
    Idempotent — uses CREATE TABLE IF NOT EXISTS throughout.
    """
    if schema_path is None:
        import pathlib
        schema_path = pathlib.Path(__file__).parent / "schema.sql"

    sql = open(schema_path, encoding="utf-8").read()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"[DB] Schema applied from {schema_path}")
