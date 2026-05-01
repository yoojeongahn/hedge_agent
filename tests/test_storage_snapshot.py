from datetime import datetime
from core.storage import save_snapshot, init_db, latest_snapshot_ts, prev_total_eval_krw
from core.pricer import PricedPosition, PortfolioSnapshot


def make_snapshot() -> PortfolioSnapshot:
    pos = PricedPosition(
        code="005930", name="삼성전자", market="KR",
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750000.0, pnl_amount_krw=50000.0,
        pnl_pct=7.14, weight_pct=15.0,
        ret_7d=2.1, ret_30d=5.3,
        week52_high=80000.0, week52_low=55000.0,
    )
    return PortfolioSnapshot(
        timestamp=datetime(2026, 5, 1, 16, 30),
        positions=[pos],
        cash_krw=1000000.0,
        cash_usd=500.0,
        usd_krw_rate=1380.0,
        total_eval_krw=2440000.0,
        total_pnl_krw=50000.0,
        total_pnl_pct=2.1,
    )


def test_save_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr("core.storage.DB_PATH", tmp_path / "test.db")
    snap = make_snapshot()
    save_snapshot(snap)
    ts = latest_snapshot_ts()
    assert ts == "2026-05-01T16:30:00"


def test_prev_total_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("core.storage.DB_PATH", tmp_path / "empty.db")
    assert prev_total_eval_krw() is None


def test_prev_total_returns_last_saved(tmp_path, monkeypatch):
    monkeypatch.setattr("core.storage.DB_PATH", tmp_path / "prev.db")
    snap = make_snapshot()
    save_snapshot(snap)
    assert prev_total_eval_krw() == 2440000.0
