from core.alerter import check_alerts, Alert
from core.pricer import PricedPosition, PortfolioSnapshot
from datetime import datetime


def make_pos(code, name, market, weight_pct, pnl_pct):
    return PricedPosition(
        code=code, name=name, market=market,
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750000.0, pnl_amount_krw=50000.0,
        pnl_pct=pnl_pct, weight_pct=weight_pct,
        ret_7d=None, ret_30d=None,
        week52_high=None, week52_low=None,
    )


def make_snap(positions, total_eval_krw=5_000_000.0):
    return PortfolioSnapshot(
        timestamp=datetime.now(), positions=positions,
        cash_krw=1_000_000.0, cash_usd=0.0,
        usd_krw_rate=1380.0,
        total_eval_krw=total_eval_krw,
        total_pnl_krw=0.0, total_pnl_pct=0.0,
    )


TARGET_WEIGHTS = {
    "005930": {"target_pct": 25.0, "rebalance_band": 5.0, "name": "삼성전자"},
}
ALERT_CONFIG = {"daily_loss_pct": -3.0, "position_loss_pct": -10.0}


def test_weight_deviation_triggers():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=18.0, pnl_pct=5.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    assert "weight_deviation" in [a.type for a in alerts]


def test_no_alert_within_band():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=23.0, pnl_pct=5.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    assert not any(a.type == "weight_deviation" for a in alerts)


def test_position_pnl_triggers():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=25.0, pnl_pct=-12.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    assert any(a.type == "position_pnl" for a in alerts)


def test_daily_pnl_triggers():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=25.0, pnl_pct=5.0)
    snap = make_snap([pos], total_eval_krw=4_800_000.0)
    alerts = check_alerts(snap, TARGET_WEIGHTS, ALERT_CONFIG, prev_total=5_000_000.0)
    assert any(a.type == "daily_pnl" for a in alerts)
