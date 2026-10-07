"""Storage for widget data: Postgres when DATABASE_URL is a postgres:// URL, SQLite otherwise.

Each pipeline saves its latest good result under a name ("weather", "news", ...). A failed
fetch records the error but keeps the last good data, so a broken source never empties a widget.
"""

import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS widget_data (
    name        TEXT PRIMARY KEY,
    data        TEXT,
    fetched_at  TEXT,
    error       TEXT,
    error_at    TEXT
)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    """Tiny wrapper so the same SQL (with %s placeholders) runs on both databases."""

    def __init__(self, url: str):
        self.postgres = url.startswith(("postgres://", "postgresql://"))
        if self.postgres:
            import psycopg
            self.conn = psycopg.connect(url, autocommit=True)
        else:
            self.conn = sqlite3.connect(url, timeout=30)
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.execute(SCHEMA)

    def execute(self, sql: str, params: tuple = ()):
        if not self.postgres:
            sql = sql.replace("%s", "?")
        cur = self.conn.execute(sql, params)
        if not self.postgres:
            self.conn.commit()
        return cur

    def close(self):
        self.conn.close()


def connect(url: str) -> DB:
    return DB(url)


def save_data(db: DB, name: str, data) -> None:
    db.execute(
        "INSERT INTO widget_data (name, data, fetched_at, error, error_at) "
        "VALUES (%s, %s, %s, NULL, NULL) "
        "ON CONFLICT (name) DO UPDATE SET data = excluded.data, "
        "fetched_at = excluded.fetched_at, error = NULL, error_at = NULL",
        (name, json.dumps(data), now_iso()),
    )


def save_error(db: DB, name: str, error: str) -> None:
    db.execute(
        "INSERT INTO widget_data (name, error, error_at) VALUES (%s, %s, %s) "
        "ON CONFLICT (name) DO UPDATE SET error = excluded.error, error_at = excluded.error_at",
        (name, error[:500], now_iso()),
    )


def load(db: DB, name: str) -> dict | None:
    row = db.execute(
        "SELECT data, fetched_at, error, error_at FROM widget_data WHERE name = %s", (name,)
    ).fetchone()
    if row is None:
        return None
    data, fetched_at, error, error_at = row
    return {"data": json.loads(data) if data else None, "fetched_at": fetched_at,
            "error": error, "error_at": error_at}


def last_attempt(db: DB, name: str) -> str | None:
    """When this pipeline last ran, successfully or not."""
    row = load(db, name)
    if row is None:
        return None
    return max(filter(None, [row["fetched_at"], row["error_at"]]), default=None)
