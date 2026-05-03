from __future__ import annotations

import logging
import os
from datetime import datetime

from anthropic import Anthropic

from core.alerter import Alert
from core.fundamentals import FundamentalsData
from core.pricer import PortfolioSnapshot
from core.rebalancer import RebalanceDelta
from core.technicals import TechnicalsData

logger = logging.getLogger(__name__)

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_SYSTEM_PROMPT = """당신은 1인 투자자의 포트폴리오 어드바이저입니다.
주어진 포트폴리오 데이터를 분석하여 간결하고 실용적인 투자 가이드를 제공합니다.
- 확신보다 가능성으로 표현하세요 ("~할 수 있음", "~검토 권장")
- 매수/매도 결정은 사용자가 최종 판단합니다
- 텔레그램 Markdown 형식으로 출력하세요 (*굵게*, `코드`)
"""


def _format_snapshot(snap: PortfolioSnapshot) -> str:
    lines = [
        f"총평가: {snap.total_eval_krw:,.0f}원",
        f"평가손익: {snap.total_pnl_pct:+.2f}%",
        f"현금: KRW {snap.cash_krw:,.0f} / USD {snap.cash_usd:,.0f}",
        f"환율: {snap.usd_krw_rate:,.0f}원/달러",
        "",
        "종목별 현황:",
    ]
    for p in snap.positions:
        if p.ret_7d is not None and p.ret_30d is not None:
            lines.append(
                f"  {p.name}({p.code}): {p.quantity}주 "
                f"현재 {p.current_price:,.0f} "
                f"비중 {p.weight_pct:.1f}% "
                f"손익 {p.pnl_pct:+.2f}% "
                f"| 7일 {p.ret_7d:+.1f}% 30일 {p.ret_30d:+.1f}%"
            )
        else:
            lines.append(
                f"  {p.name}({p.code}): {p.quantity}주 현재 {p.current_price:,.0f} 비중 {p.weight_pct:.1f}% 손익 {p.pnl_pct:+.2f}%"
            )
    return "\n".join(lines)


def _format_alerts(alerts: list[Alert]) -> str:
    if not alerts:
        return "알람 없음"
    return "\n".join(f"🔴 {a.message}" for a in alerts)


def _format_deltas(deltas: list[RebalanceDelta]) -> str:
    if not deltas:
        return "리밸런싱 필요 없음"
    lines = []
    for d in deltas:
        sign = "+" if d.direction == "BUY" else "-"
        lines.append(
            f"  {d.name}({d.code}): 현재 {d.current_pct:.1f}% → 목표 {d.target_pct:.1f}% "
            f"| {d.direction} {d.trade_qty}주 ({sign}{abs(d.diff_amount_krw):,.0f}원)"
        )
    return "\n".join(lines)


def _format_news(news: dict[str, list[str]]) -> str:
    lines = []
    for code, headlines in news.items():
        if headlines:
            lines.append(f"  [{code}]")
            for h in headlines:
                lines.append(f"    · {h}")
    return "\n".join(lines) if lines else "뉴스 없음"


def generate_full_report(
    snap: PortfolioSnapshot,
    alerts: list[Alert],
    deltas: list[RebalanceDelta],
    news: dict[str, list[str]],
) -> str:
    user_msg = f"""아래 포트폴리오 데이터를 바탕으로 일일 리포트를 작성해 주세요.

[포트폴리오 현황]
{_format_snapshot(snap)}

[알람]
{_format_alerts(alerts)}

[리밸런싱 수치]
{_format_deltas(deltas)}

[뉴스 헤드라인]
{_format_news(news)}

출력 형식:
📊 *일일 포트폴리오 리포트* ({snap.timestamp:%Y-%m-%d %H:%M})

[ 오늘의 요약 ]
(총평가, 수익률, 주요 특이사항 2~3줄)

[ 알람 ]
(알람 없으면 이 섹션 생략)

[ 리밸런싱 가이드 ]
(종목별 비중 차이 + 실행 여부 의견, 목표 비중 재검토 필요시 제안)

[ 시황 코멘트 ]
(뉴스·가격 흐름 기반 코멘트 2~3줄)
"""
    return _call_claude(user_msg)


def generate_brief_report(
    snap: PortfolioSnapshot,
    alerts: list[Alert],
    news: dict[str, list[str]],
) -> str:
    user_msg = f"""아래 알람이 발생했습니다. 간단한 코멘트를 작성해 주세요. (3~5줄)

[포트폴리오 현황]
{_format_snapshot(snap)}

[발동 알람]
{_format_alerts(alerts)}

[관련 뉴스]
{_format_news(news)}
"""
    return _call_claude(user_msg)


def _call_claude(user_msg: str, max_tokens: int = 1500) -> str:
    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        return resp.content[0].text
    except Exception as e:
        logger.error("Claude API 실패: %s", e)
        return ""


