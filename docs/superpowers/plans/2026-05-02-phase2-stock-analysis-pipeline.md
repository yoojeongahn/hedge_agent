# Phase 2 심층 분석 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m jobs.analyze TICKER` 한 줄로 재무·기술·수급·뉴스를 종합한 심층 분석 리포트(텍스트 + 4패널 차트 이미지)를 텔레그램으로 수신하는 온디맨드 분석 도구.

**Architecture:** CLI → fundamentals.py(DART/yfinance) + technicals.py(pykrx/yfinance) + chart.py(matplotlib) → reporter.py(Claude) → notifier.py(텔레그램 텍스트+이미지). 각 단계 실패 시 해당 섹션만 생략하는 graceful degradation.

**Tech Stack:** Python 3.11+, dart-fss (KR 재무), pykrx (기존, KR 수급), yfinance (기존, US 전체 + KR 가격), matplotlib (차트), anthropic SDK (기존)

---

## 파일 맵

| 파일 | 역할 | 상태 |
|------|------|------|
| `core/fundamentals.py` | FundamentalsData dataclass + KR/US 재무 수집 | 신규 |
| `core/technicals.py` | TechnicalsData dataclass + 기술 지표 계산 + KR 수급 | 신규 |
| `core/chart.py` | matplotlib 4패널 차트 생성 | 신규 |
| `core/reporter.py` | `generate_analysis_report()` 추가 | 수정 |
| `core/notifier.py` | `send_photo()` 추가 | 수정 |
| `jobs/analyze.py` | CLI 오케스트레이터 | 신규 |
| `tests/test_fundamentals.py` | 재무 모듈 테스트 | 신규 |
| `tests/test_technicals.py` | 기술 지표 테스트 | 신규 |
| `requirements.txt` | dart-fss, matplotlib 추가 | 수정 |
| `.env.example` | DART_API_KEY 추가 | 수정 |

---

## Task 1: Spike — dart-fss 검증 + 의존성 추가

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Create (임시, 스파이크 후 삭제): `verify_dart.py`

- [ ] **Step 1: requirements.txt 업데이트**

```
pyyaml>=6.0
python-dotenv>=1.0.0
requests>=2.31.0
pandas>=2.0.0
anthropic>=0.40.0
pykrx>=1.0.45
yfinance>=0.2.0
duckduckgo-search>=6.0.0
dart-fss>=0.4.0
matplotlib>=3.8.0
```

- [ ] **Step 2: .env.example 업데이트**

기존 내용 유지 + 아래 추가:

```
# DART Open API (KR 재무제표 — opendart.fss.or.kr 에서 무료 발급)
DART_API_KEY=
```

- [ ] **Step 3: 의존성 설치**

```powershell
.venv\Scripts\pip install dart-fss matplotlib
```

Expected: `Successfully installed dart-fss-x.x.x matplotlib-x.x.x`

- [ ] **Step 4: verify_dart.py 작성 후 실행**

`.env`에 `DART_API_KEY`가 설정된 상태에서:

```python
# verify_dart.py
import os
from dotenv import load_dotenv
load_dotenv()

import dart_fss as dart
dart.set_api_key(api_key=os.environ["DART_API_KEY"])

# 1. 기업 코드 조회
corp_list = dart.get_corp_list()
corps = corp_list.find_by_stock_code("005930")
print("found:", [(c.corp_code, c.corp_name) for c in corps])
corp = corps[0]

# 2. 재무제표 추출
from datetime import datetime, timedelta
end = datetime.now().strftime("%Y%m%d")
start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

fs = dart.fs.extract(
    corp_code=corp.corp_code,
    bgn_de=start,
    end_de=end,
    fs_tp="CFS",
)
print("fs type:", type(fs))
if fs:
    print("keys:", list(fs.keys()) if hasattr(fs, 'keys') else dir(fs))
    is_df = fs.show("IS") if hasattr(fs, "show") else fs.get("IS")
    if is_df is not None:
        print("IS columns:", is_df.columns.tolist()[:10])
        # 매출액, 영업이익 행 찾기
        for kw in ["매출", "영업이익", "revenue", "operating"]:
            mask = is_df.index.str.contains(kw, case=False, na=False)
            if mask.any():
                print(f"'{kw}' rows:", is_df[mask].head(2).to_string())
```

Run: `PYTHONPATH=. .venv\Scripts\python verify_dart.py`

Expected: corp_code 출력, 재무제표 컬럼 확인. 출력 결과를 Task 3 구현에 반영.

- [ ] **Step 5: verify_dart.py 삭제**

```bash
git rm --cached verify_dart.py 2>/dev/null; rm verify_dart.py
```

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt .env.example
git commit -m "feat: add dart-fss and matplotlib dependencies for Phase 2"
```

---

## Task 2: core/fundamentals.py — dataclass + US 구현

**Files:**
- Create: `core/fundamentals.py`
- Create: `tests/test_fundamentals.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_fundamentals.py
import pytest
from unittest.mock import patch, MagicMock
from core.fundamentals import fetch_fundamentals, FundamentalsData, QuarterlyPoint


