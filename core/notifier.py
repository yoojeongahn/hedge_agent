"""텔레그램 봇으로 알림 전송. 실패해도 메인 로직은 계속 돌게."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def notify(text: str, parse_mode: str = "Markdown") -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram 미설정 - 알림 스킵: %s", text[:80])
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Telegram 전송 실패: %s", e)
        return False
