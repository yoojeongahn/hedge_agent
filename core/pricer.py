"""프라이싱 데이터클래스 정의 및 가격 조회 로직."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf
from pykrx import stock as pykrx_stock

from core.holdings import Holdings, HoldingPosition


@dataclass
class PricedPosition:
    code: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float
    current_price_krw: float
    eval_amount_krw: float
    pnl_amount_krw: float
    pnl_pct: float
    weight_pct: float
    ret_7d: float | None
    ret_30d: float | None
    week52_high: float | None
    week52_low: float | None
    broker: str = ""


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    positions: list[PricedPosition]
    cash_krw: float
    cash_usd: float
    usd_krw_rate: float
    total_eval_krw: float
    total_pnl_krw: float
    total_pnl_pct: float


logger = logging.getLogger(__name__)


def fetch_usd_krw() -> float:
    try:
        ticker = yf.Ticker("KRW=X")
        hist = ticker.history(period="2d")
        if hist.empty:
            return 1380.0
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning("환율 조회 실패, 기본값 사용: %s", e)
        return 1380.0


def fetch_kr_price_data(codes: list[str]) -> dict[str, dict]:
    today = datetime.now().strftime("%Y%m%d")
    result: dict[str, dict] = {}
    for code in codes:
        try:
            df = pykrx_stock.get_market_ohlcv(
                (datetime.now() - timedelta(days=400)).strftime("%Y%m%d"),
                today, code
            )
            if df.empty:
                continue
            close = float(df["종가"].iloc[-1])
            ret_7d = _pct_change(df["종가"], 7)
            ret_30d = _pct_change(df["종가"], 30)
            week52_high = float(df["고가"].tail(252).max())
            week52_low = float(df["저가"].tail(252).min())
            result[code] = {
                "close": close, "ret_7d": ret_7d, "ret_30d": ret_30d,
                "week52_high": week52_high, "week52_low": week52_low,
            }
        except Exception as e:
            logger.warning("KR 가격 조회 실패 %s: %s", code, e)
    return result


def fetch_us_price_data(codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for code in codes:
        try:
            ticker = yf.Ticker(code)
            hist = ticker.history(period="1y")
            if hist.empty:
                continue
            close = float(hist["Close"].iloc[-1])
            ret_7d = _pct_change(hist["Close"], 7)
            ret_30d = _pct_change(hist["Close"], 30)
            week52_high = float(hist["High"].max())
            week52_low = float(hist["Low"].min())
            result[code] = {
                "close": close, "ret_7d": ret_7d, "ret_30d": ret_30d,
                "week52_high": week52_high, "week52_low": week52_low,
            }
        except Exception as e:
            logger.warning("US 가격 조회 실패 %s: %s", code, e)
    return result


def _pct_change(series, days: int) -> float | None:
    if len(series) < days + 1:
        return None
    old = float(series.iloc[-(days + 1)])
    now = float(series.iloc[-1])
    return round((now - old) / old * 100, 2) if old else None


def build_portfolio_snapshot(
    holdings: Holdings,
    market_filter: str | None = None,
) -> PortfolioSnapshot:
    """holdings + 가격 데이터 → PortfolioSnapshot.
    market_filter: "KR" | "US" | None (전체)
    """
    usd_krw = fetch_usd_krw()

    positions_to_price = [
        p for p in holdings.positions
        if market_filter is None or p.market == market_filter
    ]

    kr_codes = [p.code for p in positions_to_price if p.market == "KR"]
    us_codes = [p.code for p in positions_to_price if p.market == "US"]

    kr_data = fetch_kr_price_data(kr_codes) if kr_codes else {}
    us_data = fetch_us_price_data(us_codes) if us_codes else {}

    cash_usd_krw = holdings.cash_usd * usd_krw
    total_eval_krw = holdings.cash_krw + cash_usd_krw

    priced: list[PricedPosition] = []
    for pos in positions_to_price:
        data = kr_data.get(pos.code) if pos.market == "KR" else us_data.get(pos.code)
        if data is None:
            continue
        close = data["close"]
        close_krw = close if pos.market == "KR" else close * usd_krw
        eval_krw = pos.quantity * close_krw
        avg_krw = pos.avg_price if pos.market == "KR" else pos.avg_price * usd_krw
        cost_krw = pos.quantity * avg_krw
        pnl_krw = eval_krw - cost_krw
        pnl_pct = round(pnl_krw / cost_krw * 100, 2) if cost_krw else 0.0
        total_eval_krw += eval_krw
        priced.append(PricedPosition(
            code=pos.code, name=pos.name, market=pos.market,
            quantity=pos.quantity, avg_price=pos.avg_price,
            current_price=close, current_price_krw=close_krw,
            eval_amount_krw=eval_krw, pnl_amount_krw=pnl_krw, pnl_pct=pnl_pct,
            weight_pct=0.0,
            ret_7d=data["ret_7d"], ret_30d=data["ret_30d"],
            week52_high=data["week52_high"], week52_low=data["week52_low"],
            broker=pos.broker,
        ))

    for p in priced:
        p.weight_pct = round(p.eval_amount_krw / total_eval_krw * 100, 2) if total_eval_krw else 0.0

    total_cost_krw = sum(
        p.quantity * (p.avg_price if p.market == "KR" else p.avg_price * usd_krw)
        for p in priced
    ) + holdings.cash_krw + cash_usd_krw
    total_pnl_krw = sum(p.pnl_amount_krw for p in priced)
    total_pnl_pct = round(total_pnl_krw / total_cost_krw * 100, 2) if total_cost_krw else 0.0

    return PortfolioSnapshot(
        timestamp=datetime.now(),
        positions=priced,
        cash_krw=holdings.cash_krw,
        cash_usd=holdings.cash_usd,
        usd_krw_rate=usd_krw,
        total_eval_krw=total_eval_krw,
        total_pnl_krw=total_pnl_krw,
        total_pnl_pct=total_pnl_pct,
    )
