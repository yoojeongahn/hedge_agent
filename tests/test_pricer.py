from unittest.mock import patch
from core.holdings import HoldingPosition, Holdings
from core.pricer import build_portfolio_snapshot


def make_holdings():
    return Holdings(
        positions=[
            HoldingPosition("005930", "삼성전자", "KR", 10, 70000.0),
            HoldingPosition("AAPL", "Apple", "US", 5, 180.0),
        ],
        cash_krw=1_000_000.0,
        cash_usd=500.0,
    )


@patch("core.pricer.fetch_usd_krw", return_value=1380.0)
@patch("core.pricer.fetch_us_price_data")
@patch("core.pricer.fetch_kr_price_data")
def test_build_snapshot(mock_kr, mock_us, mock_rate):
    mock_kr.return_value = {
        "005930": {"close": 75000.0, "ret_7d": 2.0, "ret_30d": 5.0,
                   "week52_high": 80000.0, "week52_low": 55000.0}
    }
    mock_us.return_value = {
        "AAPL": {"close": 185.0, "ret_7d": -1.0, "ret_30d": 3.0,
                 "week52_high": 200.0, "week52_low": 150.0}
    }
    snap = build_portfolio_snapshot(make_holdings())
    assert snap.usd_krw_rate == 1380.0
    kr_pos = next(p for p in snap.positions if p.code == "005930")
    assert kr_pos.current_price_krw == 75000.0
    assert kr_pos.eval_amount_krw == 750_000.0
    us_pos = next(p for p in snap.positions if p.code == "AAPL")
    assert us_pos.current_price_krw == 185.0 * 1380.0
    assert snap.total_eval_krw > 0


@patch("core.pricer.fetch_usd_krw", return_value=1380.0)
@patch("core.pricer.fetch_us_price_data")
@patch("core.pricer.fetch_kr_price_data")
def test_missing_price_skips_position(mock_kr, mock_us, mock_rate):
    mock_kr.return_value = {}
    mock_us.return_value = {
        "AAPL": {"close": 185.0, "ret_7d": None, "ret_30d": None,
                 "week52_high": None, "week52_low": None}
    }
    snap = build_portfolio_snapshot(make_holdings())
    codes = [p.code for p in snap.positions]
    assert "005930" not in codes
    assert "AAPL" in codes
