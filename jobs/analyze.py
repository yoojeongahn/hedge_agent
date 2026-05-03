"""온디맨드 종목 심층 분석. 사용법: python -m jobs.analyze TICKER [STOCK_NAME]"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from core.fundamentals import fetch_fundamentals
from core.technicals import fetch_price_history, calculate_technicals, fetch_kr_supply_demand
from core.chart import generate_chart
from core.news_fetcher import fetch_news_headlines
from core.reporter import generate_analysis_report
from core.notifier import notify, notify_long, send_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def detect_market(ticker: str) -> str:
    """숫자 6자리 → KR, 나머지 → US."""
    return "KR" if ticker.isdigit() and len(ticker) == 6 else "US"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m jobs.analyze TICKER [STOCK_NAME]")
        print("  KR 예: python -m jobs.analyze 005930 삼성전자")
        print("  US 예: python -m jobs.analyze AAPL Apple")
        return 1

    ticker = sys.argv[1].upper()
    name = sys.argv[2] if len(sys.argv) > 2 else ticker
    market = detect_market(sys.argv[1])

    logger.info("심층 분석 시작: %s (%s) [%s]", name, ticker, market)
    notify(f"🔍 *{name} ({ticker})* 분석 시작 중...")

    # 1. 재무 데이터
    fd = None
    try:
        fd = fetch_fundamentals(ticker, name, market)
        logger.info("재무 데이터 수집 완료")
    except Exception as e:
        logger.warning("재무 데이터 실패: %s", e)

    # 2. 기술 지표
    tech = None
    df = None
    try:
        df = fetch_price_history(ticker, market)
        if df is not None and not df.empty:
            foreign_net, institution_net = None, None
            if market == "KR":
                foreign_net, institution_net = fetch_kr_supply_demand(ticker)
            tech = calculate_technicals(df, ticker, market, foreign_net, institution_net)
            logger.info("기술 지표 계산 완료")
        else:
            logger.warning("가격 이력 없음: %s", ticker)
    except Exception as e:
        logger.warning("기술 지표 실패: %s", e)

    # 3. 차트
    chart_path = None
    if df is not None and tech is not None:
        try:
            chart_path = generate_chart(ticker, market, df, tech)
            logger.info("차트 생성 완료: %s", chart_path)
        except Exception as e:
            logger.warning("차트 생성 실패: %s", e)

    # 4. 뉴스
    news = []
    try:
        news = fetch_news_headlines(ticker, name, market, max_results=3)
        logger.info("뉴스 수집 완료: %d건", len(news))
    except Exception as e:
        logger.warning("뉴스 수집 실패: %s", e)

    # 5. Claude 리포트
    report = ""
    if fd is not None and tech is not None:
        try:
            report = generate_analysis_report(fd, tech, news)
            logger.info("Claude 리포트 생성 완료")
        except Exception as e:
            logger.warning("Claude 리포트 실패: %s", e)

    # 6. 텔레그램 전송
    if chart_path and chart_path.exists():
        send_photo(chart_path)
        try:
            chart_path.unlink()
        except Exception:
            pass

    if report:
        notify_long(report)
    else:
        lines = [f"🔍 *{name} ({ticker})* 분석 결과\n"]
        if fd:
            lines.append(f"PER {fd.per} | PBR {fd.pbr} | ROE {fd.roe}%")
        if tech:
            lines.append(f"현재가 {tech.current_price:,.2f} | RSI {tech.rsi14}")
        if news:
            lines.extend([f"· {h}" for h in news])
        notify_long("\n".join(lines))

    logger.info("분석 완료: %s", ticker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