@patch("core.fundamentals.yf.Ticker")
def test_us_fundamentals(mock_ticker):
    mock_info = {
        "trailingPE": 28.4,
        "priceToBook": 45.2,
        "returnOnEquity": 1.47,
        "debtToEquity": 198.0,
        "operatingMargins": 0.317,
        "revenueGrowth": 0.061,
    }
    mock_qf = MagicMock()
    mock_qf.empty = False
    import pandas as pd
    import numpy as np
    dates = pd.to_datetime(["2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31"])
    mock_qf.columns = dates
    mock_qf.loc.__getitem__ = MagicMock(return_value=pd.Series(
        [94930e6, 85777e6, 90753e6, 89498e6], index=dates
    ))

    t = MagicMock()
    t.info = mock_info
    t.quarterly_financials = mock_qf
    mock_ticker.return_value = t

    fd = fetch_fundamentals("AAPL", "Apple", "US")
    assert fd.per == pytest.approx(28.4)
    assert fd.pbr == pytest.approx(45.2)
    assert fd.roe == pytest.approx(147.0, abs=1)  # 1.47 * 100
    assert fd.operating_margin == pytest.approx(31.7, abs=1)
    assert fd.market == "US"


def test_missing_us_data_returns_none():
    with patch("core.fundamentals.yf.Ticker") as mock_ticker:
        t = MagicMock()
        t.info = {}
        t.quarterly_financials = MagicMock(empty=True)
        mock_ticker.return_value = t
        fd = fetch_fundamentals("UNKNOWN", "Unknown", "US")
        assert fd.per is None
        assert fd.quarterly == []
```

- [ ] **Step 2: 테스트 실패 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_fundamentals.py -v
```

Expected: ImportError

- [ ] **Step 3: core/fundamentals.py 작성 (dataclass + US)**

