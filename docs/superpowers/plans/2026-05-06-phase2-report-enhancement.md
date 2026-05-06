# Phase 2 리포트 고도화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 2 심층 분석 리포트를 ① 캔들차트, ② ATR 기반 손절/목표가, ③ 애널리스트 컨센서스(US), ④ Bull/Base/Bear 시나리오 분리로 고도화한다.

**Architecture:** 기존 `core/chart.py`, `core/technicals.py`, `core/fundamentals.py`, `core/reporter.py` 4개 파일만 수정. 신규 외부 의존성 없음(yfinance는 이미 포함). 각 태스크는 독립적으로 동작 가능하며 앞 태스크 변경에 의존하지 않는다(단, Task 2의 atr14 필드는 Task 3·4에서 프롬프트에 활용되므로 Task 2가 먼저여야 한다).

**Tech Stack:** Python 3.9+, matplotlib, pandas, yfinance, anthropic SDK

---

## 파일 변경 맵

| 파일 | 변경 내용 |
|------|---------|
| `core/chart.py` | Panel 1 라인차트 → OHLC 캔들스틱 |
| `core/technicals.py` | `TechnicalsData.atr14` 필드 추가, `_atr()` 함수 추가 |
| `core/fundamentals.py` | `FundamentalsData` 애널리스트 필드 5개 추가, `_fetch_us()` 업데이트 |
| `core/reporter.py` | ATR 표시 추가, 애널리스트 섹션 추가, 출력 형식 Bull/Base/Bear로 교체 |
| `tests/test_chart.py` | 캔들스틱 smoke test |
| `tests/test_technicals.py` | ATR 계산 단위 테스트 |
| `tests/test_fundamentals.py` | 애널리스트 컨센서스 mock 테스트 |

---

## Task 1: 캔들스틱 차트 전환

**Files:**
- Modify: `core/chart.py`
- Test: `tests/test_chart.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_chart.py` 하단에 추가:

```python
def test_chart_uses_ohlc(tmp_path):
    """캔들스틱이 OHLC 데이터를 사용하는지 확인 — Open != Close여야 의미 있음."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 130
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    opens = closes * rng.uniform(0.99, 1.01, n)
    df = pd.DataFrame({
        "Open": opens,
        "High": np.maximum(opens, closes) * 1.005,
        "Low": np.minimum(opens, closes) * 0.995,
        "Close": closes,
        "Volume": [1_000_000] * n,
    }, index=pd.date_range("2025-01-01", periods=n, freq="B"))
    tech = calculate_technicals(df, "TEST", "US")
    chart_path = generate_chart("TEST", "US", df, tech, output_dir=tmp_path)
    assert chart_path.exists()
    assert chart_path.stat().st_size > 5000  # 실질적인 PNG 크기
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_chart.py::test_chart_uses_ohlc -v
```

테스트가 통과하거나 실패 모두 가능 — 중요한 것은 이후 캔들스틱 전환 후에도 통과해야 한다는 것.

- [ ] **Step 3: `core/chart.py` Panel 1을 캔들스틱으로 교체**

`generate_chart()` 함수 상단에 import 추가:

```python
from datetime import timedelta
```

Panel 1 블록에서 기존 라인차트 라인을 제거하고 캔들스틱으로 교체. 기존:

```python
ax1.plot(dates, close, color="white", linewidth=1.2, label="종가")
```

교체 후 (이 한 줄을 아래 블록으로 대체):

```python
_bar_width = timedelta(hours=14)
for idx, row in chart_df.iterrows():
    is_up = row["Close"] >= row["Open"]
    color = "#26A69A" if is_up else "#EF5350"
    body_bottom = min(row["Open"], row["Close"])
    body_height = max(abs(row["Close"] - row["Open"]), row["Close"] * 0.0002)
    ax1.bar(idx, body_height, bottom=body_bottom, color=color,
            width=_bar_width, alpha=0.9, linewidth=0)
    ax1.vlines(idx, row["Low"], row["High"], color=color, linewidth=0.5)
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_chart.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```
git add core/chart.py tests/test_chart.py
git commit -m "feat: replace line chart with OHLC candlestick in chart panel 1"
```

---

## Task 2: ATR 지표 추가

**Files:**
- Modify: `core/technicals.py`
- Modify: `core/reporter.py`
- Test: `tests/test_technicals.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_technicals.py` 하단에 추가:

```python
def test_atr_calculated():
    df = make_price_df(60)
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.atr14 is not None
    assert tech.atr14 > 0

