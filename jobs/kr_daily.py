"""16:30 KST 실행. 국내 당일 종가 기준 간략 리포트."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from dotenv import load_dotenv

load_dotenv()

from core.holdings import load_holdings, Holdings
from core.pricer import build_portfolio_snapshot
from core.alerter import check_alerts
from core.news_fetcher import fetch_portfolio_news
from core.reporter import generate_brief_report
from core.storage import save_snapshot, prev_total_eval_krw
from core.notifier import notify, notify_long

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config"


def load_config() -> tuple[dict, dict]:
    portfolio = yaml.safe_load((CONFIG_PATH / "portfolio.yaml").read_text(encoding="utf-8"))
    return portfolio.get("target_weights", {}), portfolio.get("alerts", {})


def _format_summary(snap) -> str:
    lines = [
        f"📊 *KR 마감* ({snap.timestamp:%Y-%m-%d %H:%M})",
        f"총평가: `{snap.total_eval_krw:,.0f}원` ({snap.total_pnl_pct:+.2f}%)",
    ]
    for p in snap.positions:
        lines.append(f"`{p.name}`: {p.current_price:,.0f}원 ({p.pnl_pct:+.2f}%) 비중 {p.weight_pct:.1f}%")
    return "\n".join(lines)


def main() -> int:
    try:
        target_weights, alert_config = load_config()
        holdings = load_holdings()
        kr_positions = [p for p in holdings.positions if p.market == "KR"]
        if not kr_positions:
            notify("📊 *KR 마감 리포트*\n보유 중인 국내 주식이 없습니다.")
            return 0

        kr_holdings = Holdings(
            positions=kr_positions,
            cash_krw=holdings.cash_krw,
            cash_usd=0.0,
        )
        prev_total = prev_total_eval_krw()
        snap = build_portfolio_snapshot(kr_holdings)
        save_snapshot(snap)
    except Exception as e:
        logger.exception("KR 스냅샷 실패")
        notify(f"⚠️ *KR 스냅샷 실패*\n`{e}`")
        return 1

    try:
        alerts = check_alerts(snap, target_weights, alert_config, prev_total)

        if not alerts:
            notify(_format_summary(snap))
            logger.info("KR 마감 리포트 완료 (알람 없음)")
            return 0

        alerted_codes = {a.code for a in alerts if a.code != "PORTFOLIO"}
        alerted_positions = [p for p in snap.positions if p.code in alerted_codes]
        news = fetch_portfolio_news(alerted_positions)
        comment = generate_brief_report(snap, alerts, news)

        summary = _format_summary(snap)
        if comment:
            notify_long(f"{summary}\n\n{comment}")
        else:
            alert_lines = "\n".join(f"🔴 {a.message}" for a in alerts)
            notify_long(f"{summary}\n\n*알람*\n{alert_lines}")

        logger.info("KR 마감 리포트 완료 (알람 %d건)", len(alerts))
    except Exception as e:
        logger.exception("KR 리포트 생성 실패")
        notify(f"⚠️ *KR 리포트 생성 실패*\n`{e}`")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