```python
# core/fundamentals.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class QuarterlyPoint:
    label: str          # "2024Q3", "2024Q2", ...
    revenue: float | None
    operating_profit: float | None


@dataclass
class FundamentalsData:
    code: str
    name: str
    market: str
    per: float | None
    pbr: float | None
    roe: float | None               # %
    debt_ratio: float | None        # %
    operating_margin: float | None  # %
    revenue_growth_yoy: float | None  # %
    quarterly: list[QuarterlyPoint] = field(default_factory=list)


def fetch_fundamentals(code: str, name: str, market: str) -> FundamentalsData:
    if market == "US":
        return _fetch_us(code, name)
    return _fetch_kr(code, name)


def _fetch_us(code: str, name: str) -> FundamentalsData:
    try:
        ticker = yf.Ticker(code)
        info = ticker.info
    except Exception as e:
        logger.warning("US 기본정보 조회 실패 %s: %s", code, e)
        info = {}

    def _pct(val: float | None) -> float | None:
        return round(val * 100, 2) if val is not None else None

    quarterly = []
    try:
        qf = ticker.quarterly_financials
        if not qf.empty:
            for col in list(qf.columns)[:4]:
                label = f"{col.year}Q{(col.month - 1) // 3 + 1}"
                try:
                    rev_row = [r for r in qf.index if "revenue" in str(r).lower() or "total rev" in str(r).lower()]
                    op_row = [r for r in qf.index if "operating" in str(r).lower() and "income" in str(r).lower()]
                    rev = float(qf.loc[rev_row[0], col]) / 1e8 if rev_row else None   # 억 단위
                    op = float(qf.loc[op_row[0], col]) / 1e8 if op_row else None
                    quarterly.append(QuarterlyPoint(label=label, revenue=rev, operating_profit=op))
                except Exception:
                    quarterly.append(QuarterlyPoint(label=label, revenue=None, operating_profit=None))
    except Exception as e:
        logger.warning("US 분기 데이터 조회 실패 %s: %s", code, e)

    return FundamentalsData(
        code=code, name=name, market="US",
        per=info.get("trailingPE"),
        pbr=info.get("priceToBook"),
        roe=_pct(info.get("returnOnEquity")),
        debt_ratio=info.get("debtToEquity"),
        operating_margin=_pct(info.get("operatingMargins")),
        revenue_growth_yoy=_pct(info.get("revenueGrowth")),
        quarterly=quarterly,
    )


def _fetch_kr(code: str, name: str) -> FundamentalsData:
    """KR 재무: pykrx(PER/PBR) + dart-fss(ROE/부채비율/분기). dart-fss 실패 시 부분 반환."""
    per, pbr = _fetch_kr_ratios(code)
    roe, debt_ratio, op_margin, rev_growth, quarterly = _fetch_kr_dart(code)

    return FundamentalsData(
        code=code, name=name, market="KR",
        per=per, pbr=pbr,
        roe=roe, debt_ratio=debt_ratio,
        operating_margin=op_margin,
        revenue_growth_yoy=rev_growth,
        quarterly=quarterly,
    )


def _fetch_kr_ratios(code: str) -> tuple[float | None, float | None]:
    try:
        from pykrx import stock as pykrx_stock
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        df = pykrx_stock.get_market_fundamental(today, today, code)
        if df.empty:
            return None, None
        per = float(df["PER"].iloc[-1]) if "PER" in df.columns else None
        pbr = float(df["PBR"].iloc[-1]) if "PBR" in df.columns else None
        return (None if per == 0 else per), (None if pbr == 0 else pbr)
    except Exception as e:
        logger.warning("KR PER/PBR 조회 실패 %s: %s", code, e)
        return None, None


def _fetch_kr_dart(
    code: str,
) -> tuple[float | None, float | None, float | None, float | None, list[QuarterlyPoint]]:
    """dart-fss로 ROE, 부채비율, 영업이익률, 매출성장률, 분기 데이터 반환."""
    dart_key = os.getenv("DART_API_KEY")
    if not dart_key:
        logger.warning("DART_API_KEY 미설정 — KR 재무 상세 스킵")
        return None, None, None, None, []
    try:
        import dart_fss as dart
        from datetime import datetime, timedelta
        dart.set_api_key(api_key=dart_key)
        corp_list = dart.get_corp_list()
        corps = corp_list.find_by_stock_code(code)
        if not corps:
            logger.warning("DART 기업 코드 조회 실패: %s", code)
            return None, None, None, None, []
        corp_code = corps[0].corp_code

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=550)).strftime("%Y%m%d")
        fs = dart.fs.extract(corp_code=corp_code, bgn_de=start, end_de=end, fs_tp="CFS")
        if not fs:
            return None, None, None, None, []

        is_df = fs.show("IS")
        bs_df = fs.show("BS")

        roe = _kr_calc_roe(is_df, bs_df)
        debt_ratio = _kr_calc_debt_ratio(bs_df)
        op_margin, rev_growth = _kr_calc_margins(is_df)
        quarterly = _kr_quarterly(corp_code, dart)

        return roe, debt_ratio, op_margin, rev_growth, quarterly
    except Exception as e:
        logger.warning("DART 재무 조회 실패 %s: %s", code, e)
        return None, None, None, None, []


def _kr_find_row(df, keywords: list[str]) -> float | None:
    """DataFrame에서 키워드가 포함된 첫 행의 최신 값 반환."""
    if df is None or df.empty:
        return None
    for kw in keywords:
        mask = df.index.str.contains(kw, case=False, na=False)
        if mask.any():
            row = df[mask].iloc[0]
            # 가장 최근 컬럼 값 (숫자로 변환 가능한 마지막 컬럼)
            for col in reversed(row.index.tolist()):
                try:
                    val = float(str(row[col]).replace(",", ""))
                    if val != 0:
                        return val
                except (ValueError, TypeError):
                    continue
    return None


def _kr_calc_roe(is_df, bs_df) -> float | None:
    try:
        net_income = _kr_find_row(is_df, ["당기순이익"])
        equity = _kr_find_row(bs_df, ["자본총계", "자본 총계"])
        if net_income and equity and equity != 0:
            return round(net_income / equity * 100, 2)
    except Exception:
        pass
    return None


def _kr_calc_debt_ratio(bs_df) -> float | None:
    try:
        liabilities = _kr_find_row(bs_df, ["부채총계", "부채 총계"])
        equity = _kr_find_row(bs_df, ["자본총계", "자본 총계"])
        if liabilities and equity and equity != 0:
            return round(liabilities / equity * 100, 2)
    except Exception:
        pass
    return None


def _kr_calc_margins(is_df) -> tuple[float | None, float | None]:
    try:
        revenue_vals = []
        for kw in ["매출액", "수익(매출액)"]:
            mask = is_df.index.str.contains(kw, case=False, na=False)
            if mask.any():
                row = is_df[mask].iloc[0]
                vals = []
                for col in row.index:
                    try:
                        v = float(str(row[col]).replace(",", ""))
                        if v > 0:
                            vals.append(v)
                    except (ValueError, TypeError):
                        pass
                if len(vals) >= 2:
                    revenue_vals = vals
                    break

        op_income = _kr_find_row(is_df, ["영업이익"])

        op_margin = None
        if op_income and revenue_vals:
            latest_rev = revenue_vals[0]
            if latest_rev != 0:
                op_margin = round(op_income / latest_rev * 100, 2)

        rev_growth = None
        if len(revenue_vals) >= 2 and revenue_vals[1] != 0:
            rev_growth = round((revenue_vals[0] - revenue_vals[1]) / revenue_vals[1] * 100, 2)

        return op_margin, rev_growth
    except Exception:
        return None, None


def _kr_quarterly(corp_code: str, dart) -> list[QuarterlyPoint]:
    """최근 4분기 매출 + 영업이익."""
    from datetime import datetime, timedelta
    quarters = []
    now = datetime.now()
    # 최근 4분기: 현재 분기부터 역순
    for i in range(4):
        try:
            end_dt = now - timedelta(days=i * 90)
            start_dt = end_dt - timedelta(days=95)
            fs = dart.fs.extract(
                corp_code=corp_code,
                bgn_de=start_dt.strftime("%Y%m%d"),
                end_de=end_dt.strftime("%Y%m%d"),
                fs_tp="CFS",
            )
            if not fs:
                continue
            is_df = fs.show("IS")
            label = f"{end_dt.year}Q{(end_dt.month - 1) // 3 + 1}"
            rev = _kr_find_row(is_df, ["매출액", "수익(매출액)"])
            op = _kr_find_row(is_df, ["영업이익"])
            # 억 단위로 변환 (DART는 원 단위 또는 백만 원 단위)
            # 삼성전자 기준 억 단위
            rev_bn = round(rev / 1e8, 0) if rev else None
            op_bn = round(op / 1e8, 0) if op else None
            quarters.append(QuarterlyPoint(label=label, revenue=rev_bn, operating_profit=op_bn))
        except Exception as e:
            logger.warning("분기 데이터 조회 실패 %d분기 전: %s", i, e)
    return list(reversed(quarters))
```

- [ ] **Step 4: 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_fundamentals.py -v
```

Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add core/fundamentals.py tests/test_fundamentals.py
git commit -m "feat: add fundamentals.py with FundamentalsData and US/KR implementations"
```

---

## Task 3: core/technicals.py — TechnicalsData + 일봉 지표

