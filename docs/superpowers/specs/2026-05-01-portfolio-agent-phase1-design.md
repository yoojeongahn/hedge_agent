# Phase 1 설계 스펙 — 포트폴리오 모니터링·리밸런싱 에이전트

**작성일:** 2026-05-01  
**범위:** Phase 1 — 일일 모니터링 파이프라인 (알람 + 리밸런싱 가이드 + LLM 리포트)  
**제외 범위:** Phase 2 (종목 심층 분석), Phase 3 (투자 대가 에이전트)

---

## 1. 배경 및 목표

1단계 MVP(SQLite 스냅샷 + 텔레그램 전송)가 완성된 상태에서, 다음을 추가한다:

- 다증권사 사용 환경에 맞게 **보유 내역을 YAML로 수동 관리**
- 국내(KR) + 미국(US) 혼합 포트폴리오 지원
- 비중 이탈·손익 **알람** 자동 발송
- 목표 비중 복귀에 필요한 수치를 계산하고, **Claude가 리밸런싱 가이드를 제안**
- 보유 종목 전일 뉴스 헤드라인 포함한 **일일 LLM 리포트**
- 실제 주문은 사용자가 직접 수행 (자동 매매 없음)

---

## 2. 아키텍처

### 2.1 파일 구조

```
hedge_agent/
├── config/
│   ├── portfolio.yaml      # 목표 비중·알람 규칙 (기존)
│   └── holdings.yaml       # 실제 보유 내역 (신규, 수동 관리)
├── core/
│   ├── holdings.py         # holdings.yaml 파싱·검증
│   ├── pricer.py           # pykrx(KR) + yfinance(US) + 환율
│   ├── alerter.py          # 비중 이탈·손익 알람 (3종)
│   ├── rebalancer.py       # 비중 차이 수치 계산기
│   ├── news_fetcher.py     # DuckDuckGo 뉴스 헤드라인 (무료)
│   ├── reporter.py         # Claude API 리포트 생성
│   ├── storage.py          # SQLite 스냅샷 저장 (기존)
│   └── notifier.py         # 텔레그램 전송 (기존)
├── jobs/
│   ├── us_morning.py       # 08:00 cron — US 풀 리포트
│   └── kr_daily.py         # 16:30 cron — KR 간략 리포트
└── data/
    └── snapshots.db        # SQLite DB (기존)
```

### 2.2 두 파이프라인

#### 🌅 08:00 KST — `jobs/us_morning.py` (풀버전)

미국 전일 종가 기준. 하루 투자 전략 수립용.

```
holdings.yaml (US 필터)
  → pricer.py: yfinance 전일 종가 + 7일·30일 수익률 + 52주 고저점
  → storage.py: SQLite 저장
  → alerter.py: 알람 조건 체크
  → rebalancer.py: 비중 차이 수치 계산
  → news_fetcher.py: 종목별 뉴스 헤드라인 3건
  → reporter.py: Claude 풀 리포트 생성
  → notifier.py: 텔레그램 전송
```

#### 📊 16:30 KST — `jobs/kr_daily.py` (간략버전)

국내 당일 종가 기준. 장 마감 확인용.

```
holdings.yaml (KR 필터)
  → pricer.py: pykrx 당일 종가
  → storage.py: KR 스냅샷 저장
  → alerter.py: KR 포지션 기준 알람 체크
      - 비중 이탈, 개별 손익: KR 종목만
      - 일일 손익: KR 포트폴리오 기준 (US는 08:00 리포트에서 확인)
  → [알람 없음] → 숫자 요약만 텔레그램 전송
  → [알람 있음] → news_fetcher.py + reporter.py Claude 짧은 코멘트 추가
  → notifier.py: 텔레그램 전송
```

#### 스케줄 등록

**Windows (Task Scheduler):**
```
작업 이름: hedge_us_morning
트리거: 매일 08:00, 평일(월~금)
동작: .venv\Scripts\python.exe -m jobs.us_morning
시작 위치: C:\절대경로\hedge_agent

작업 이름: hedge_kr_daily
트리거: 매일 16:30, 평일(월~금)
동작: .venv\Scripts\python.exe -m jobs.kr_daily
시작 위치: C:\절대경로\hedge_agent
```

**Linux/macOS (cron):**
```cron
0 8 * * 1-5   cd /절대경로/hedge_agent && .venv/bin/python -m jobs.us_morning >> data/cron.log 2>&1
30 16 * * 1-5  cd /절대경로/hedge_agent && .venv/bin/python -m jobs.kr_daily  >> data/cron.log 2>&1
```

---

## 3. 데이터 모델

### 3.1 holdings.yaml

```yaml
# 매매 후 직접 수정. market: KR | US
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
```

### 3.2 portfolio.yaml (기존 + 확장)

```yaml
target_weights:
  "005930":
    name: "삼성전자"
    target_pct: 25.0
    rebalance_band: 5.0

  "AAPL":
    name: "Apple"
    market: US
    target_pct: 15.0
    rebalance_band: 5.0

cash:
  target_pct: 40.0

alerts:
  daily_loss_pct: -3.0
  position_loss_pct: -10.0
```

---

## 4. 모듈 상세

### 4.1 `core/holdings.py`

