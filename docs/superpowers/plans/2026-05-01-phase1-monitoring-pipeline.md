# Phase 1 모니터링 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** holdings.yaml로 수동 관리하는 KR+US 혼합 포트폴리오를 매일 08:00(US 풀 리포트)과 16:30(KR 간략 리포트)에 자동 모니터링하고 텔레그램으로 Claude 리밸런싱 가이드를 전송한다.

**Architecture:** holdings.yaml → pricer(pykrx/yfinance) → alerter/rebalancer → news_fetcher → reporter(Claude API) → notifier(Telegram) 순서로 데이터가 흐르는 선형 파이프라인 2개. 각 core 모듈은 독립적으로 테스트 가능한 순수 함수/dataclass 구조.

**Tech Stack:** Python 3.11+, pykrx, yfinance, duckduckgo-search, anthropic SDK, sqlite3, pytest, pytest-mock

---

## 파일 맵

| 파일 | 역할 | 상태 |
|------|------|------|
| `config/holdings.yaml` | 보유 내역 (수동 관리) | 기존 (템플릿) |
| `config/portfolio.yaml` | 목표 비중·알람 규칙 | 기존 |
| `core/holdings.py` | holdings.yaml 파싱·검증 | 신규 |
| `core/pricer.py` | KR/US 가격 조회 + 포트폴리오 계산 | 신규 |
| `core/alerter.py` | 알람 3종 체크 | 신규 |
| `core/rebalancer.py` | 비중 차이 수치 계산 | 신규 |
| `core/news_fetcher.py` | DuckDuckGo 뉴스 헤드라인 | 신규 |
| `core/reporter.py` | Claude API 리포트 생성 | 신규 |
| `core/storage.py` | SQLite 저장 (AccountSnapshot → PortfolioSnapshot) | 수정 |
| `core/notifier.py` | 텔레그램 전송 + 분할 전송 | 수정 |
| `jobs/us_morning.py` | 08:00 파이프라인 오케스트레이터 | 신규 |
| `jobs/kr_daily.py` | 16:30 파이프라인 오케스트레이터 | 신규 |
| `tests/test_holdings.py` | holdings.py 테스트 | 신규 |
| `tests/test_pricer.py` | pricer.py 테스트 | 신규 |
| `tests/test_alerter.py` | alerter.py 테스트 | 신규 |
| `tests/test_rebalancer.py` | rebalancer.py 테스트 | 신규 |
| `tests/test_notifier.py` | notifier.py 분할 전송 테스트 | 신규 |

---

## Task 1: 핵심 dataclass 정의 + storage.py 수정

**Files:**
- Create: `core/holdings.py` (dataclass 부분만)
- Modify: `core/storage.py`
- Create: `tests/test_holdings.py` (dataclass 검증)

### 데이터 구조 전체 정의 (Task 1~5에서 사용)

```python
# core/holdings.py 에 정의할 dataclass
from dataclasses import dataclass, field

@dataclass
class HoldingPosition:
    code: str
    name: str
    market: str       # "KR" | "US"
    quantity: int
    avg_price: float
    broker: str = ""

@dataclass
class Holdings:
    positions: list[HoldingPosition]
    cash_krw: float
    cash_usd: float

# core/pricer.py 에 정의할 dataclass
@dataclass
class PricedPosition:
    code: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float      # 원화폐 기준 (KR=원, US=달러)
    current_price_krw: float  # 항상 KRW
    eval_amount_krw: float    # quantity * current_price_krw
    pnl_amount_krw: float
    pnl_pct: float
    weight_pct: float         # 전체 포트폴리오 대비 비중
    ret_7d: float | None
    ret_30d: float | None
    week52_high: float | None
    week52_low: float | None
    broker: str = ""

@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    positions: list[PricedPosition]
    cash_krw: float
    cash_usd: float
    usd_krw_rate: float
    total_eval_krw: float
    total_pnl_krw: float
    total_pnl_pct: float

# core/alerter.py 에 정의할 dataclass
@dataclass
class Alert:
    type: str    # "weight_deviation" | "position_pnl" | "daily_pnl"
    code: str
    name: str
    message: str
    current_value: float
    threshold: float

# core/rebalancer.py 에 정의할 dataclass
@dataclass
class RebalanceDelta:
    code: str
    name: str
    market: str
    current_pct: float
    target_pct: float
    diff_pct: float        # current - target (음수 = 매수 필요)
    diff_amount_krw: float # 목표금액 - 현재금액 (양수 = 매수 필요)
    trade_qty: int
    direction: str         # "BUY" | "SELL"
    current_price: float   # 원화폐 기준
```

- [ ] **Step 1: storage.py 수정을 위한 테스트 작성**

`tests/test_storage_snapshot.py` 생성:

```python
from datetime import datetime
from core.storage import save_snapshot, init_db, latest_snapshot_ts
from core.pricer import PricedPosition, PortfolioSnapshot

def make_snapshot() -> PortfolioSnapshot:
    pos = PricedPosition(
        code="005930", name="삼성전자", market="KR",
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750000.0, pnl_amount_krw=50000.0,
        pnl_pct=7.14, weight_pct=15.0,
        ret_7d=2.1, ret_30d=5.3,
        week52_high=80000.0, week52_low=55000.0,
    )
    return PortfolioSnapshot(
        timestamp=datetime(2026, 5, 1, 16, 30),
        positions=[pos],
        cash_krw=1000000.0,
        cash_usd=500.0,
        usd_krw_rate=1380.0,
        total_eval_krw=2440000.0,
        total_pnl_krw=50000.0,
        total_pnl_pct=2.1,
    )

def test_save_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr("core.storage.DB_PATH", tmp_path / "test.db")
    snap = make_snapshot()
    save_snapshot(snap)
    ts = latest_snapshot_ts()
    assert ts == "2026-05-01T16:30:00"
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_storage_snapshot.py -v
```
Expected: ImportError (PortfolioSnapshot 미정의)

- [ ] **Step 3: core/pricer.py에 dataclass 작성**

```python
# core/pricer.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class PricedPosition:
    code: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float
    current_price_krw: float
    eval_amount_krw: float
    pnl_amount_krw: float
    pnl_pct: float
    weight_pct: float
    ret_7d: float | None
    ret_30d: float | None
    week52_high: float | None
    week52_low: float | None
    broker: str = ""

@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    positions: list[PricedPosition]
    cash_krw: float
    cash_usd: float
    usd_krw_rate: float
    total_eval_krw: float
    total_pnl_krw: float
    total_pnl_pct: float
```

- [ ] **Step 4: core/storage.py 수정**

기존 `AccountSnapshot` import 를 `PortfolioSnapshot` 으로 교체하고 스키마에 `usd_krw_rate` 컬럼 추가:

```python
"""SQLite 기반 스냅샷 저장."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.pricer import PortfolioSnapshot

DB_PATH = Path(__file__).parent.parent / "data" / "snapshots.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    ts            TEXT PRIMARY KEY,
    total_eval    REAL NOT NULL,
    cash          REAL NOT NULL,
    cash_usd      REAL NOT NULL DEFAULT 0,
    usd_krw_rate  REAL NOT NULL DEFAULT 0,
    total_pnl     REAL NOT NULL,
    total_pnl_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    ts             TEXT NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    market         TEXT NOT NULL DEFAULT 'KR',
    quantity       INTEGER NOT NULL,
    avg_price      REAL NOT NULL,
    current_price  REAL NOT NULL,
    eval_amount    REAL NOT NULL,
    pnl_amount     REAL NOT NULL,
    pnl_pct        REAL NOT NULL,
    PRIMARY KEY (ts, code),
    FOREIGN KEY (ts) REFERENCES account_snapshots(ts)
);

CREATE INDEX IF NOT EXISTS idx_position_code ON position_snapshots(code);
"""

@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

def save_snapshot(snap: PortfolioSnapshot) -> None:
    init_db()
    ts = snap.timestamp.isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO account_snapshots
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, snap.total_eval_krw, snap.cash_krw, snap.cash_usd,
             snap.usd_krw_rate, snap.total_pnl_krw, snap.total_pnl_pct),
        )
        for p in snap.positions:
            conn.execute(
                """INSERT OR REPLACE INTO position_snapshots
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, p.code, p.name, p.market, p.quantity, p.avg_price,
                 p.current_price_krw, p.eval_amount_krw,
                 p.pnl_amount_krw, p.pnl_pct),
            )

def latest_snapshot_ts() -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT ts FROM account_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return row["ts"] if row else None

def prev_total_eval_krw() -> float | None:
    """직전 스냅샷의 총평가금액 반환 (일일 손익 계산용)."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT total_eval FROM account_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return float(row["total_eval"]) if row else None
```

- [ ] **Step 5: 테스트 통과 확인**

```
pytest tests/test_storage_snapshot.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add core/pricer.py core/storage.py tests/test_storage_snapshot.py
git commit -m "feat: replace AccountSnapshot with PortfolioSnapshot in storage"
```

---

## Task 2: core/holdings.py — YAML 파싱·검증

