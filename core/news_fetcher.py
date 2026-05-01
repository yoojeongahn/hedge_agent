from __future__ import annotations

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def fetch_news_headlines(code: str, name: str, market: str, max_results: int = 3) -> list[str]:
    query = f"{name} 주식 뉴스" if market == "KR" else f"{code} stock news"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
        return [r["title"] for r in results if "title" in r]
    except Exception as e:
        logger.warning("뉴스 조회 실패 %s: %s", code, e)
        return []


def fetch_portfolio_news(positions: list, max_per_stock: int = 3) -> dict[str, list[str]]:
    return {
        p.code: fetch_news_headlines(p.code, p.name, p.market, max_per_stock)
        for p in positions
    }