**Files:**
- Create: `core/technicals.py`
- Create: `tests/test_technicals.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_technicals.py
import pytest
import pandas as pd
import numpy as np
from core.technicals import calculate_technicals, TechnicalsData, FibLevels


def make_price_df(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    """단조 증가하는 가격 시리즈 (지표 계산 검증용)."""
    prices = [start + i * 0.5 for i in range(n)]
    volumes = [1_000_000] * n
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Close": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Volume": volumes,
    }, index=dates)


def test_ma_calculated():
    df = make_price_df(120)
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.ma5 is not None
    assert tech.ma20 is not None
    assert tech.ma60 is not None
    # 단조 증가이므로 ma5 > ma20 > ma60 역전 (최근 값이 더 높음)
    assert tech.ma5 > tech.ma60


def test_rsi_range():
    df = make_price_df(60)
    tech = calculate_technicals(df, "TEST", "US")
    if tech.rsi14 is not None:
        assert 0 <= tech.rsi14 <= 100


def test_fibonacci_levels():
    df = make_price_df(260)  # 52주 이상
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.fib is not None
    assert tech.fib.level_618 < tech.fib.level_500 < tech.fib.level_382


def test_volume_ratio():
    df = make_price_df(60)
    df["Volume"] = [500_000] * 40 + [2_000_000] * 20  # 마지막 20일 4배 거래량
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.volume_ratio is not None
    assert tech.volume_ratio > 1.0


def test_short_series_returns_none_gracefully():
    df = make_price_df(10)  # MA60 계산 불가
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.ma60 is None
    assert tech.rsi14 is None
```

- [ ] **Step 2: 테스트 실패 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_technicals.py -v
```

Expected: ImportError

- [ ] **Step 3: core/technicals.py 작성**

```python
# core/technicals.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FibLevels:
    high: float
    low: float
    level_236: float
    level_382: float
    level_500: float
    level_618: float
    level_786: float
    current_zone: str   # e.g. "50%~38.2% 구간"


@dataclass
class TechnicalsData:
    code: str
    market: str
    current_price: float
    week52_high: float | None
    week52_low: float | None
    # Daily MAs
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    # Indicators
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    # Fibonacci
    fib: FibLevels | None
    # Volume
    volume_ratio: float | None      # 현재 / 20일 평균
    # Weekly (주봉 계산용 일봉 리샘플링)
    ma10w: float | None             # 10주 MA (50일 MA)
    ma20w: float | None             # 20주 MA (100일 MA)
    weekly_trend: str               # "정배열" | "역배열" | "횡보"
    pct_from_52w_high: float | None
    pct_from_52w_low: float | None
    # KR 수급 (US는 None)
    foreign_net_buy_5d: float | None    # 억원
    institution_net_buy_5d: float | None


def fetch_price_history(code: str, market: str) -> pd.DataFrame | None:
    """6개월 일봉 OHLCV 반환. 실패 시 None."""
    try:
        if market == "KR":
            from pykrx import stock as pykrx_stock
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
            df = pykrx_stock.get_market_ohlcv(start, end, code)
            if df.empty:
                return None
            df = df.rename(columns={"시가": "Open", "고가": "High", "저가": "Low",
                                    "종가": "Close", "거래량": "Volume"})
            return df[["Open", "High", "Low", "Close", "Volume"]]
        else:
            import yfinance as yf
            ticker = yf.Ticker(code)
            df = ticker.history(period="2y")  # 주봉 MA20(100일) 계산 위해 2년치
            if df.empty:
                return None
            return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        logger.warning("가격 이력 조회 실패 %s: %s", code, e)
        return None


def calculate_technicals(
    df: pd.DataFrame,
    code: str,
    market: str,
    foreign_net: float | None = None,
    institution_net: float | None = None,
) -> TechnicalsData:
    """가격 DataFrame → TechnicalsData."""
    close = df["Close"]
    volume = df["Volume"]
    high = df["High"]
    low = df["Low"]
    n = len(close)

    current_price = float(close.iloc[-1])

    # 52주 고/저
    week52_high = float(high.tail(252).max()) if n >= 30 else None
    week52_low = float(low.tail(252).min()) if n >= 30 else None

    # MAs
    ma5 = _ma(close, 5)
    ma10 = _ma(close, 10)
    ma20 = _ma(close, 20)
    ma60 = _ma(close, 60)

    # RSI
    rsi14 = _rsi(close, 14)

    # MACD (12, 26, 9)
    macd_val, macd_sig, macd_hist = _macd(close, 12, 26, 9)

    # Bollinger Bands (20, 2σ)
    bb_upper, bb_middle, bb_lower = _bollinger(close, 20, 2.0)

    # Fibonacci
    fib = _fibonacci(current_price, week52_high, week52_low) if week52_high and week52_low else None

    # Volume ratio (현재 / 20일 평균)
    volume_ratio = None
    if n >= 21:
        avg_vol = float(volume.iloc[-21:-1].mean())
        curr_vol = float(volume.iloc[-1])
        volume_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else None

    # Weekly MAs (일봉 리샘플링)
    ma10w = _ma(close, 50)   # 10주 ≈ 50거래일
    ma20w = _ma(close, 100)  # 20주 ≈ 100거래일

    weekly_trend = _weekly_trend(ma10w, ma20w, current_price)

    pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
    pct_from_52w_low = round((current_price - week52_low) / week52_low * 100, 2) if week52_low else None

    return TechnicalsData(
        code=code, market=market,
        current_price=current_price,
        week52_high=week52_high, week52_low=week52_low,
        ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60,
        rsi14=rsi14,
        macd=macd_val, macd_signal=macd_sig, macd_hist=macd_hist,
        bb_upper=bb_upper, bb_middle=bb_middle, bb_lower=bb_lower,
        fib=fib,
        volume_ratio=volume_ratio,
        ma10w=ma10w, ma20w=ma20w,
        weekly_trend=weekly_trend,
        pct_from_52w_high=pct_from_52w_high,
        pct_from_52w_low=pct_from_52w_low,
        foreign_net_buy_5d=foreign_net,
        institution_net_buy_5d=institution_net,
    )


