from core.rebalancer import calc_rebalance_deltas, RebalanceDelta
from core.pricer import PricedPosition, PortfolioSnapshot
from datetime import datetime


def make_snap():
    pos = PricedPosition(
        code="005930", name="삼성전자", market="KR",
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750_000.0, pnl_amount_krw=50000.0,
        pnl_pct=7.14, weight_pct=15.0,
        ret_7d=None, ret_30d=None,
        week52_high=None, week52_low=None,
    )
    return PortfolioSnapshot(
        timestamp=datetime.now(), positions=[pos],
        cash_krw=1_000_000.0, cash_usd=0.0,
        usd_krw_rate=1380.0,
        total_eval_krw=5_000_000.0,
        total_pnl_krw=50000.0, total_pnl_pct=1.0,
    )


TARGET = {"005930": {"target_pct": 25.0, "rebalance_band": 5.0, "name": "삼성전자"}}


def test_buy_needed():
    deltas = calc_rebalance_deltas(make_snap(), TARGET)
    assert len(deltas) == 1
    d = deltas[0]
    assert d.direction == "BUY"
    assert d.diff_amount_krw > 0


def test_within_band_excluded():
    TARGET_WIDE = {"005930": {"target_pct": 25.0, "rebalance_band": 15.0, "name": "삼성전자"}}
    deltas = calc_rebalance_deltas(make_snap(), TARGET_WIDE)
    assert len(deltas) == 0