- `holdings.yaml` 읽기·파싱
- 필수 필드(code, market, quantity, avg_price) 검증
- `market` 기준 KR/US 필터링 메서드 제공
- 반환 타입: `list[HoldingPosition]` dataclass
- **목표 비중 미설정 종목 처리**: `portfolio.yaml`의 `target_weights`에 없는 종목은 알람·리밸런싱 대상에서 제외하고 현황 표시만 함 (보유는 하되 목표 없는 종목)

### 4.2 `core/pricer.py`

| 대상 | 라이브러리 | 데이터 |
|------|-----------|--------|
| KR 종목 종가 | pykrx | 당일 종가 (16:00 이후) |
| US 종목 종가 | yfinance | 전일 종가 |
| 시황 수치 | yfinance / pykrx | 7일·30일 수익률, 52주 고저점 |
| USD/KRW 환율 | yfinance (`KRW=X`) | 전일 기준 |

- 가격 조회 실패 시 `None` 반환, 호출부에서 스킵 처리
- 총평가금액은 KRW 단위로 통일 (USD × 환율)

### 4.3 `core/alerter.py`

알람 3종:

| # | 조건 | 파라미터 출처 |
|---|------|-------------|
| 1 | 현재 비중이 `목표 ± band` 이탈 | `portfolio.yaml` → `rebalance_band` |
| 2 | 개별 종목 평가손익률 < 임계값 | `portfolio.yaml` → `position_loss_pct` |
| 3 | 전일 대비 포트폴리오 손익률 < 임계값 | `portfolio.yaml` → `daily_loss_pct` |

- 반환: `list[Alert]` (알람명, 종목, 현재값, 임계값)
- 알람 없으면 빈 리스트 반환

### 4.4 `core/rebalancer.py`

수치 계산만 담당. 판단·제안은 `reporter.py`(Claude)가 수행.

```
총평가(KRW) = Σ(종목 평가금액) + 현금KRW + 현금USD × 환율
목표금액    = 총평가 × target_pct / 100
차이금액    = 목표금액 − 현재 평가금액
복귀수량    = abs(차이금액) / 현재가
```

- 반환: `list[RebalanceDelta]` (종목, 현재 비중, 목표 비중, 차이%p, 차이금액, 복귀수량)
- band 이탈 종목만 포함 (이탈 없으면 빈 리스트)

### 4.5 `core/news_fetcher.py`

```python
# duckduckgo-search 라이브러리 사용 (API 키 불필요)
# KR: "{종목명} 주식 뉴스"
# US: "{ticker} stock news"
# 종목당 헤드라인 3건
# 실패 시 빈 리스트 반환 (메인 파이프라인 중단 없음)
```

### 4.6 `core/storage.py` (기존 수정)

현재 `AccountSnapshot` (broker.py 전용)을 받도록 설계되어 있어 수정 필요:

- `AccountSnapshot` dataclass → `PortfolioSnapshot` dataclass로 교체
- `PortfolioSnapshot`: holdings.yaml + pricer 결과를 담는 새 구조
- 기존 SQLite 스키마(`account_snapshots`, `position_snapshots`)는 그대로 재사용
- `broker.py` import 제거

### 4.7 `core/reporter.py`

**Claude에 전달하는 컨텍스트:**

1. 포트폴리오 현황 (총평가, 종목별 현재가·손익률·비중)
2. 비중 차이 수치 (`rebalancer` 결과)
3. 발동된 알람 목록 (`alerter` 결과)
4. 시황 수치 (7일·30일 수익률, 52주 고저점)
5. 보유 종목 뉴스 헤드라인 (`news_fetcher` 결과)

**Claude 출력 구조 (풀버전):**

```
📊 일일 포트폴리오 리포트 (날짜 시간)

[ 오늘의 요약 ]
총평가 및 전일 대비 수익률 요약

[ 알람 ]
발동된 알람 목록 (없으면 생략)

[ 리밸런싱 가이드 ]
종목별 비중 차이 + Claude 실행 여부 의견
목표 비중 재검토 필요 시 제안 포함

[ 시황 코멘트 ]
보유 종목 관련 뉴스·가격 흐름 요약
```

**모델:** `claude-sonnet-4-6`  
**최적화:** 시스템 프롬프트에 prompt caching 적용 (`cache_control`)

---

## 5. 에러 처리 원칙

- 가격 조회 실패 → 해당 종목 스킵, 나머지 계속 진행
- 뉴스 조회 실패 → 뉴스 없이 리포트 생성
- Claude API 실패 → 수치 데이터만 텔레그램 전송
- 전체 파이프라인 실패 → 에러 메시지 텔레그램 전송 (기존 동작 유지)
- **텔레그램 4096자 제한** → 리포트가 초과할 경우 분할 전송 (섹션 단위로 나눠 순서대로 발송)

---

## 6. 의존성 변경

**추가:**
```
yfinance>=0.2.0
duckduckgo-search>=6.0.0
```

**제거:**
- `python-kis` — KIS API 미사용으로 삭제
- `core/broker.py` — 삭제
- `jobs/snapshot_daily.py` — `us_morning.py`, `kr_daily.py`로 대체 후 삭제

---

## 7. 미결 사항 (Phase 2 이후)

- Phase 2: 신규 종목 심층 분석 (재무제표·차트·프렉탈)
- Phase 3: 투자 대가 에이전트 (버핏·멍거·버리 철학 기반)
- 미국 장 마감 후 리포트 추가 여부 (05:00 KST) — 현재 미포함
