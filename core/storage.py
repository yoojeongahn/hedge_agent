"""SQLite 기반 스냅샷 저장. 가벼운 시계열 DB로 사용."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.broker import AccountSnapshot

DB_PATH = Path(__file__).parent.parent / "data" / "snapshots.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    ts            TEXT PRIMARY KEY,
    total_eval    REAL NOT NULL,
    cash          REAL NOT NULL,
    deposit_d2    REAL NOT NULL,
    total_pnl     REAL NOT NULL,
    total_pnl_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    ts             TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    avg_price      REAL NOT NULL,
    current_price  REAL NOT NULL,
    eval_amount    REAL NOT NULL,
    pnl_amount     REAL NOT NULL,
    pnl_pct        REAL NOT NULL,
    PRIMARY KEY (ts, code),
    FOREIGN KEY (ts) REFERENCES account_snapshots(ts)
);

CREATE INDEX IF NOT EXISTS idx_position_code ON position_snapshots(code);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_snapshot(snap: AccountSnapshot) -> None:
    init_db()
    ts = snap.timestamp.isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO account_snapshots
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ts, snap.total_eval, snap.cash, snap.deposit_d2,
             snap.total_pnl, snap.total_pnl_pct),
        )
        for p in snap.positions:
            conn.execute(
                """INSERT OR REPLACE INTO position_snapshots
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, p.code, p.name, p.quantity, p.avg_price,
                 p.current_price, p.eval_amount, p.pnl_amount, p.pnl_pct),
            )


def latest_snapshot_ts() -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT ts FROM account_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return row["ts"] if row else None