**Files:**
- Modify: `core/holdings.py`
- Create: `tests/test_holdings.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_holdings.py
import pytest
import textwrap
from pathlib import Path
from core.holdings import load_holdings, HoldingPosition

SAMPLE_YAML = textwrap.dedent("""
    positions:
      - code: "005930"
        name: "삼성전자"
        market: KR
        quantity: 100
        avg_price: 68000
        broker: "KB증권"
      - code: "AAPL"
        name: "Apple"
        market: US
        quantity: 10
        avg_price: 180.0
        broker: "토스증권"
    cash:
      KRW: 5000000
      USD: 1000
""")

def test_load_valid_yaml(tmp_path):
    f = tmp_path / "holdings.yaml"
    f.write_text(SAMPLE_YAML, encoding="utf-8")
    h = load_holdings(f)
    assert len(h.positions) == 2
    assert h.cash_krw == 5000000
    assert h.cash_usd == 1000

def test_filter_by_market(tmp_path):
    f = tmp_path / "holdings.yaml"
    f.write_text(SAMPLE_YAML, encoding="utf-8")
    h = load_holdings(f)
    kr = [p for p in h.positions if p.market == "KR"]
    us = [p for p in h.positions if p.market == "US"]
    assert len(kr) == 1 and kr[0].code == "005930"
    assert len(us) == 1 and us[0].code == "AAPL"

def test_missing_required_field_raises(tmp_path):
    bad = textwrap.dedent("""
        positions:
          - code: "005930"
            name: "삼성전자"
            market: KR
            quantity: 100
            # avg_price 누락
        cash:
          KRW: 0
          USD: 0
    """)
    f = tmp_path / "holdings.yaml"
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="avg_price"):
        load_holdings(f)
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_holdings.py -v
```
Expected: ImportError

- [ ] **Step 3: core/holdings.py 구현**

```python
# core/holdings.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent / "config" / "holdings.yaml"

@dataclass
class HoldingPosition:
    code: str
    name: str
    market: str   # "KR" | "US"
    quantity: int
    avg_price: float
    broker: str = ""

@dataclass
class Holdings:
    positions: list[HoldingPosition]
    cash_krw: float
    cash_usd: float

def load_holdings(path: Path = CONFIG_PATH) -> Holdings:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    positions: list[HoldingPosition] = []
    for item in data.get("positions", []):
        for field in ("code", "name", "market", "quantity", "avg_price"):
            if field not in item:
                raise ValueError(f"holdings.yaml 항목에 필수 필드 누락: {field} ({item})")
        positions.append(HoldingPosition(
            code=str(item["code"]),
            name=item["name"],
            market=item["market"].upper(),
            quantity=int(item["quantity"]),
            avg_price=float(item["avg_price"]),
            broker=item.get("broker", ""),
        ))
    cash = data.get("cash", {})
    return Holdings(
        positions=positions,
        cash_krw=float(cash.get("KRW", 0)),
        cash_usd=float(cash.get("USD", 0)),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_holdings.py -v
```
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add core/holdings.py tests/test_holdings.py
git commit -m "feat: add holdings.py for YAML-based portfolio input"
```

---

## Task 3: core/pricer.py — 가격 조회 + 포트폴리오 계산

**Files:**
- Modify: `core/pricer.py` (dataclass는 Task 1에서 작성됨)
- Create: `tests/test_pricer.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_pricer.py
from datetime import datetime
from unittest.mock import patch, MagicMock
import pandas as pd
from core.holdings import HoldingPosition, Holdings
from core.pricer import build_portfolio_snapshot

def make_holdings():
    return Holdings(
        positions=[
            HoldingPosition("005930", "삼성전자", "KR", 10, 70000.0),
            HoldingPosition("AAPL", "Apple", "US", 5, 180.0),
        ],
        cash_krw=1_000_000.0,
        cash_usd=500.0,
    )

@patch("core.pricer.fetch_usd_krw", return_value=1380.0)
@patch("core.pricer.fetch_us_price_data")
@patch("core.pricer.fetch_kr_price_data")
def test_build_snapshot(mock_kr, mock_us, mock_rate):
    mock_kr.return_value = {
        "005930": {"close": 75000.0, "ret_7d": 2.0, "ret_30d": 5.0,
                   "week52_high": 80000.0, "week52_low": 55000.0}
    }
    mock_us.return_value = {
        "AAPL": {"close": 185.0, "ret_7d": -1.0, "ret_30d": 3.0,
                 "week52_high": 200.0, "week52_low": 150.0}
    }
    snap = build_portfolio_snapshot(make_holdings())
    assert snap.usd_krw_rate == 1380.0
    kr_pos = next(p for p in snap.positions if p.code == "005930")
    assert kr_pos.current_price_krw == 75000.0
    assert kr_pos.eval_amount_krw == 750_000.0
    us_pos = next(p for p in snap.positions if p.code == "AAPL")
    assert us_pos.current_price_krw == 185.0 * 1380.0
    assert snap.total_eval_krw > 0

@patch("core.pricer.fetch_usd_krw", return_value=1380.0)
@patch("core.pricer.fetch_us_price_data")
@patch("core.pricer.fetch_kr_price_data")
def test_missing_price_skips_position(mock_kr, mock_us, mock_rate):
    mock_kr.return_value = {}   # 005930 가격 없음
    mock_us.return_value = {
        "AAPL": {"close": 185.0, "ret_7d": None, "ret_30d": None,
                 "week52_high": None, "week52_low": None}
    }
    snap = build_portfolio_snapshot(make_holdings())
    codes = [p.code for p in snap.positions]
    assert "005930" not in codes
    assert "AAPL" in codes
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_pricer.py -v
```
Expected: ImportError (build_portfolio_snapshot 미정의)

- [ ] **Step 3: core/pricer.py 구현**

```python
# core/pricer.py (기존 dataclass 아래에 추가)
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import yfinance as yf
from pykrx import stock as pykrx_stock