def fetch_kr_supply_demand(code: str) -> tuple[float | None, float | None]:
    """KR 외국인·기관 최근 5거래일 순매수 합계 (억원). 실패 시 (None, None)."""
    try:
        from pykrx import stock as pykrx_stock
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        df = pykrx_stock.get_market_trading_value_by_date(start, end, code)
        if df.empty:
            return None, None
        recent = df.tail(5)
        # pykrx 컬럼: '기관합계', '외국인합계' (순매수)
        foreign = float(recent["외국인합계"].sum()) / 1e8 if "외국인합계" in recent.columns else None
        institution = float(recent["기관합계"].sum()) / 1e8 if "기관합계" in recent.columns else None
        return (round(foreign, 0) if foreign is not None else None,
                round(institution, 0) if institution is not None else None)
    except Exception as e:
        logger.warning("KR 수급 조회 실패 %s: %s", code, e)
        return None, None


# ── 지표 계산 헬퍼 ──────────────────────────────────────────

def _ma(series: pd.Series, period: int) -> float | None:
    if len(series) < period:
        return None
    return round(float(series.tail(period).mean()), 2)


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.tail(period).mean()
    avg_loss = loss.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _macd(series: pd.Series, fast: int, slow: int, signal: int
          ) -> tuple[float | None, float | None, float | None]:
    if len(series) < slow + signal:
        return None, None, None
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return (round(float(macd_line.iloc[-1]), 4),
            round(float(signal_line.iloc[-1]), 4),
            round(float(hist.iloc[-1]), 4))


def _bollinger(series: pd.Series, period: int, std_mult: float
               ) -> tuple[float | None, float | None, float | None]:
    if len(series) < period:
        return None, None, None
    rolling = series.tail(period)
    mid = float(rolling.mean())
    std = float(rolling.std())
    return round(mid + std_mult * std, 2), round(mid, 2), round(mid - std_mult * std, 2)


def _fibonacci(current: float, high: float, low: float) -> FibLevels:
    rng = high - low
    levels = {
        "236": round(high - 0.236 * rng, 2),
        "382": round(high - 0.382 * rng, 2),
        "500": round(high - 0.500 * rng, 2),
        "618": round(high - 0.618 * rng, 2),
        "786": round(high - 0.786 * rng, 2),
    }
    # 현재가 위치 구간
    sorted_vals = sorted(levels.values(), reverse=True)
    zone = "하단 이하"
    for i, lvl in enumerate(sorted_vals[:-1]):
        if current >= sorted_vals[i + 1]:
            keys = list(levels.keys())
            zone = f"{keys[i]}%~{keys[i+1]}% 구간"
            break
    return FibLevels(
        high=high, low=low,
        level_236=levels["236"], level_382=levels["382"],
        level_500=levels["500"], level_618=levels["618"],
        level_786=levels["786"],
        current_zone=zone,
    )


def _weekly_trend(ma10w: float | None, ma20w: float | None, current: float) -> str:
    if ma10w is None or ma20w is None:
        return "데이터 부족"
    if ma10w > ma20w and current > ma10w:
        return "정배열"
    if ma10w < ma20w and current < ma10w:
        return "역배열"
    return "횡보"
```

- [ ] **Step 4: 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_technicals.py -v
```

Expected: 5 passed

- [ ] **Step 5: 전체 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/ -v
```

Expected: 기존 17개 + 신규 7개 = 24개 이상 passed

- [ ] **Step 6: 커밋**

```bash
git add core/technicals.py tests/test_technicals.py
git commit -m "feat: add technicals.py with TechnicalsData, indicators, and KR supply/demand"
```

---

## Task 4: core/chart.py — 4패널 차트 생성

**Files:**
- Create: `core/chart.py`
- Create: `tests/test_chart.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_chart.py
from pathlib import Path
import pandas as pd
import pytest
from core.chart import generate_chart
from core.technicals import calculate_technicals


def make_df(n=120):
    import numpy as np
    prices = [100 + i * 0.3 + np.random.normal(0, 0.5) for i in range(n)]
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Close": prices,
        "Volume": [1_000_000] * n,
    }, index=dates)


def test_chart_creates_file(tmp_path):
    df = make_df()
    tech = calculate_technicals(df, "TEST", "US")
    chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)
    assert chart_path.exists()
    assert chart_path.suffix == ".png"
    assert chart_path.stat().st_size > 0


def test_chart_cleans_up_on_request(tmp_path):
    df = make_df()
    tech = calculate_technicals(df, "TEST", "US")
    chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)
    chart_path.unlink()
    assert not chart_path.exists()
```

- [ ] **Step 2: 테스트 실패 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_chart.py -v
```

Expected: ImportError

- [ ] **Step 3: core/chart.py 작성**

