"""SQLite 기반 스냅샷 저장."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.pricer import PortfolioSnapshot

DB_PATH = Path(__file__).parent.parent / "data" / "snapshots.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    ts            TEXT PRIMARY KEY,
    total_eval    REAL NOT NULL,
    cash          REAL NOT NULL,
    cash_usd      REAL NOT NULL DEFAULT 0,
    usd_krw_rate  REAL NOT NULL DEFAULT 0,
    total_pnl     REAL NOT NULL,
    total_pnl_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    ts             TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    market         TEXT NOT NULL DEFAULT 'KR',
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


def save_snapshot(snap: PortfolioSnapshot) -> None:
    init_db()
    ts = snap.timestamp.isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO account_snapshots
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, snap.total_eval_krw, snap.cash_krw, snap.cash_usd,
             snap.usd_krw_rate, snap.total_pnl_krw, snap.total_pnl_pct),
        )
        for p in snap.positions:
            conn.execute(
                """INSERT OR REPLACE INTO position_snapshots
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, p.code, p.name, p.market, p.quantity, p.avg_price,
                 p.current_price_krw, p.eval_amount_krw,
                 p.pnl_amount_krw, p.pnl_pct),
            )


def latest_snapshot_ts() -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT ts FROM account_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return row["ts"] if row else None


def prev_total_eval_krw() -> float | None:
    """직전 스냅샷의 총평가금액 반환. save_snapshot() 호출 전에 불러야 함."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT total_eval FROM account_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return float(row["total_eval"]) if row else None
