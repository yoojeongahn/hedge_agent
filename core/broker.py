"""
한국투자증권 API 래퍼.
잔고 조회와 현재가 조회만 우선 구현. 주문 기능은 의도적으로 빼둠
(MVP는 모니터링·리밸런싱 '제안'까지만, 실제 주문은 본인이 직접).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from pykis import PyKis

load_dotenv()


@dataclass
class Position:
    code: str
    name: str
    quantity: int
    avg_price: float
    current_price: float
    eval_amount: float       # 평가금액
    pnl_amount: float        # 평가손익
    pnl_pct: float           # 평가손익률


@dataclass
class AccountSnapshot:
    timestamp: datetime
    total_eval: float        # 총평가금액
    cash: float              # 예수금
    deposit_d2: float        # D+2 예수금
    positions: list[Position]
    total_pnl: float
    total_pnl_pct: float


class Broker:
    def __init__(self) -> None:
        virtual = os.getenv("KIS_VIRTUAL", "true").lower() == "true"
        self.kis = PyKis(
            id=os.environ["KIS_HTS_ID"],
            account=os.environ["KIS_ACCOUNT"],
            appkey=os.environ["KIS_APP_KEY"],
            secretkey=os.environ["KIS_APP_SECRET"],
            virtual=virtual,
            keep_token=True,
        )
        self.virtual = virtual

    def fetch_snapshot(self) -> AccountSnapshot:
        """현재 계좌 스냅샷 조회."""
        account = self.kis.account()
        balance = account.balance()

        positions: list[Position] = []
        for stock in balance.stocks:
            positions.append(
                Position(
                    code=stock.symbol,
                    name=stock.name,
                    quantity=int(stock.qty),
                    avg_price=float(stock.price),
                    current_price=float(stock.current_price),
                    eval_amount=float(stock.amount),
                    pnl_amount=float(stock.profit),
                    pnl_pct=float(stock.profit_rate),
                )
            )

        deposits = balance.deposits
        # KRW 예수금 (해외주식까지 확장시 통화별 분리 필요)
        krw_deposit = next(
            (d for d in deposits.values() if d.currency == "KRW"),
            None,
        )
        cash = float(krw_deposit.amount) if krw_deposit else 0.0
        deposit_d2 = float(krw_deposit.deposit) if krw_deposit else 0.0

        total_eval = sum(p.eval_amount for p in positions) + cash
        total_pnl = sum(p.pnl_amount for p in positions)
        total_cost = total_eval - total_pnl
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

        return AccountSnapshot(
            timestamp=datetime.now(),
            total_eval=total_eval,
            cash=cash,
            deposit_d2=deposit_d2,
            positions=positions,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
        )

    def fetch_price(self, code: str) -> float:
        """단일 종목 현재가 조회."""
        stock = self.kis.stock(code)
        return float(stock.quote().price)


if __name__ == "__main__":
    # 단독 실행 테스트
    broker = Broker()
    snap = broker.fetch_snapshot()
    print(f"=== {'모의투자' if broker.virtual else '실계좌'} 스냅샷 ===")
    print(f"총평가: {snap.total_eval:,.0f}원")
    print(f"예수금: {snap.cash:,.0f}원")
    print(f"평가손익: {snap.total_pnl:+,.0f}원 ({snap.total_pnl_pct:+.2f}%)")
    print(f"\n보유종목 {len(snap.positions)}개:")
    for p in snap.positions:
        print(f"  {p.name}({p.code}) {p.quantity}주 "
              f"평가 {p.eval_amount:,.0f}원 "
              f"손익 {p.pnl_pct:+.2f}%")