def test_atr_none_on_short_series():
    df = make_price_df(10)  # period+1=15 미만
    tech = calculate_technicals(df, "TEST", "US")
    assert tech.atr14 is None
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_technicals.py::test_atr_calculated tests/test_technicals.py::test_atr_none_on_short_series -v
```

Expected: AttributeError — `atr14` 필드 없음

- [ ] **Step 3: `core/technicals.py` 수정**

`TechnicalsData` dataclass에 필드 추가 (volume_ratio 다음 줄):

```python
    # ATR
    atr14: float | None
```

`calculate_technicals()` 함수에서 `volume_ratio` 계산 직후에 추가:

```python
    atr14 = _atr(high, low, close, 14)
```

`return TechnicalsData(...)` 블록에 `atr14=atr14,` 추가.

파일 하단 `_weekly_trend` 정의 앞에 헬퍼 함수 추가:

```python
def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.tail(period).mean()), 2)
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_technicals.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: `core/reporter.py` `_fmt_technicals()` 에 ATR 줄 추가**

기존 `lines` 리스트의 볼린저밴드 줄 다음에 ATR 줄 삽입:

```python
        f"볼린저밴드 상단 {_v(tech.bb_upper)} / 하단 {_v(tech.bb_lower)}",
        f"ATR(14) {_v(tech.atr14)} | 거래량 {_v(tech.volume_ratio, '.1f')}배 (20일 평균 대비)",
```

기존 `f"거래량 {_v(tech.volume_ratio, '.1f')}배 (20일 평균 대비)",` 줄을 위 두 줄로 대체 (ATR 병합).

- [ ] **Step 6: Claude 프롬프트에 ATR 손절 지시 추가**

`generate_analysis_report()`의 `user_msg` 내 지시사항 섹션:

```python
지시사항:
- 섹터 평균 PER를 감안하여 현재 밸류에이션 수준 평가
- ATR(14) 기반으로 손절가와 1차 목표가를 숫자로 제안 (예: 손절 현재가 - ATR×1.5)
- 매수/매도 결정은 사용자 최종 판단 (제안만)
```

- [ ] **Step 7: 커밋**

```
git add core/technicals.py core/reporter.py tests/test_technicals.py
git commit -m "feat: add ATR14 to technicals and stop-loss hint in analysis report"
```

---

## Task 3: 애널리스트 컨센서스 (US 전용)

**Files:**
- Modify: `core/fundamentals.py`
- Modify: `core/reporter.py`
- Test: `tests/test_fundamentals.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_fundamentals.py` 하단에 추가:

```python
@patch("core.fundamentals.yf.Ticker")
def test_us_analyst_consensus(mock_ticker):
    import pandas as pd
    t = MagicMock()
    t.info = {}
    t.quarterly_financials = MagicMock(empty=True)
    t.analyst_price_targets = {
        "current": 220.0,
        "mean": 245.0,
        "high": 300.0,
        "low": 180.0,
        "numberOfAnalysts": 42,
    }
    rec_df = pd.DataFrame([{
        "strongBuy": 20, "buy": 12, "hold": 8, "sell": 2, "strongSell": 0
    }])
    t.recommendations_summary = rec_df
    mock_ticker.return_value = t

    fd = fetch_fundamentals("AAPL", "Apple", "US")
    assert fd.analyst_count == 42
    assert fd.analyst_target_mean == pytest.approx(245.0)
    assert fd.analyst_target_high == pytest.approx(300.0)
    assert fd.analyst_target_low == pytest.approx(180.0)
    assert fd.analyst_recommendation == "매수"


@patch("core.fundamentals.yf.Ticker")
def test_us_analyst_consensus_missing(mock_ticker):
    """analyst_price_targets 없는 경우 None 처리."""
    t = MagicMock()
    t.info = {}
    t.quarterly_financials = MagicMock(empty=True)
    t.analyst_price_targets = {}
    t.recommendations_summary = MagicMock(empty=True)
    mock_ticker.return_value = t

    fd = fetch_fundamentals("UNKNOWN", "Unknown", "US")
    assert fd.analyst_count is None
    assert fd.analyst_target_mean is None
    assert fd.analyst_recommendation is None
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_fundamentals.py::test_us_analyst_consensus tests/test_fundamentals.py::test_us_analyst_consensus_missing -v
```

Expected: AttributeError — `analyst_count` 필드 없음

- [ ] **Step 3: `core/fundamentals.py` `FundamentalsData` 에 필드 추가**

`FundamentalsData` dataclass에 다음 5개 필드 추가 (quarterly 필드 다음):

```python
    # 애널리스트 컨센서스 (US only, KR는 None)
    analyst_count: int | None = None
    analyst_target_mean: float | None = None
    analyst_target_high: float | None = None
    analyst_target_low: float | None = None
    analyst_recommendation: str | None = None  # "매수" | "중립" | "매도"
```

