# core/technicals.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TechnicalsData:
    code: str
    market: str
    current_price: float
    week52_high: float | None
    week52_low: float | None
    # 일봉 MAs
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    # 일봉 지표
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    volume_ratio: float | None
    # 주봉 MAs (weekly resample)
    ma5w: float | None
    ma10w: float | None
    ma20w: float | None
    weekly_trend: str        # "정배열 (상승)" | "역배열 (하락)" | "횡보" | "데이터 부족"
    pct_from_52w_high: float | None
    pct_from_52w_low: float | None
    # 월봉 MAs (monthly resample)
    ma3m: float | None
    ma6m: float | None
    ma12m: float | None
    monthly_trend: str       # "정배열 (상승)" | "역배열 (하락)" | "횡보" | "데이터 부족"
    # KR 수급 (US는 None)
    foreign_net_buy_5d: float | None
    institution_net_buy_5d: float | None


def fetch_price_history(code: str, market: str) -> pd.DataFrame | None:
    """일봉 OHLCV 반환 (KR 500일, US 2년). 실패 시 None."""
    try:
        if market == "KR":
            from pykrx import stock as pykrx_stock
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=500)).strftime("%Y%m%d")
            df = pykrx_stock.get_market_ohlcv(start, end, code)
            if df.empty:
                return None
            df = df.rename(columns={"시가": "Open", "고가": "High", "저가": "Low",
                                    "종가": "Close", "거래량": "Volume"})
            return df[["Open", "High", "Low", "Close", "Volume"]]
        else:
            import yfinance as yf
            ticker = yf.Ticker(code)
            df = ticker.history(period="2y")
            if df.empty:
                return None
            return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        logger.warning("가격 이력 조회 실패 %s: %s", code, e)
        return None


def calculate_technicals(
    df: pd.DataFrame,
    code: str,
    market: str,
    foreign_net: float | None = None,
    institution_net: float | None = None,
) -> TechnicalsData:
    """가격 DataFrame → TechnicalsData."""
    # DatetimeIndex 보장 (yfinance 타임존 제거)
    _df = df.copy()
    if hasattr(_df.index, "tz") and _df.index.tz is not None:
        _df.index = _df.index.tz_localize(None)
    _df.index = pd.DatetimeIndex(_df.index)

    close = _df["Close"]
    volume = _df["Volume"]
    high = _df["High"]
    low = _df["Low"]
    n = len(close)

    current_price = float(close.iloc[-1])

    week52_high = float(high.tail(252).max()) if n >= 30 else None
    week52_low = float(low.tail(252).min()) if n >= 30 else None

    # 일봉 지표
    ma5 = _ma(close, 5)
    ma10 = _ma(close, 10)
    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)

    rsi14 = _rsi(close, 14)
    macd_val, macd_sig, macd_hist = _macd(close, 12, 26, 9)
    bb_upper, bb_middle, bb_lower = _bollinger(close, 20, 2.0)

    volume_ratio = None
    if n >= 21:
        avg_vol = float(volume.iloc[-21:-1].mean())
        curr_vol = float(volume.iloc[-1])
        volume_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else None

    pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
    pct_from_52w_low = round((current_price - week52_low) / week52_low * 100, 2) if week52_low else None

    # 주봉 리샘플링
    weekly_close = _resample_close(_df, "W")
    ma5w = _ma(weekly_close, 5)
    ma10w = _ma(weekly_close, 10)
    ma20w = _ma(weekly_close, 20)
    weekly_trend = _trend(ma5w, ma10w, ma20w, current_price)

    # 월봉 리샘플링
    monthly_close = _resample_close(_df, "ME")
    ma3m = _ma(monthly_close, 3)
    ma6m = _ma(monthly_close, 6)
    ma12m = _ma(monthly_close, 12)
    monthly_trend = _trend(ma3m, ma6m, ma12m, current_price)

    return TechnicalsData(
        code=code, market=market,
        current_price=current_price,
        week52_high=week52_high, week52_low=week52_low,
        ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60,
        rsi14=rsi14,
        macd=macd_val, macd_signal=macd_sig, macd_hist=macd_hist,
        bb_upper=bb_upper, bb_middle=bb_middle, bb_lower=bb_lower,
        volume_ratio=volume_ratio,
        ma5w=ma5w, ma10w=ma10w, ma20w=ma20w,
        weekly_trend=weekly_trend,
        pct_from_52w_high=pct_from_52w_high,
        pct_from_52w_low=pct_from_52w_low,
        ma3m=ma3m, ma6m=ma6m, ma12m=ma12m,
        monthly_trend=monthly_trend,
        foreign_net_buy_5d=foreign_net,
        institution_net_buy_5d=institution_net,
    )


def fetch_kr_supply_demand(code: str) -> tuple[float | None, float | None]:
    """KR 외국인·기관 최근 5거래일 순매수 합계 (억원). 실패 시 (None, None)."""
    try:
        from pykrx import stock as pykrx_stock
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        df = pykrx_stock.get_market_trading_value_by_date(start, end, code)
        if df.empty:
            return None, None
        recent = df.tail(5)
        foreign = float(recent["외국인합계"].sum()) / 1e8 if "외국인합계" in recent.columns else None
        institution = float(recent["기관합계"].sum()) / 1e8 if "기관합계" in recent.columns else None
        return (round(foreign, 0) if foreign is not None else None,
                round(institution, 0) if institution is not None else None)
    except Exception as e:
        logger.warning("KR 수급 조회 실패 %s: %s", code, e)
        return None, None


# ── 지표 계산 헬퍼 ──────────────────────────────────────────

def _resample_close(df: pd.DataFrame, freq: str) -> pd.Series:
    """OHLCV DataFrame을 freq 주기로 리샘플해 종가 Series 반환."""
    try:
        return df["Close"].resample(freq).last().dropna()
    except Exception:
        try:
            # pandas < 2.2 fallback: ME → M
            fallback = "M" if freq == "ME" else freq
            return df["Close"].resample(fallback).last().dropna()
        except Exception:
            return pd.Series(dtype=float)


def _ma(series: pd.Series, period: int) -> float | None:
    if len(series) < period:
        return None
    return round(float(series.tail(period).mean()), 2)


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.tail(period).mean()
    avg_loss = loss.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _macd(series: pd.Series, fast: int, slow: int, signal: int
          ) -> tuple[float | None, float | None, float | None]:
    if len(series) < slow + signal:
        return None, None, None
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return (round(float(macd_line.iloc[-1]), 4),
            round(float(signal_line.iloc[-1]), 4),
            round(float(hist.iloc[-1]), 4))


def _bollinger(series: pd.Series, period: int, std_mult: float
               ) -> tuple[float | None, float | None, float | None]:
    if len(series) < period:
        return None, None, None
    rolling = series.tail(period)
    mid = float(rolling.mean())
    std = float(rolling.std())
    return round(mid + std_mult * std, 2), round(mid, 2), round(mid - std_mult * std, 2)


def _trend(ma_fast: float | None, ma_mid: float | None, ma_slow: float | None, current: float) -> str:
    """3개 이평선 배열과 현재가로 추세 판단."""
    if ma_fast is None or ma_mid is None:
        return "데이터 부족"
    if ma_slow is None:
        if ma_fast > ma_mid and current > ma_fast:
            return "상승"
        if ma_fast < ma_mid and current < ma_fast:
            return "하락"
        return "횡보"
    if ma_fast > ma_mid > ma_slow:
        return "정배열 (상승)"
    if ma_fast < ma_mid < ma_slow:
        return "역배열 (하락)"
    return "횡보"
