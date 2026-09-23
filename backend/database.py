"""SQLite database helpers. A short-lived connection is opened per call,
which keeps the module safe across the FastAPI event loop and worker threads."""
import sqlite3
from typing import Any, Dict, List, Optional

from backend.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'shopkeeper')),
    shop_name     TEXT DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item           TEXT NOT NULL,
    customer_name  TEXT NOT NULL,
    customer_phone TEXT DEFAULT '',
    address        TEXT DEFAULT '',
    lat            REAL NOT NULL,
    lng            REAL NOT NULL,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    drone_id       INTEGER,
    created_by     INTEGER NOT NULL,
    distance_km    REAL,
    eta_min        REAL,
    notes          TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now')),
    delivered_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_user   ON orders (created_by);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)


def query(sql: str, params: tuple = (), one: bool = False):
    """Run a SELECT; returns list of dicts (or a single dict / None)."""
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        rows = [dict(r) for r in rows]
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, params: tuple = ()) -> int:
    """Run an INSERT/UPDATE/DELETE; returns lastrowid."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def user_row(user_id: int) -> Optional[Dict[str, Any]]:
    return query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)


def order_row(order_id: int) -> Optional[Dict[str, Any]]:
    return query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)


def set_order_status(order_id: int, status: str, notes: str = "") -> None:
    if notes:
        execute(
            "UPDATE orders SET status = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
            (status, notes, order_id),
        )
    else:
        execute(
            "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, order_id),
        )


def complete_order(order_id: int) -> None:
    execute(
        "UPDATE orders SET status='DELIVERED', delivered_at=datetime('now'), "
        "updated_at=datetime('now'), eta_min=0 WHERE id = ?",
        (order_id,),
    )