- [ ] **Step 4: `_fetch_us()` 에 애널리스트 데이터 수집 로직 추가**

`_fetch_us()` 함수에서 `quarterly` 수집 블록 다음에 추가:

```python
    analyst_count = None
    analyst_target_mean = None
    analyst_target_high = None
    analyst_target_low = None
    analyst_recommendation = None
    try:
        targets = ticker.analyst_price_targets or {}
        analyst_count = targets.get("numberOfAnalysts")
        analyst_target_mean = targets.get("mean")
        analyst_target_high = targets.get("high")
        analyst_target_low = targets.get("low")
    except Exception as e:
        logger.warning("애널리스트 목표가 조회 실패 %s: %s", code, e)

    try:
        rec = ticker.recommendations_summary
        if rec is not None and not rec.empty:
            row = rec.iloc[0]
            buys = row.get("strongBuy", 0) + row.get("buy", 0)
            holds = row.get("hold", 0)
            sells = row.get("sell", 0) + row.get("strongSell", 0)
            total = buys + holds + sells
            if total > 0:
                if buys / total >= 0.6:
                    analyst_recommendation = "매수"
                elif sells / total >= 0.4:
                    analyst_recommendation = "매도"
                else:
                    analyst_recommendation = "중립"
    except Exception as e:
        logger.warning("애널리스트 추천 조회 실패 %s: %s", code, e)
```

그리고 `return FundamentalsData(...)` 블록에 추가:

```python
        analyst_count=analyst_count,
        analyst_target_mean=analyst_target_mean,
        analyst_target_high=analyst_target_high,
        analyst_target_low=analyst_target_low,
        analyst_recommendation=analyst_recommendation,
```

- [ ] **Step 5: 테스트 통과 확인**

```
pytest tests/test_fundamentals.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: `core/reporter.py` 에 `_fmt_analyst()` 헬퍼 추가 및 Claude 프롬프트 반영**

`_fmt_supply()` 함수 다음에 추가:

```python
def _fmt_analyst(fd: FundamentalsData) -> str | None:
    if fd.analyst_target_mean is None and fd.analyst_count is None:
        return None
    parts = []
    if fd.analyst_count is not None:
        parts.append(f"커버리지 {fd.analyst_count}명")
    if fd.analyst_recommendation is not None:
        parts.append(f"컨센서스 {fd.analyst_recommendation}")
    if fd.analyst_target_mean is not None:
        parts.append(f"목표주가 평균 {fd.analyst_target_mean:,.2f}")
    if fd.analyst_target_high is not None and fd.analyst_target_low is not None:
        parts.append(f"(범위 {fd.analyst_target_low:,.2f}~{fd.analyst_target_high:,.2f})")
    return "  ".join(parts)
```

`generate_analysis_report()` 함수 내 `user_msg` 구성 부분에서 supply_section 다음에 analyst 섹션 추가:

```python
    analyst_str = _fmt_analyst(fd)
    analyst_section = f"\n[애널리스트 컨센서스]\n{analyst_str}" if analyst_str else ""
    analyst_output = "\n━━━ 🎯 애널리스트 ━━━\n(목표주가 범위 + 컨센서스)" if analyst_str else ""
