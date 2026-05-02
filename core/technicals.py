# core/technicals.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FibLevels:
    high: float
    low: float
    level_236: float
    level_382: float
    level_500: float
    level_618: float
    level_786: float
    current_zone: str


@dataclass
class TechnicalsData:
    code: str
    market: str
    current_price: float
    week52_high: float | None
    week52_low: float | None
    # Daily MAs
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    # Indicators
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    # Fibonacci
    fib: FibLevels | None
    # Volume
    volume_ratio: float | None
    # Weekly (주봉: 일봉 리샘플링)
    ma10w: float | None             # 10주 MA ≈ 50거래일
    ma20w: float | None             # 20주 MA ≈ 100거래일
    weekly_trend: str               # "정배열" | "역배열" | "횡보" | "데이터 부족"
    pct_from_52w_high: float | None
    pct_from_52w_low: float | None
    # KR 수급 (US는 None)
    foreign_net_buy_5d: float | None    # 억원
    institution_net_buy_5d: float | None


def fetch_price_history(code: str, market: str) -> pd.DataFrame | None:
    """6개월 일봉 OHLCV 반환. 실패 시 None."""
    try:
        if market == "KR":
            from pykrx import stock as pykrx_stock
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
            df = pykrx_stock.get_market_ohlcv(start, end, code)
            if df.empty:
                return None
            df = df.rename(columns={"시가": "Open", "고가": "High", "저가": "Low",
                                    "종가": "Close", "거래량": "Volume"})
            return df[["Open", "High", "Low", "Close", "Volume"]]
        else:
            import yfinance as yf
            ticker = yf.Ticker(code)
            df = ticker.history(period="2y")  # 주봉 MA20(100일) 계산 위해 2년치
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
    close = df["Close"]
    volume = df["Volume"]
    high = df["High"]
    low = df["Low"]
    n = len(close)

    current_price = float(close.iloc[-1])

    week52_high = float(high.tail(252).max()) if n >= 30 else None
    week52_low = float(low.tail(252).min()) if n >= 30 else None

    ma5 = _ma(close, 5)
    ma10 = _ma(close, 10)
    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)

    rsi14 = _rsi(close, 14)

    macd_val, macd_sig, macd_hist = _macd(close, 12, 26, 9)

    bb_upper, bb_middle, bb_lower = _bollinger(close, 20, 2.0)

    fib = _fibonacci(current_price, week52_high, week52_low) if week52_high and week52_low else None

    volume_ratio = None
    if n >= 21:
        avg_vol = float(volume.iloc[-21:-1].mean())
        curr_vol = float(volume.iloc[-1])
        volume_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else None

    ma10w = _ma(close, 50)
    ma20w = _ma(close, 100)

    weekly_trend = _weekly_trend(ma10w, ma20w, current_price)

    pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
    pct_from_52w_low = round((current_price - week52_low) / week52_low * 100, 2) if week52_low else None

    return TechnicalsData(
        code=code, market=market,
        current_price=current_price,
        week52_high=week52_high, week52_low=week52_low,
        ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60,
        rsi14=rsi14,
        macd=macd_val, macd_signal=macd_sig, macd_hist=macd_hist,
        bb_upper=bb_upper, bb_middle=bb_middle, bb_lower=bb_lower,
        fib=fib,
        volume_ratio=volume_ratio,
        ma10w=ma10w, ma20w=ma20w,
        weekly_trend=weekly_trend,
        pct_from_52w_high=pct_from_52w_high,
        pct_from_52w_low=pct_from_52w_low,
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


def _fibonacci(current: float, high: float, low: float) -> FibLevels:
    rng = high - low
    levels = {
        "236": round(high - 0.236 * rng, 2),
        "382": round(high - 0.382 * rng, 2),
        "500": round(high - 0.500 * rng, 2),
        "618": round(high - 0.618 * rng, 2),
        "786": round(high - 0.786 * rng, 2),
    }
    sorted_vals = sorted(levels.values(), reverse=True)
    zone = "하단 이하"
    keys = list(levels.keys())
    for i in range(len(sorted_vals) - 1):
        if current >= sorted_vals[i + 1]:
            zone = f"{keys[i]}%~{keys[i+1]}% 구간"
            break
    return FibLevels(
        high=high, low=low,
        level_236=levels["236"], level_382=levels["382"],
        level_500=levels["500"], level_618=levels["618"],
        level_786=levels["786"],
        current_zone=zone,
    )


def _weekly_trend(ma10w: float | None, ma20w: float | None, current: float) -> str:
    if ma10w is None or ma20w is None:
        return "데이터 부족"
    if ma10w > ma20w and current > ma10w:
        return "정배열"
    if ma10w < ma20w and current < ma10w:
        return "역배열"
    return "횡보"
