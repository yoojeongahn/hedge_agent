"""텔레그램 봇으로 알림 전송."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def split_message(text: str, limit: int = 4096) -> list[str]:
    """텔레그램 4096자 제한에 맞게 줄바꿈 단위로 분할. 줄이 limit보다 길면 강제 분할."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        # If a single line exceeds limit, hard-split it
        while len(line) > limit:
            chunk = line[:limit]
            if current:
                parts.append(current.rstrip())
                current = ""
            parts.append(chunk.rstrip())
            line = line[limit:]
        if len(current) + len(line) > limit:
            if current:
                parts.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        parts.append(current.rstrip())
    return parts


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


def notify_long(text: str, parse_mode: str = "Markdown") -> bool:
    """4096자 초과 시 섹션 단위로 분할해서 순서대로 전송."""
    parts = split_message(text)
    success = True
    for part in parts:
        if not notify(part, parse_mode):
            success = False
    return success


def send_photo(image_path: Path, caption: str = "") -> bool:
    """차트 이미지를 텔레그램으로 전송. 전송 후 파일은 호출자가 삭제."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram 미설정 - 이미지 전송 스킵: %s", image_path)
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": f},
                timeout=30,
            )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Telegram 이미지 전송 실패: %s", e)
        return False