```

`user_msg` 문자열에 `{analyst_section}` 삽입 (supply_section 다음):

```python
    user_msg = f"""...
{supply_section}{analyst_section}
...
```

Claude 출력 포맷에도 `{analyst_output}` 삽입 (supply_output 다음 줄):

```
━━━ 📉 추세 분석 (주봉 / 월봉) ━━━
...{supply_output}{analyst_output}
```

- [ ] **Step 7: 커밋**

```
git add core/fundamentals.py core/reporter.py tests/test_fundamentals.py
git commit -m "feat: add analyst consensus (US) to fundamentals and analysis report"
```

---

## Task 4: Bull / Base / Bear 시나리오 분리

**Files:**
- Modify: `core/reporter.py`
- Test: `tests/test_reporter.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_reporter.py` 신규 생성:

```python
# tests/test_reporter.py
from unittest.mock import patch, MagicMock
from core.reporter import generate_analysis_report
from core.fundamentals import FundamentalsData, QuarterlyPoint
from core.technicals import TechnicalsData


def _make_fd():
    return FundamentalsData(
        code="AAPL", name="Apple", market="US",
        per=28.0, pbr=45.0, roe=147.0,
        debt_ratio=198.0, operating_margin=31.7,
        revenue_growth_yoy=6.1,
        quarterly=[QuarterlyPoint("2024Q4", 94930.0, 29000.0)],
    )


def _make_tech():
    return TechnicalsData(
        code="AAPL", market="US", current_price=190.0,
        week52_high=220.0, week52_low=165.0,
        ma5=191.0, ma10=189.0, ma20=185.0, ma60=178.0,
        rsi14=52.0, macd=1.2, macd_signal=0.8, macd_hist=0.4,
        bb_upper=200.0, bb_middle=185.0, bb_lower=170.0,
        atr14=3.5,
        volume_ratio=1.2,
        ma5w=188.0, ma10w=182.0, ma20w=175.0, weekly_trend="정배열",
        pct_from_52w_high=-13.6, pct_from_52w_low=15.2,
        ma3m=183.0, ma6m=178.0, ma12m=170.0, monthly_trend="정배열",
        foreign_net_buy_5d=None, institution_net_buy_5d=None,
    )


@patch("core.reporter._call_claude")
def test_generate_analysis_report_prompt_has_scenarios(mock_claude):
    mock_claude.return_value = "테스트 리포트"
    generate_analysis_report(_make_fd(), _make_tech(), ["뉴스1"])

    call_args = mock_claude.call_args[0][0]
    assert "Bull" in call_args
    assert "Base" in call_args
    assert "Bear" in call_args


@patch("core.reporter._call_claude")
def test_generate_analysis_report_prompt_has_atr_instruction(mock_claude):
    mock_claude.return_value = "테스트 리포트"
    generate_analysis_report(_make_fd(), _make_tech(), [])

    call_args = mock_claude.call_args[0][0]
    assert "ATR" in call_args
```

- [ ] **Step 2: 테스트 실패 확인**

```
pytest tests/test_reporter.py -v
```

Expected: FAIL — "Bull" not in prompt

- [ ] **Step 3: `core/reporter.py` `generate_analysis_report()` 출력 포맷 교체**

기존 Claude 의견 출력 형식 섹션:

```python
━━━ 🤖 Claude 의견 ━━━
*단기 (단타):* (기술 지표·수급·거래량 기반 진입 타이밍)
*중장기 (가치+차트):* (재무 건전성·섹터 평균 PER 감안 밸류에이션·주봉/월봉 추세 종합)

지시사항:
- 섹터 평균 PER를 감안하여 현재 밸류에이션 수준 평가
- ATR(14) 기반으로 손절가와 1차 목표가를 숫자로 제안 (예: 손절 현재가 - ATR×1.5)
- 매수/매도 결정은 사용자 최종 판단 (제안만)
```

아래로 교체:

```python
━━━ 🤖 시나리오 분석 ━━━
*🟢 Bull (상승):* 조건 + 목표가
*🟡 Base (기본):* 조건 + 가격 범위
*🔴 Bear (하락):* 리스크 조건 + 손절가

지시사항:
- 각 시나리오별로 "이 조건이 충족될 때 → 예상 가격 반응"을 구체적으로 작성
- ATR(14) 기반 손절가 = 현재가 - ATR×1.5, 1차 목표가 = 현재가 + ATR×2.0 계산하여 Bear/Bull에 반영
- 섹터 평균 PER 감안 밸류에이션 평가 포함
- 매수/매도 결정은 사용자 최종 판단 (제안만)
- 텔레그램 Markdown 형식 (*굵게*)
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/test_reporter.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 전체 테스트 통과 확인**

```
pytest tests/ -v --ignore=tests/test_pricer.py --ignore=tests/test_storage_snapshot.py
```

(pricer/storage는 외부 API 의존 — 로컬 실행 스킵 가능)

- [ ] **Step 6: 커밋**

```
git add core/reporter.py tests/test_reporter.py
git commit -m "feat: replace short/long term with Bull/Base/Bear scenario format in analysis report"
```

---

## Self-Review

**Spec coverage 체크:**
- [x] 캔들차트 전환 → Task 1
- [x] ATR 추가 + 손절/목표가 제안 → Task 2
- [x] 애널리스트 컨센서스 (US) → Task 3
- [x] 시나리오 분리 (Bull/Base/Bear) → Task 4

**Placeholder scan:**
- 모든 코드 블록에 실제 구현 포함됨
- "TBD" 없음

**Type consistency:**
- `TechnicalsData.atr14: float | None` → Task 2 step 3에서 정의, `_make_tech()` 에서 `atr14=3.5`로 사용 ✓
- `FundamentalsData.analyst_count` 등 5개 필드 → Task 3 step 3에서 정의, `_make_fd()`에서는 기본값 None 사용 ✓
- `_fmt_analyst(fd)` → Task 3 step 6에서 정의 ✓