from core.holdings import Holdings, HoldingPosition

logger = logging.getLogger(__name__)


@dataclass
class PricedPosition:
    code: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float
    current_price_krw: float
    eval_amount_krw: float
    pnl_amount_krw: float
    pnl_pct: float
    weight_pct: float
    ret_7d: float | None
    ret_30d: float | None
    week52_high: float | None
    week52_low: float | None
    broker: str = ""


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    positions: list[PricedPosition]
    cash_krw: float
    cash_usd: float
    usd_krw_rate: float
    total_eval_krw: float
    total_pnl_krw: float
    total_pnl_pct: float


def fetch_usd_krw() -> float:
    try:
        ticker = yf.Ticker("KRW=X")
        hist = ticker.history(period="2d")
        if hist.empty:
            return 1380.0
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning("환율 조회 실패, 기본값 사용: %s", e)
        return 1380.0


def fetch_kr_price_data(codes: list[str]) -> dict[str, dict]:
    today = datetime.now().strftime("%Y%m%d")
    result: dict[str, dict] = {}
    for code in codes:
        try:
            df = pykrx_stock.get_market_ohlcv(
                (datetime.now() - timedelta(days=400)).strftime("%Y%m%d"),
                today, code
            )
            if df.empty:
                continue
            close = float(df["종가"].iloc[-1])
            ret_7d = _pct_change(df["종가"], 7)
            ret_30d = _pct_change(df["종가"], 30)
            week52_high = float(df["고가"].tail(252).max())
            week52_low = float(df["저가"].tail(252).min())
            result[code] = {
                "close": close, "ret_7d": ret_7d, "ret_30d": ret_30d,
                "week52_high": week52_high, "week52_low": week52_low,
            }
        except Exception as e:
            logger.warning("KR 가격 조회 실패 %s: %s", code, e)
    return result


