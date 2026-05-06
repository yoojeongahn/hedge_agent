# tests/test_reporter.py
from unittest.mock import patch, MagicMock
from core.reporter import generate_analysis_report
from core.fundamentals import FundamentalsData, QuarterlyPoint
from core.technicals import TechnicalsData


def _make_fd():
    return FundamentalsData(
        code="AAPL", name="Apple", market="US",
        per=28.0, pbr=45.0, roe=147.0,
        debt_ratio=198.0, operating_margin=31.7,
        revenue_growth_yoy=6.1,
        quarterly=[QuarterlyPoint("2024Q4", 94930.0, 29000.0)],
    )


def _make_tech():
    return TechnicalsData(
        code="AAPL", market="US", current_price=190.0,
        week52_high=220.0, week52_low=165.0,
        ma5=191.0, ma10=189.0, ma20=185.0, ma60=178.0,
        rsi14=52.0, macd=1.2, macd_signal=0.8, macd_hist=0.4,
        bb_upper=200.0, bb_middle=185.0, bb_lower=170.0,
        volume_ratio=1.2,
        atr14=3.5,
        ma5w=188.0, ma10w=182.0, ma20w=175.0, weekly_trend="정배열",
        pct_from_52w_high=-13.6, pct_from_52w_low=15.2,
        ma3m=183.0, ma6m=178.0, ma12m=170.0, monthly_trend="정배열",
        foreign_net_buy_5d=None, institution_net_buy_5d=None,
    )


@patch("core.reporter._call_claude")
def test_generate_analysis_report_prompt_has_scenarios(mock_claude):
    mock_claude.return_value = "테스트 리포트"
    generate_analysis_report(_make_fd(), _make_tech(), ["뉴스1"])

    call_args = mock_claude.call_args[0][0]
    assert "Bull" in call_args
    assert "Base" in call_args
    assert "Bear" in call_args


@patch("core.reporter._call_claude")
def test_generate_analysis_report_prompt_has_atr_instruction(mock_claude):
    mock_claude.return_value = "테스트 리포트"
    generate_analysis_report(_make_fd(), _make_tech(), [])

    call_args = mock_claude.call_args[0][0]
    assert "ATR" in call_args
