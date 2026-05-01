from __future__ import annotations
from dataclasses import dataclass
from core.pricer import PortfolioSnapshot


@dataclass
class RebalanceDelta:
    code: str
    name: str
    market: str
    current_pct: float
    target_pct: float
    diff_pct: float
    diff_amount_krw: float
    trade_qty: int
    direction: str  # "BUY" | "SELL"
    current_price: float


def calc_rebalance_deltas(
    snap: PortfolioSnapshot,
    target_weights: dict,
) -> list[RebalanceDelta]:
    deltas: list[RebalanceDelta] = []

    for pos in snap.positions:
        tw = target_weights.get(pos.code)
        if tw is None:
            continue
        band = tw["rebalance_band"]
        target_pct = tw["target_pct"]

        if abs(pos.weight_pct - target_pct) <= band:
            continue

        target_amount = snap.total_eval_krw * target_pct / 100
        diff_amount = target_amount - pos.eval_amount_krw
        trade_qty = int(abs(diff_amount) / pos.current_price_krw) if pos.current_price_krw else 0

        deltas.append(RebalanceDelta(
            code=pos.code, name=pos.name, market=pos.market,
            current_pct=pos.weight_pct, target_pct=target_pct,
            diff_pct=round(pos.weight_pct - target_pct, 2),
            diff_amount_krw=round(diff_amount, 0),
            trade_qty=trade_qty,
            direction="BUY" if diff_amount > 0 else "SELL",
            current_price=pos.current_price,
        ))

    return deltas