```python
# core/chart.py
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경용
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd

from core.technicals import TechnicalsData

logger = logging.getLogger(__name__)

_COLORS = {
    "ma5": "#FF6B6B",
    "ma10": "#FFA07A",
    "ma20": "#4ECDC4",
    "ma60": "#45B7D1",
    "bb": "#95A5A6",
    "volume": "#5D6D7E",
    "vol_avg": "#F39C12",
    "rsi": "#8E44AD",
    "macd": "#2980B9",
    "signal": "#E74C3C",
    "hist_pos": "#27AE60",
    "hist_neg": "#E74C3C",
}


def generate_chart(
    code: str,
    market: str,
    df: pd.DataFrame,
    tech: TechnicalsData,
    output_dir: Path | None = None,
) -> Path:
    """4패널 차트(가격+MA+BB+피보, 거래량, RSI, MACD)를 PNG로 저장하고 Path 반환."""
    if output_dir is None:
        output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 최근 6개월(약 126거래일) 만 표시
    chart_df = df.tail(126).copy()
    close = chart_df["Close"]
    volume = chart_df["Volume"]
    dates = chart_df.index

    fig = plt.figure(figsize=(12, 10), facecolor="#1C1C1C")
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.05)
    fig.suptitle(f"{code} ({market}) — {datetime.now().strftime('%Y-%m-%d')}",
                 color="white", fontsize=13, y=0.98)

    # Panel 1: 가격 + MAs + BB + 피보나치
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#1C1C1C")
    ax1.plot(dates, close, color="white", linewidth=1.2, label="종가")

    for ma_attr, color, label in [
        ("ma5", _COLORS["ma5"], "MA5"),
        ("ma10", _COLORS["ma10"], "MA10"),
        ("ma20", _COLORS["ma20"], "MA20"),
        ("ma60", _COLORS["ma60"], "MA60"),
    ]:
        val = getattr(tech, ma_attr, None)
        if val:
            # 실제 rolling으로 라인 그리기
            period = int(label[2:])
            if len(close) >= period:
                ax1.plot(dates, close.rolling(period).mean(), color=color,
                         linewidth=0.8, alpha=0.8, label=label)

    # 볼린저밴드
    if tech.bb_upper and tech.bb_lower and tech.bb_middle:
        if len(close) >= 20:
            rolling_mean = close.rolling(20).mean()
            rolling_std = close.rolling(20).std()
            ax1.fill_between(dates,
                             rolling_mean + 2 * rolling_std,
                             rolling_mean - 2 * rolling_std,
                             alpha=0.1, color=_COLORS["bb"], label="볼린저밴드")

    # 피보나치 수평선
    if tech.fib:
        fib_levels = [
            (tech.fib.level_236, "23.6%", "yellow"),
            (tech.fib.level_382, "38.2%", "orange"),
            (tech.fib.level_500, "50.0%", "red"),
            (tech.fib.level_618, "61.8%", "lime"),
            (tech.fib.level_786, "78.6%", "cyan"),
        ]
        for lvl, lbl, color in fib_levels:
            ax1.axhline(y=lvl, color=color, linewidth=0.5, linestyle="--", alpha=0.6)
            ax1.text(dates[-1], lvl, f" {lbl}", color=color, fontsize=7, va="center")

    ax1.legend(loc="upper left", fontsize=7, facecolor="#2C2C2C", labelcolor="white")
    ax1.set_ylabel("Price", color="white", fontsize=9)
    ax1.tick_params(colors="white", labelsize=7)
    for spine in ax1.spines.values():
        spine.set_color("#444444")
    plt.setp(ax1.get_xticklabels(), visible=False)

    # Panel 2: 거래량
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#1C1C1C")
    ax2.bar(dates, volume, color=_COLORS["volume"], alpha=0.7, width=0.8)
    if len(volume) >= 20:
        ax2.plot(dates, volume.rolling(20).mean(), color=_COLORS["vol_avg"],
                 linewidth=0.8, label="MA20")
    ax2.set_ylabel("Vol", color="white", fontsize=9)
    ax2.tick_params(colors="white", labelsize=7)
    for spine in ax2.spines.values():
        spine.set_color("#444444")
    plt.setp(ax2.get_xticklabels(), visible=False)

    # Panel 3: RSI
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.set_facecolor("#1C1C1C")
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        ax3.plot(dates, rsi_series, color=_COLORS["rsi"], linewidth=0.8)
        ax3.axhline(70, color="red", linewidth=0.5, linestyle="--", alpha=0.7)
        ax3.axhline(30, color="lime", linewidth=0.5, linestyle="--", alpha=0.7)
        ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI", color="white", fontsize=9)
    ax3.tick_params(colors="white", labelsize=7)
    for spine in ax3.spines.values():
        spine.set_color("#444444")
    plt.setp(ax3.get_xticklabels(), visible=False)

    # Panel 4: MACD
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.set_facecolor("#1C1C1C")
    if len(close) >= 35:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        colors = [_COLORS["hist_pos"] if v >= 0 else _COLORS["hist_neg"] for v in hist]
        ax4.bar(dates, hist, color=colors, alpha=0.7, width=0.8)
        ax4.plot(dates, macd_line, color=_COLORS["macd"], linewidth=0.8, label="MACD")
        ax4.plot(dates, signal_line, color=_COLORS["signal"], linewidth=0.8, label="Signal")
        ax4.axhline(0, color="#444444", linewidth=0.5)
        ax4.legend(loc="upper left", fontsize=7, facecolor="#2C2C2C", labelcolor="white")
    ax4.set_ylabel("MACD", color="white", fontsize=9)
    ax4.tick_params(colors="white", labelsize=7)
    for spine in ax4.spines.values():
        spine.set_color("#444444")

    # x축 날짜 포맷
    ax4.xaxis.set_major_formatter(
        plt.matplotlib.dates.DateFormatter("%m/%d") if hasattr(dates[0], 'strftime') else plt.NullFormatter()
    )

    chart_path = output_dir / f"chart_{code}_{datetime.now().strftime('%Y%m%d')}.png"
    plt.savefig(chart_path, dpi=100, bbox_inches="tight", facecolor="#1C1C1C")
    plt.close(fig)
    return chart_path
```

