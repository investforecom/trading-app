"""Database connection and helpers."""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager


def get_conn():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", 5432),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )


@contextmanager
def transaction():
    conn = get_conn()
    try:
        with conn:
            yield conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    finally:
        conn.close()


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def fetch_all(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()
