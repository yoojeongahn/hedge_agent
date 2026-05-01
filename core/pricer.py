"""프라이싱 데이터클래스 정의 (가격 조회 로직 없음)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