- [ ] **Step 4: 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_chart.py -v
```

Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add core/chart.py tests/test_chart.py
git commit -m "feat: add chart.py with 4-panel matplotlib chart generation"
```

---

## Task 5: core/notifier.py — send_photo() 추가

**Files:**
- Modify: `core/notifier.py`
- Modify: `tests/test_notifier.py`

- [ ] **Step 1: 테스트 추가**

기존 `tests/test_notifier.py` 끝에 추가:

```python
# tests/test_notifier.py 에 아래 테스트 추가
import os
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_send_photo_missing_token(tmp_path):
    fake_img = tmp_path / "chart.png"
    fake_img.write_bytes(b"PNG")
    with patch.dict(os.environ, {}, clear=True):
        from core.notifier import send_photo
        result = send_photo(fake_img)
    assert result is False


def test_send_photo_calls_telegram_api(tmp_path):
    fake_img = tmp_path / "chart.png"
    fake_img.write_bytes(b"PNG")
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}):
        with patch("core.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            from core.notifier import send_photo
            result = send_photo(fake_img)
    assert result is True
    assert mock_post.called
    call_kwargs = mock_post.call_args
    assert "sendPhoto" in call_kwargs[0][0]
```

- [ ] **Step 2: 테스트 실패 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_notifier.py::test_send_photo_missing_token -v
```

Expected: ImportError 또는 AttributeError

- [ ] **Step 3: core/notifier.py에 send_photo() 추가**

기존 파일 끝에 추가:

```python
def send_photo(image_path: Path, caption: str = "") -> bool:
    """차트 이미지를 텔레그램으로 전송. 전송 후 파일은 호출자가 삭제."""
    from pathlib import Path as _Path
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
```

또한 파일 상단 import에 `from pathlib import Path` 추가.

- [ ] **Step 4: 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/test_notifier.py -v
```

Expected: 5 passed (기존 3 + 신규 2)

- [ ] **Step 5: 커밋**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: add send_photo() to notifier.py for chart image delivery"
```

---

## Task 6: core/reporter.py — generate_analysis_report() 추가

**Files:**
- Modify: `core/reporter.py`

- [ ] **Step 1: core/reporter.py에 함수 추가**

기존 파일 끝 (imports 유지, `_SYSTEM_PROMPT` 아래)에 추가:

```python
# core/reporter.py 에 추가할 import
from core.fundamentals import FundamentalsData
from core.technicals import TechnicalsData
```

기존 import 블록에 위 두 줄 추가. 그리고 파일 끝에 아래 함수들 추가:

```python
def _fmt_fundamentals(fd: FundamentalsData) -> str:
    def _v(val, fmt=".1f", suffix=""):
        return f"{val:{fmt}}{suffix}" if val is not None else "N/A"

    lines = [
        f"PER {_v(fd.per)} | PBR {_v(fd.pbr)} | ROE {_v(fd.roe)}%",
        f"부채비율 {_v(fd.debt_ratio)}% | 영업이익률 {_v(fd.operating_margin)}% | 매출성장 {_v(fd.revenue_growth_yoy, '+.1f')}% YoY",
    ]
    if fd.quarterly:
        rev_line = " → ".join(
            f"{q.label} {q.revenue:,.0f}" if q.revenue else f"{q.label} N/A"
            for q in fd.quarterly
        )
        op_line = " → ".join(
            f"{q.label} {q.operating_profit:,.0f}" if q.operating_profit else f"{q.label} N/A"
            for q in fd.quarterly
        )
        lines.append(f"분기매출(억): {rev_line}")
        lines.append(f"분기영업이익: {op_line}")
    return "\n".join(lines)


def _fmt_technicals(tech: TechnicalsData) -> str:
    def _v(val, fmt=".2f"):
        return f"{val:{fmt}}" if val is not None else "N/A"
    def _arr(cur, ref):
        if cur is None or ref is None:
            return ""
        return "↑" if cur > ref else "↓"

    lines = [
        f"현재가 {tech.current_price:,.2f}",
        f"MA5 {_v(tech.ma5)}{_arr(tech.current_price, tech.ma5)}  "
        f"MA10 {_v(tech.ma10)}{_arr(tech.current_price, tech.ma10)}  "
        f"MA20 {_v(tech.ma20)}{_arr(tech.current_price, tech.ma20)}  "
        f"MA60 {_v(tech.ma60)}{_arr(tech.current_price, tech.ma60)}",
        f"RSI {_v(tech.rsi14)} | MACD {_v(tech.macd)} / Signal {_v(tech.macd_signal)}",
        f"볼린저밴드 상단 {_v(tech.bb_upper)} / 하단 {_v(tech.bb_lower)}",
        f"거래량 {_v(tech.volume_ratio, '.1f')}배 (20일 평균 대비)",
    ]
    if tech.fib:
        lines.append(
            f"피보나치 ({tech.fib.high:,.2f}~{tech.fib.low:,.2f}) | "
            f"38.2% {tech.fib.level_382:,.2f} | 50% {tech.fib.level_500:,.2f} | "
            f"61.8% {tech.fib.level_618:,.2f} | 현재: {tech.fib.current_zone}"
        )
    lines.append(
        f"주봉 MA10 {_v(tech.ma10w)} MA20 {_v(tech.ma20w)} — {tech.weekly_trend}"
    )
    if tech.pct_from_52w_high is not None:
        lines.append(
            f"52주 고점 대비 {tech.pct_from_52w_high:+.1f}% | "
            f"52주 저점 대비 {tech.pct_from_52w_low:+.1f}%"
        )
    return "\n".join(lines)


