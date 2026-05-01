"""08:00 KST 실행. 미국 전일 종가 기준 풀 리포트."""
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
from core.rebalancer import calc_rebalance_deltas
from core.news_fetcher import fetch_portfolio_news
from core.reporter import generate_full_report
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


def main() -> int:
    try:
        target_weights, alert_config = load_config()
        holdings = load_holdings()
        us_positions = [p for p in holdings.positions if p.market == "US"]
        if not us_positions:
            notify("🌅 *US 모닝 리포트*\n보유 중인 미국 주식이 없습니다.")
            return 0

        us_holdings = Holdings(
            positions=us_positions,
            cash_krw=0.0,
            cash_usd=holdings.cash_usd,
        )
        prev_total = prev_total_eval_krw()
        snap = build_portfolio_snapshot(us_holdings)
        save_snapshot(snap)
    except Exception as e:
        logger.exception("스냅샷 실패")
        notify(f"⚠️ *US 모닝 스냅샷 실패*\n`{e}`")
        return 1

    try:
        alerts = check_alerts(snap, target_weights, alert_config, prev_total)
        deltas = calc_rebalance_deltas(snap, target_weights)
        news = fetch_portfolio_news(snap.positions)
        report = generate_full_report(snap, alerts, deltas, news)

        if not report:
            lines = [f"🌅 *US 포트폴리오* ({snap.timestamp:%Y-%m-%d} 전일 종가)"]
            for p in snap.positions:
                lines.append(f"`{p.name}`: {p.current_price:.2f} ({p.pnl_pct:+.2f}%)")
            report = "\n".join(lines)

        notify_long(report)
        logger.info("US 모닝 리포트 완료")
    except Exception as e:
        logger.exception("리포트 생성 실패")
        notify(f"⚠️ *US 리포트 생성 실패*\n`{e}`")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
