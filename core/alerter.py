from __future__ import annotations
from dataclasses import dataclass
from core.pricer import PortfolioSnapshot


@dataclass
class Alert:
    type: str
    code: str
    name: str
    message: str
    current_value: float
    threshold: float


def check_alerts(
    snap: PortfolioSnapshot,
    target_weights: dict,
    alert_config: dict,
    prev_total: float | None,
) -> list[Alert]:
    alerts: list[Alert] = []

    for pos in snap.positions:
        tw = target_weights.get(pos.code)
        if tw is None:
            continue

        band = tw["rebalance_band"]
        target = tw["target_pct"]
        if abs(pos.weight_pct - target) > band:
            direction = "과다" if pos.weight_pct > target else "부족"
            alerts.append(Alert(
                type="weight_deviation",
                code=pos.code, name=pos.name,
                message=f"비중 {pos.weight_pct:.1f}% (목표 {target}±{band}%) — {direction}",
                current_value=pos.weight_pct, threshold=target,
            ))

        threshold = alert_config.get("position_loss_pct", -10.0)
        if pos.pnl_pct < threshold:
            alerts.append(Alert(
                type="position_pnl",
                code=pos.code, name=pos.name,
                message=f"평가손익 {pos.pnl_pct:+.2f}% (임계 {threshold}%)",
                current_value=pos.pnl_pct, threshold=threshold,
            ))

    if prev_total and prev_total > 0:
        daily_pct = (snap.total_eval_krw - prev_total) / prev_total * 100
        threshold = alert_config.get("daily_loss_pct", -3.0)
        if daily_pct < threshold:
            alerts.append(Alert(
                type="daily_pnl",
                code="PORTFOLIO", name="포트폴리오",
                message=f"일일 손익 {daily_pct:+.2f}% (임계 {threshold}%)",
                current_value=daily_pct, threshold=threshold,
            ))

    return alerts
