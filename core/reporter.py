from __future__ import annotations

import logging
import os

from anthropic import Anthropic

from core.alerter import Alert
from core.pricer import PortfolioSnapshot
from core.rebalancer import RebalanceDelta

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


def _call_claude(user_msg: str) -> str:
    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
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