def _fmt_supply(tech: TechnicalsData) -> str | None:
    if tech.foreign_net_buy_5d is None and tech.institution_net_buy_5d is None:
        return None
    f = f"외국인 {tech.foreign_net_buy_5d:+,.0f}억" if tech.foreign_net_buy_5d is not None else ""
    i = f"기관 {tech.institution_net_buy_5d:+,.0f}억" if tech.institution_net_buy_5d is not None else ""
    return "  ".join(x for x in [f, i] if x)


def generate_analysis_report(
    fd: FundamentalsData,
    tech: TechnicalsData,
    news: list[str],
) -> str:
    """Claude 심층 분석 리포트 생성."""
    supply_str = _fmt_supply(tech)
    news_str = "\n".join(f"· {h}" for h in news) if news else "뉴스 없음"

    user_msg = f"""아래 종목 데이터를 바탕으로 심층 분석 리포트를 작성해 주세요.

종목: {fd.name} ({fd.code}) | 시장: {fd.market}

[재무 지표]
{_fmt_fundamentals(fd)}

[기술 지표]
{_fmt_technicals(tech)}

{"[수급 (최근 5거래일)]\\n" + supply_str if supply_str else ""}

[뉴스]
{news_str}

출력 형식 (텔레그램 Markdown):
🔍 *{fd.name} ({fd.code}) 심층 분석* | {datetime.now().strftime('%Y-%m-%d')}

━━━ 📊 재무 ━━━
(PER/PBR/ROE/부채비율/영업이익률/매출성장 + 분기 추이)

━━━ 📈 기술 지표 (일봉) ━━━
(MA / RSI / MACD / 볼린저밴드 / 거래량)

━━━ 🌀 피보나치 ━━━
(지지·저항 레벨 + 현재가 위치)

━━━ 📉 장기 추세 (주봉) ━━━
(MA10주/MA20주 + 정배열 여부 + 52주 위치)

{"━━━ 🏦 수급 ━━━\\n(외국인·기관 순매수)" if supply_str else ""}

━━━ 📰 뉴스 ━━━
(헤드라인 나열)

━━━ 🤖 Claude 의견 ━━━
*단기 (단타):* (기술 지표·수급·거래량 기반 진입 타이밍)
*중장기 (가치+차트):* (재무 건전성·섹터 평균 PER 감안 밸류에이션·주봉 추세 종합)

지시사항:
- 섹터 평균 PER를 감안하여 현재 밸류에이션 수준 평가
- 매수/매도 결정은 사용자 최종 판단 (제안만)
"""
    return _call_claude(user_msg)
```

파일 상단에 `from datetime import datetime` 이미 있는지 확인하고 없으면 추가.

- [ ] **Step 2: import 확인**

```
PYTHONPATH=. .venv\Scripts\python -c "from core.reporter import generate_analysis_report; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add core/reporter.py
git commit -m "feat: add generate_analysis_report() to reporter.py"
```

---

## Task 7: jobs/analyze.py — CLI 오케스트레이터

**Files:**
- Create: `jobs/analyze.py`

- [ ] **Step 1: jobs/analyze.py 작성**

```python
"""온디맨드 종목 심층 분석. 사용법: python -m jobs.analyze TICKER [STOCK_NAME]"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
            foreign_net, institution_net = (None, None)
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
        # Claude 실패 시 수치만 전송
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
```

- [ ] **Step 2: import 확인**

```
PYTHONPATH=. .venv\Scripts\python -c "import jobs.analyze; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 전체 테스트 통과 확인**

```
PYTHONPATH=. .venv\Scripts\pytest tests/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 4: 커밋**

```bash
git add jobs/analyze.py
git commit -m "feat: add analyze.py CLI pipeline for on-demand stock deep analysis"
```

---

## 전체 테스트 명령

```bash
PYTHONPATH=. .venv\Scripts\pytest tests/ -v --tb=short
```

예상 결과:
```
tests/test_fundamentals.py::test_us_fundamentals              PASSED
tests/test_fundamentals.py::test_missing_us_data_returns_none PASSED
tests/test_technicals.py::test_ma_calculated                  PASSED
tests/test_technicals.py::test_rsi_range                      PASSED
tests/test_technicals.py::test_fibonacci_levels               PASSED
tests/test_technicals.py::test_volume_ratio                   PASSED
tests/test_technicals.py::test_short_series_returns_none_gracefully PASSED
tests/test_chart.py::test_chart_creates_file                  PASSED
tests/test_chart.py::test_chart_cleans_up_on_request          PASSED
tests/test_notifier.py::test_short_message_not_split          PASSED
tests/test_notifier.py::test_long_message_splits_on_newline   PASSED
tests/test_notifier.py::test_each_part_fits_limit             PASSED
tests/test_notifier.py::test_send_photo_missing_token         PASSED
tests/test_notifier.py::test_send_photo_calls_telegram_api    PASSED
... (기존 holdings/pricer/alerter/rebalancer/storage 테스트)
```

## 통합 테스트 (실제 실행)

`.env` 설정 완료 후:

```powershell
# KR 테스트
.venv\Scripts\python -m jobs.analyze 005930 삼성전자

# US 테스트
.venv\Scripts\python -m jobs.analyze AAPL Apple
```

Expected: 텔레그램에 차트 이미지 + 분석 리포트 수신
