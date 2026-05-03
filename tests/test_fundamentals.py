# tests/test_fundamentals.py
import pytest
from unittest.mock import patch, MagicMock
from core.fundamentals import fetch_fundamentals, FundamentalsData, QuarterlyPoint


@patch("core.fundamentals.yf.Ticker")
def test_us_fundamentals(mock_ticker):
    mock_info = {
        "trailingPE": 28.4,
        "priceToBook": 45.2,
        "returnOnEquity": 1.47,
        "debtToEquity": 198.0,
        "operatingMargins": 0.317,
        "revenueGrowth": 0.061,
    }
    import pandas as pd
    dates = pd.to_datetime(["2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31"])
    mock_qf = MagicMock()
    mock_qf.empty = False
    mock_qf.columns = dates

    # Mock loc to return revenue row
    def mock_loc_getitem(key):
        return pd.Series([94930e6, 85777e6, 90753e6, 89498e6], index=dates)
    mock_qf.loc.__getitem__ = MagicMock(side_effect=mock_loc_getitem)

    t = MagicMock()
    t.info = mock_info
    t.quarterly_financials = mock_qf
    mock_ticker.return_value = t

    fd = fetch_fundamentals("AAPL", "Apple", "US")
    assert fd.per == pytest.approx(28.4)
    assert fd.pbr == pytest.approx(45.2)
    assert fd.roe == pytest.approx(147.0, abs=1)  # 1.47 * 100
    assert fd.operating_margin == pytest.approx(31.7, abs=1)
    assert fd.market == "US"


def test_missing_us_data_returns_none():
    with patch("core.fundamentals.yf.Ticker") as mock_ticker:
        t = MagicMock()
        t.info = {}
        t.quarterly_financials = MagicMock(empty=True)
        mock_ticker.return_value = t
        fd = fetch_fundamentals("UNKNOWN", "Unknown", "US")
        assert fd.per is None
        assert fd.quarterly == []