def fetch_us_price_data(codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for code in codes:
        try:
            ticker = yf.Ticker(code)
            hist = ticker.history(period="1y")
            if hist.empty:
                continue
            close = float(hist["Close"].iloc[-1])
            ret_7d = _pct_change(hist["Close"], 7)
            ret_30d = _pct_change(hist["Close"], 30)
            week52_high = float(hist["High"].max())
            week52_low = float(hist["Low"].min())
            result[code] = {
                "close": close, "ret_7d": ret_7d, "ret_30d": ret_30d,
                "week52_high": week52_high, "week52_low": week52_low,
            }
        except Exception as e:
            logger.warning("US 가격 조회 실패 %s: %s", code, e)
    return result


def _pct_change(series, days: int) -> float | None:
    if len(series) < days + 1:
        return None
    old = float(series.iloc[-(days + 1)])
    now = float(series.iloc[-1])
    return round((now - old) / old * 100, 2) if old else None


def build_portfolio_snapshot(
    holdings: Holdings,
    market_filter: str | None = None,
) -> PortfolioSnapshot:
    """holdings + 가격 데이터 → PortfolioSnapshot.
    market_filter: "KR" | "US" | None (전체)
    """
    usd_krw = fetch_usd_krw()

    positions_to_price = [
        p for p in holdings.positions
        if market_filter is None or p.market == market_filter
    ]

    kr_codes = [p.code for p in positions_to_price if p.market == "KR"]
    us_codes = [p.code for p in positions_to_price if p.market == "US"]

    kr_data = fetch_kr_price_data(kr_codes) if kr_codes else {}
    us_data = fetch_us_price_data(us_codes) if us_codes else {}

    cash_usd_krw = holdings.cash_usd * usd_krw
    total_eval_krw = holdings.cash_krw + cash_usd_krw

    priced: list[PricedPosition] = []
    for pos in positions_to_price:
        data = kr_data.get(pos.code) if pos.market == "KR" else us_data.get(pos.code)
        if data is None:
            continue
        close = data["close"]
        close_krw = close if pos.market == "KR" else close * usd_krw
        eval_krw = pos.quantity * close_krw
        avg_krw = pos.avg_price if pos.market == "KR" else pos.avg_price * usd_krw
        cost_krw = pos.quantity * avg_krw
        pnl_krw = eval_krw - cost_krw
        pnl_pct = round(pnl_krw / cost_krw * 100, 2) if cost_krw else 0.0
        total_eval_krw += eval_krw
        priced.append(PricedPosition(
            code=pos.code, name=pos.name, market=pos.market,
            quantity=pos.quantity, avg_price=pos.avg_price,
            current_price=close, current_price_krw=close_krw,
            eval_amount_krw=eval_krw, pnl_amount_krw=pnl_krw, pnl_pct=pnl_pct,
            weight_pct=0.0,  # 아래에서 재계산
            ret_7d=data["ret_7d"], ret_30d=data["ret_30d"],
            week52_high=data["week52_high"], week52_low=data["week52_low"],
            broker=pos.broker,
        ))

    # 비중 계산
    for p in priced:
        p.weight_pct = round(p.eval_amount_krw / total_eval_krw * 100, 2) if total_eval_krw else 0.0

    total_cost_krw = sum(
        p.quantity * (p.avg_price if p.market == "KR" else p.avg_price * usd_krw)
        for p in priced
    ) + holdings.cash_krw + cash_usd_krw
    total_pnl_krw = sum(p.pnl_amount_krw for p in priced)
    total_pnl_pct = round(total_pnl_krw / total_cost_krw * 100, 2) if total_cost_krw else 0.0

    return PortfolioSnapshot(
        timestamp=datetime.now(),
        positions=priced,
        cash_krw=holdings.cash_krw,
        cash_usd=holdings.cash_usd,
        usd_krw_rate=usd_krw,
        total_eval_krw=total_eval_krw,
        total_pnl_krw=total_pnl_krw,
        total_pnl_pct=total_pnl_pct,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_pricer.py -v
```
Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add core/pricer.py tests/test_pricer.py
git commit -m "feat: add pricer.py with KR/US price fetching and portfolio snapshot"
```

---

## Task 4: core/alerter.py — 알람 엔진

**Files:**
- Create: `core/alerter.py`
- Create: `tests/test_alerter.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_alerter.py
from dataclasses import dataclass
from core.alerter import check_alerts, Alert
from core.pricer import PricedPosition, PortfolioSnapshot
from datetime import datetime

def make_pos(code, name, market, weight_pct, pnl_pct):
    return PricedPosition(
        code=code, name=name, market=market,
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750000.0, pnl_amount_krw=50000.0,
        pnl_pct=pnl_pct, weight_pct=weight_pct,
        ret_7d=None, ret_30d=None,
        week52_high=None, week52_low=None,
    )

def make_snap(positions, total_eval_krw=5_000_000.0):
    return PortfolioSnapshot(
        timestamp=datetime.now(), positions=positions,
        cash_krw=1_000_000.0, cash_usd=0.0,
        usd_krw_rate=1380.0,
        total_eval_krw=total_eval_krw,
        total_pnl_krw=0.0, total_pnl_pct=0.0,
    )

TARGET_WEIGHTS = {
    "005930": {"target_pct": 25.0, "rebalance_band": 5.0, "name": "삼성전자"},
}
ALERT_CONFIG = {"daily_loss_pct": -3.0, "position_loss_pct": -10.0}

def test_weight_deviation_triggers():
    # 비중 18% < 목표 25% - 밴드 5% = 20% → 알람
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=18.0, pnl_pct=5.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    types = [a.type for a in alerts]
    assert "weight_deviation" in types

def test_no_alert_within_band():
    # 비중 23% → 목표 25±5% 이내 → 알람 없음
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=23.0, pnl_pct=5.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    assert not any(a.type == "weight_deviation" for a in alerts)

def test_position_pnl_triggers():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=25.0, pnl_pct=-12.0)
    alerts = check_alerts(make_snap([pos]), TARGET_WEIGHTS, ALERT_CONFIG, prev_total=None)
    assert any(a.type == "position_pnl" for a in alerts)

def test_daily_pnl_triggers():
    pos = make_pos("005930", "삼성전자", "KR", weight_pct=25.0, pnl_pct=5.0)
    snap = make_snap([pos], total_eval_krw=4_800_000.0)
    # 전일 5,000,000 → 오늘 4,800,000 = -4% < -3%
    alerts = check_alerts(snap, TARGET_WEIGHTS, ALERT_CONFIG, prev_total=5_000_000.0)
    assert any(a.type == "daily_pnl" for a in alerts)
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_alerter.py -v
```
Expected: ImportError

- [ ] **Step 3: core/alerter.py 구현**

```python
# core/alerter.py
from __future__ import annotations
from dataclasses import dataclass
from core.pricer import PortfolioSnapshot

@dataclass
class Alert:
    type: str
    code: str
    name: str
    message: str
    current_value: float
    threshold: float

def check_alerts(
    snap: PortfolioSnapshot,
    target_weights: dict,
    alert_config: dict,
    prev_total: float | None,
) -> list[Alert]:
    alerts: list[Alert] = []

    for pos in snap.positions:
        tw = target_weights.get(pos.code)
        if tw is None:
            continue

        # 1. 비중 이탈
        band = tw["rebalance_band"]
        target = tw["target_pct"]
        if abs(pos.weight_pct - target) > band:
            direction = "과다" if pos.weight_pct > target else "부족"
            alerts.append(Alert(
                type="weight_deviation",
                code=pos.code, name=pos.name,
                message=f"비중 {pos.weight_pct:.1f}% (목표 {target}±{band}%) — {direction}",
                current_value=pos.weight_pct, threshold=target,
            ))

        # 2. 개별 손익
        threshold = alert_config.get("position_loss_pct", -10.0)
        if pos.pnl_pct < threshold:
            alerts.append(Alert(
                type="position_pnl",
                code=pos.code, name=pos.name,
                message=f"평가손익 {pos.pnl_pct:+.2f}% (임계 {threshold}%)",
                current_value=pos.pnl_pct, threshold=threshold,
            ))

    # 3. 일일 포트폴리오 손익
    if prev_total and prev_total > 0:
        daily_pct = (snap.total_eval_krw - prev_total) / prev_total * 100
        threshold = alert_config.get("daily_loss_pct", -3.0)
        if daily_pct < threshold:
            alerts.append(Alert(
                type="daily_pnl",
                code="PORTFOLIO", name="포트폴리오",
                message=f"일일 손익 {daily_pct:+.2f}% (임계 {threshold}%)",
                current_value=daily_pct, threshold=threshold,
            ))

    return alerts
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_alerter.py -v
```
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add core/alerter.py tests/test_alerter.py
git commit -m "feat: add alerter.py with 3 alert types"
```

---

## Task 5: core/rebalancer.py — 비중 차이 계산

**Files:**
- Create: `core/rebalancer.py`
- Create: `tests/test_rebalancer.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_rebalancer.py
from core.rebalancer import calc_rebalance_deltas, RebalanceDelta
from core.pricer import PricedPosition, PortfolioSnapshot
from datetime import datetime

def make_snap():
    pos = PricedPosition(
        code="005930", name="삼성전자", market="KR",
        quantity=10, avg_price=70000.0,
        current_price=75000.0, current_price_krw=75000.0,
        eval_amount_krw=750_000.0, pnl_amount_krw=50000.0,
        pnl_pct=7.14, weight_pct=15.0,
        ret_7d=None, ret_30d=None,
        week52_high=None, week52_low=None,
    )
    return PortfolioSnapshot(
        timestamp=datetime.now(), positions=[pos],
        cash_krw=1_000_000.0, cash_usd=0.0,
        usd_krw_rate=1380.0,
        total_eval_krw=5_000_000.0,
        total_pnl_krw=50000.0, total_pnl_pct=1.0,
    )

TARGET = {"005930": {"target_pct": 25.0, "rebalance_band": 5.0, "name": "삼성전자"}}

def test_buy_needed():
    # 현재 15%, 목표 25% → 매수 필요
    deltas = calc_rebalance_deltas(make_snap(), TARGET)
    assert len(deltas) == 1
    d = deltas[0]
    assert d.direction == "BUY"
    assert d.diff_amount_krw > 0   # 목표금액 - 현재금액 > 0

def test_within_band_excluded():
    # 밴드 내 종목은 결과에 포함되지 않아야 함
    TARGET_WIDE = {"005930": {"target_pct": 25.0, "rebalance_band": 15.0, "name": "삼성전자"}}
    deltas = calc_rebalance_deltas(make_snap(), TARGET_WIDE)
    assert len(deltas) == 0
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_rebalancer.py -v
```
Expected: ImportError

- [ ] **Step 3: core/rebalancer.py 구현**

```python
# core/rebalancer.py
from __future__ import annotations
from dataclasses import dataclass
from core.pricer import PortfolioSnapshot

@dataclass
class RebalanceDelta:
    code: str
    name: str
    market: str
    current_pct: float
    target_pct: float
    diff_pct: float         # current - target
    diff_amount_krw: float  # 목표금액 - 현재금액 (양수 = 매수)
    trade_qty: int
    direction: str          # "BUY" | "SELL"
    current_price: float    # 원화폐 기준

def calc_rebalance_deltas(
    snap: PortfolioSnapshot,
    target_weights: dict,
) -> list[RebalanceDelta]:
    deltas: list[RebalanceDelta] = []

    for pos in snap.positions:
        tw = target_weights.get(pos.code)
        if tw is None:
            continue
        band = tw["rebalance_band"]
        target_pct = tw["target_pct"]

        if abs(pos.weight_pct - target_pct) <= band:
            continue

        target_amount = snap.total_eval_krw * target_pct / 100
        diff_amount = target_amount - pos.eval_amount_krw
        trade_qty = int(abs(diff_amount) / pos.current_price_krw) if pos.current_price_krw else 0

        deltas.append(RebalanceDelta(
            code=pos.code, name=pos.name, market=pos.market,
            current_pct=pos.weight_pct, target_pct=target_pct,
            diff_pct=round(pos.weight_pct - target_pct, 2),
            diff_amount_krw=round(diff_amount, 0),
            trade_qty=trade_qty,
            direction="BUY" if diff_amount > 0 else "SELL",
            current_price=pos.current_price,
        ))

    return deltas
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_rebalancer.py -v
```
Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add core/rebalancer.py tests/test_rebalancer.py
git commit -m "feat: add rebalancer.py for weight delta calculation"
```

---

## Task 6: core/news_fetcher.py — 뉴스 헤드라인

**Files:**
- Create: `core/news_fetcher.py`

테스트는 DuckDuckGo 실제 호출에 의존하므로 별도 단독 실행 스크립트로 검증한다.

- [ ] **Step 1: core/news_fetcher.py 작성**

```python
# core/news_fetcher.py
from __future__ import annotations

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

def fetch_news_headlines(code: str, name: str, market: str, max_results: int = 3) -> list[str]:
    """종목 뉴스 헤드라인 반환. 실패 시 빈 리스트."""
    query = f"{name} 주식 뉴스" if market == "KR" else f"{code} stock news"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
        return [r["title"] for r in results if "title" in r]
    except Exception as e:
        logger.warning("뉴스 조회 실패 %s: %s", code, e)
        return []

def fetch_portfolio_news(positions: list, max_per_stock: int = 3) -> dict[str, list[str]]:
    """보유 종목 전체 뉴스. {code: [headline, ...]}"""
    return {
        p.code: fetch_news_headlines(p.code, p.name, p.market, max_per_stock)
        for p in positions
    }
```

- [ ] **Step 2: 단독 실행으로 동작 확인**

```bash
python -c "
from core.news_fetcher import fetch_news_headlines
headlines = fetch_news_headlines('005930', '삼성전자', 'KR')
print(headlines)
"
```
Expected: 헤드라인 리스트 출력 (빈 리스트도 OK, 오류 없어야 함)

- [ ] **Step 3: 커밋**

```bash
git add core/news_fetcher.py
git commit -m "feat: add news_fetcher.py with DuckDuckGo headlines"
```

---

## Task 7: core/notifier.py 수정 — 4096자 분할 전송

**Files:**
- Modify: `core/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_notifier.py
from core.notifier import split_message

def test_short_message_not_split():
    parts = split_message("hello", limit=4096)
    assert parts == ["hello"]

def test_long_message_splits_on_newline():
    lines = ["line"] * 200
    msg = "\n".join(lines)   # 200 * 5 = 1000자 (limit=500으로 테스트)
    parts = split_message(msg, limit=500)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 500

def test_each_part_fits_limit():
    msg = "a" * 5000
    parts = split_message(msg, limit=4096)
    for p in parts:
        assert len(p) <= 4096
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_notifier.py -v
```
Expected: ImportError (split_message 미정의)

- [ ] **Step 3: core/notifier.py 수정**

기존 `notify()` 함수는 유지하고 `split_message()`와 `notify_long()` 추가:

```python
"""텔레그램 봇으로 알림 전송."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def split_message(text: str, limit: int = 4096) -> list[str]:
    """텔레그램 4096자 제한에 맞게 줄바꿈 단위로 분할."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
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
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_notifier.py -v
```
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: add split_message and notify_long for 4096 char limit"
```

---

## Task 8: core/reporter.py — Claude 리포트 생성

**Files:**
- Create: `core/reporter.py`

- [ ] **Step 1: core/reporter.py 작성**

```python
# core/reporter.py
from __future__ import annotations

import logging
import os
from anthropic import Anthropic
from core.pricer import PortfolioSnapshot
from core.alerter import Alert
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
        lines.append(
            f"  {p.name}({p.code}): {p.quantity}주 "
            f"현재 {p.current_price:,.0f} "
            f"비중 {p.weight_pct:.1f}% "
            f"손익 {p.pnl_pct:+.2f}% "
            f"| 7일 {p.ret_7d:+.1f}% 30일 {p.ret_30d:+.1f}%"
            if p.ret_7d is not None and p.ret_30d is not None
            else f"  {p.name}({p.code}): {p.quantity}주 현재 {p.current_price:,.0f} 비중 {p.weight_pct:.1f}% 손익 {p.pnl_pct:+.2f}%"
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
    """08:00 풀 리포트 (US 중심)."""
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
    """16:30 간략 리포트 (KR, 알람 있을 때만 Claude 호출)."""
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
```

- [ ] **Step 2: 단독 실행으로 API 응답 확인**

`.env`에 `ANTHROPIC_API_KEY`가 설정된 상태에서:

```bash
python -c "
from core.reporter import generate_full_report
from core.pricer import PricedPosition, PortfolioSnapshot
from datetime import datetime

pos = PricedPosition('AAPL','Apple','US',10,180.0,185.0,185.0*1380,1850*1380,50*1380,2.7,12.0,1.0,-1.5,200.0,150.0)
snap = PortfolioSnapshot(datetime.now(),[pos],1000000,500,1380.0,3_000_000,100000,3.4)
report = generate_full_report(snap, [], [], {})
print(report)
"
```
Expected: 텔레그램용 Markdown 형식 리포트 출력

- [ ] **Step 3: 커밋**

```bash
git add core/reporter.py
git commit -m "feat: add reporter.py with Claude API full/brief report generation"
```

---

## Task 9: jobs/us_morning.py — 08:00 파이프라인

**Files:**
- Create: `jobs/us_morning.py`

- [ ] **Step 1: jobs/us_morning.py 작성**

```python
"""08:00 KST 실행. 미국 전일 종가 기준 풀 리포트."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from dotenv import load_dotenv

load_dotenv()

from core.holdings import load_holdings
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
    target_weights = portfolio.get("target_weights", {})
    alert_config = portfolio.get("alerts", {})
    return target_weights, alert_config


def main() -> int:
    try:
        target_weights, alert_config = load_config()
        holdings = load_holdings()
        # US 포지션만
        us_holdings_positions = [p for p in holdings.positions if p.market == "US"]
        if not us_holdings_positions:
            notify("🌅 *US 모닝 리포트*\n보유 중인 미국 주식이 없습니다.")
            return 0

        from core.holdings import Holdings
        us_holdings = Holdings(
            positions=us_holdings_positions,
            cash_krw=0.0,
            cash_usd=holdings.cash_usd,
        )
        prev_total = prev_total_eval_krw()  # save 전에 호출해야 오늘 데이터가 아닌 전일 데이터를 가져옴
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
            # Claude 실패 시 수치만 전송
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
```

- [ ] **Step 2: 단독 실행 테스트**

```bash
python -m jobs.us_morning
```
Expected: 텔레그램에 US 리포트 수신

- [ ] **Step 3: 커밋**

```bash
git add jobs/us_morning.py
git commit -m "feat: add us_morning.py pipeline (08:00 US full report)"
```

---

## Task 10: jobs/kr_daily.py — 16:30 파이프라인

**Files:**
- Create: `jobs/kr_daily.py`

- [ ] **Step 1: jobs/kr_daily.py 작성**

```python
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
        prev_total = prev_total_eval_krw()  # save 전에 호출해야 전일 데이터를 가져옴
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

        # 알람 있을 때만 뉴스 + Claude 코멘트
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
```

- [ ] **Step 2: 단독 실행 테스트**

```bash
python -m jobs.kr_daily
```
Expected: 텔레그램에 KR 마감 리포트 수신 (알람 없으면 숫자 요약, 알람 있으면 Claude 코멘트 포함)

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
pytest tests/ -v
```
Expected: 모든 테스트 PASS

- [ ] **Step 4: 최종 커밋**

```bash
git add jobs/kr_daily.py
git commit -m "feat: add kr_daily.py pipeline (16:30 KR brief report)"
```

---

## Task 11: Windows 작업 스케줄러 등록

- [ ] **Step 1: PowerShell로 작업 등록**

PowerShell을 관리자 권한으로 열고 실행 (경로를 본인 환경에 맞게 수정):

```powershell
$projectDir = "C:\절대경로\hedge_agent"
$python = "$projectDir\.venv\Scripts\python.exe"

# US 모닝 (08:00 평일)
$actionMorning = New-ScheduledTaskAction -Execute $python -Argument "-m jobs.us_morning" -WorkingDirectory $projectDir
$triggerMorning = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "08:00"
Register-ScheduledTask -TaskName "hedge_us_morning" -Action $actionMorning -Trigger $triggerMorning -RunLevel Highest

# KR 마감 (16:30 평일)
$actionDaily = New-ScheduledTaskAction -Execute $python -Argument "-m jobs.kr_daily" -WorkingDirectory $projectDir
$triggerDaily = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "16:30"
Register-ScheduledTask -TaskName "hedge_kr_daily" -Action $actionDaily -Trigger $triggerDaily -RunLevel Highest
```

- [ ] **Step 2: 등록 확인**

```powershell
Get-ScheduledTask | Where-Object {$_.TaskName -like "hedge_*"}
```
Expected: `hedge_us_morning`, `hedge_kr_daily` 두 태스크 표시

- [ ] **Step 3: 수동 즉시 실행으로 최종 검증**

```powershell
Start-ScheduledTask -TaskName "hedge_us_morning"
Start-ScheduledTask -TaskName "hedge_kr_daily"
```
Expected: 각각 텔레그램 메시지 수신

---

## 전체 테스트 명령

```bash
pytest tests/ -v --tb=short
```

예상 결과:
```
tests/test_holdings.py::test_load_valid_yaml              PASSED
tests/test_holdings.py::test_filter_by_market             PASSED
tests/test_holdings.py::test_missing_required_field_raises PASSED
tests/test_alerter.py::test_weight_deviation_triggers     PASSED
tests/test_alerter.py::test_no_alert_within_band          PASSED
tests/test_alerter.py::test_position_pnl_triggers         PASSED
tests/test_alerter.py::test_daily_pnl_triggers            PASSED
tests/test_rebalancer.py::test_buy_needed                 PASSED
tests/test_rebalancer.py::test_within_band_excluded       PASSED
tests/test_notifier.py::test_short_message_not_split      PASSED
tests/test_notifier.py::test_long_message_splits_on_newline PASSED
tests/test_notifier.py::test_each_part_fits_limit         PASSED
tests/test_storage_snapshot.py::test_save_and_retrieve    PASSED
```
