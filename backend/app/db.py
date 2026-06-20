import os
import psycopg2
from psycopg2.extras import RealDictCursor


def _connect():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=int(os.environ.get("PGPORT", 5432)),
        dbname=os.environ.get("PGDATABASE", "trading"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        cursor_factory=RealDictCursor,
    )


def query(sql: str, params=None) -> list[dict]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params=None) -> dict | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()