def _fmt_fundamentals(fd: FundamentalsData) -> str:
    def _v(val, fmt=".1f", suffix=""):
        return f"{val:{fmt}}{suffix}" if val is not None else "N/A"

    lines = [
        f"PER {_v(fd.per)} | PBR {_v(fd.pbr)} | ROE {_v(fd.roe)}%",
        f"부채비율 {_v(fd.debt_ratio)}% | 영업이익률 {_v(fd.operating_margin)}% | 매출성장 {_v(fd.revenue_growth_yoy, '+.1f')}% YoY",
    ]
    if fd.quarterly:
        rev_line = " → ".join(
            f"{q.label} {q.revenue:,.0f}" if q.revenue is not None else f"{q.label} N/A"
            for q in fd.quarterly
        )
        op_line = " → ".join(
            f"{q.label} {q.operating_profit:,.0f}" if q.operating_profit is not None else f"{q.label} N/A"
            for q in fd.quarterly
        )
        unit = "억원" if fd.market == "KR" else "M USD"
        lines.append(f"분기매출({unit}): {rev_line}")
        lines.append(f"분기영업이익({unit}): {op_line}")
    return "\n".join(lines)


def _fmt_technicals(tech: TechnicalsData) -> str:
    def _v(val, fmt=".2f"):
        return f"{val:{fmt}}" if val is not None else "N/A"
    def _arr(cur, ref):
        if cur is None or ref is None:
            return ""
        return "↑" if cur > ref else "↓"

    lines = [
        # 월봉
        f"[월봉] MA3M {_v(tech.ma3m)}  MA6M {_v(tech.ma6m)}  MA12M {_v(tech.ma12m)} → {tech.monthly_trend}",
        # 주봉
        f"[주봉] MA5W {_v(tech.ma5w)}  MA10W {_v(tech.ma10w)}  MA20W {_v(tech.ma20w)} → {tech.weekly_trend}",
        # 일봉
        f"[일봉] 현재가 {tech.current_price:,.2f}",
        f"MA5 {_v(tech.ma5)}{_arr(tech.current_price, tech.ma5)}  "
        f"MA10 {_v(tech.ma10)}{_arr(tech.current_price, tech.ma10)}  "
        f"MA20 {_v(tech.ma20)}{_arr(tech.current_price, tech.ma20)}  "
        f"MA60 {_v(tech.ma60)}{_arr(tech.current_price, tech.ma60)}",
        f"RSI {_v(tech.rsi14)} | MACD {_v(tech.macd)} / Signal {_v(tech.macd_signal)}",
        f"볼린저밴드 상단 {_v(tech.bb_upper)} / 하단 {_v(tech.bb_lower)}",
        f"거래량 {_v(tech.volume_ratio, '.1f')}배 (20일 평균 대비)",
    ]
    if tech.pct_from_52w_high is not None:
        lines.append(
            f"52주 고점 대비 {tech.pct_from_52w_high:+.1f}% | "
            f"52주 저점 대비 {tech.pct_from_52w_low:+.1f}%"
        )
    return "\n".join(lines)


def _fmt_supply(tech: TechnicalsData) -> str | None:
    if tech.foreign_net_buy_5d is None and tech.institution_net_buy_5d is None:
        return None
    parts = []
    if tech.foreign_net_buy_5d is not None:
        parts.append(f"외국인 {tech.foreign_net_buy_5d:+,.0f}억")
    if tech.institution_net_buy_5d is not None:
        parts.append(f"기관 {tech.institution_net_buy_5d:+,.0f}억")
    return "  ".join(parts)


def generate_analysis_report(
    fd: FundamentalsData,
    tech: TechnicalsData,
    news: list[str],
) -> str:
    """Claude 심층 분석 리포트 생성."""
    supply_str = _fmt_supply(tech)
    news_str = "\n".join(f"· {h}" for h in news) if news else "뉴스 없음"

    supply_section = f"\n[수급 (최근 5거래일)]\n{supply_str}" if supply_str else ""
    supply_output = "\n━━━ 🏦 수급 ━━━\n(외국인·기관 순매수)" if supply_str else ""

    user_msg = f"""아래 종목 데이터를 바탕으로 심층 분석 리포트를 작성해 주세요.

종목: {fd.name} ({fd.code}) | 시장: {fd.market}

[재무 지표]
{_fmt_fundamentals(fd)}

[기술 지표]
{_fmt_technicals(tech)}
{supply_section}

[뉴스]
{news_str}

출력 형식 (텔레그램 Markdown):
🔍 *{fd.name} ({fd.code}) 심층 분석* | {datetime.now().strftime('%Y-%m-%d')}

━━━ 📊 재무 ━━━
(PER/PBR/ROE/부채비율/영업이익률/매출성장 + 분기 추이)

━━━ 📈 멀티타임프레임 추세 ━━━
월봉: (MA3M/6M/12M 배열 → 장기 방향)
주봉: (MA5W/10W/20W 배열 → 중기 방향)
일봉: (MA5/20/60 + RSI + MACD + 볼린저밴드 + 거래량){supply_output}

━━━ 📰 뉴스 ━━━
(헤드라인 나열)

━━━ 🤖 Claude 의견 ━━━
*단기 (단타):* (일봉 지표·수급·거래량 기반 진입 타이밍)
*중장기 (가치+차트):* (재무 건전성·섹터 평균 PER 감안 밸류에이션·월봉/주봉 추세 종합)

지시사항:
- 월봉→주봉→일봉 순서로 큰 추세에서 작은 추세를 확인하는 탑다운 분석
- 섹터 평균 PER를 감안하여 현재 밸류에이션 수준 평가
- 매수/매도 결정은 사용자 최종 판단 (제안만)
"""
    return _call_claude(user_msg, max_tokens=3000)
