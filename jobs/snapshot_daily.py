"""
매일 장 마감 후 실행. cron 예시:
30 16 * * 1-5 cd /path/to/hedge_agent && /usr/bin/python3 -m jobs.snapshot_daily
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가 (cron에서 실행시 import 안정화)
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.broker import Broker
from core.notifier import notify
from core.storage import save_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        broker = Broker()
        snap = broker.fetch_snapshot()
        save_snapshot(snap)
    except Exception as e:
        logger.exception("스냅샷 실패")
        notify(f"⚠️ *스냅샷 실패*\n`{e}`")
        return 1

    msg = (
        f"📊 *일일 스냅샷* ({snap.timestamp:%Y-%m-%d %H:%M})\n"
        f"총평가: `{snap.total_eval:,.0f}원`\n"
        f"평가손익: `{snap.total_pnl:+,.0f}원 ({snap.total_pnl_pct:+.2f}%)`\n"
        f"예수금: `{snap.cash:,.0f}원`\n"
        f"보유: {len(snap.positions)}종목"
    )
    notify(msg)
    logger.info("스냅샷 저장 완료: %s", snap.timestamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
