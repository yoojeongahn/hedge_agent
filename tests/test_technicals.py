# tests/test_technicals.py
import pytest
import pandas as pd
import numpy as np
from core.technicals import calculate_technicals, TechnicalsData


def make_price_df(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    """단조 증가하는 가격 시리즈 (지표 계산 검증용)."""
    prices = [start + i * 0.5 for i in range(n)]
    volumes = [1_000_000] * n
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Close": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Volume": volumes,
    }, index=dates)


def test_ma_calculated():
    df = make_price_df(120)
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.ma5 is not None
    assert tech.ma20 is not None
    assert tech.ma60 is not None
    # 단조 증가이므로 ma5 > ma60 (최근 값이 더 높음)
    assert tech.ma5 > tech.ma60


def test_rsi_range():
    df = make_price_df(60)
    tech = calculate_technicals(df, "TEST", "US")
    if tech.rsi14 is not None:
        assert 0 <= tech.rsi14 <= 100


def test_weekly_monthly_trend():
    df = make_price_df(260)  # 52주 이상 → 주봉 20주 + 월봉 12개월 커버
    tech = calculate_technicals(df, "TEST", "US")
    # 단조 증가 시리즈이므로 정배열 (상승) 또는 데이터 부족
    assert tech.weekly_trend in ("정배열 (상승)", "횡보", "데이터 부족")
    assert tech.monthly_trend in ("정배열 (상승)", "횡보", "데이터 부족")
    # MA 값 존재 확인
    assert tech.ma5w is not None
    assert tech.ma10w is not None


def test_volume_ratio():
    df = make_price_df(60)
    df["Volume"] = [500_000] * 40 + [2_000_000] * 20  # 마지막 20일 4배 거래량
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.volume_ratio is not None
    assert tech.volume_ratio > 1.0


def test_short_series_returns_none_gracefully():
    df = make_price_df(10)  # MA60 계산 불가
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.ma60 is None
    assert tech.rsi14 is None
