# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Hedge Agent** — 한국(KR) + 미국(US) 혼합 포트폴리오를 매일 자동 모니터링하고 Claude AI로 리밸런싱 가이던스를 Telegram으로 전송하는 개인 에이전트. **실제 매매는 실행하지 않으며** 사용자가 최종 결정한다.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY 입력
mkdir data
```

## Running Jobs

```powershell
# 미국 모닝 리포트 (08:00 KST, 평일)
python -m jobs.us_morning

# 한국 일일 리포트 (16:30 KST, 평일)
python -m jobs.kr_daily
```

## Windows Task Scheduler 등록

```
Task 1: hedge_us_morning  → .venv\Scripts\python.exe -m jobs.us_morning  (매일 08:00 평일)
Task 2: hedge_kr_daily    → .venv\Scripts\python.exe -m jobs.kr_daily   (매일 16:30 평일)
Working directory: C:\absolute\path\hedge_agent
```

## Architecture

### 두 파이프라인

| 파이프라인 | 파일 | 트리거 | 내용 |
|---|---|---|---|
| US 모닝 | `jobs/us_morning.py` | 08:00 KST | 전일 미국 종가 기준 전체 리포트 |
| KR 일일 | `jobs/kr_daily.py` | 16:30 KST | 당일 한국 종가 기준 요약 리포트 |

각 파이프라인은 다음 순서로 실행된다: **holdings 로드 → 가격 조회 → 알람 체크 → 리밸런싱 계산 → 뉴스 수집 → Claude 리포트 생성 → Telegram 전송**. 개별 단계 실패 시에도 파이프라인은 계속 진행한다(graceful degradation).

### Core 모듈 역할

- `core/holdings.py` — `config/holdings.yaml` 파싱 및 검증 → `Holdings` 반환 (`HoldingPosition` 리스트 + 현금)
- `core/pricer.py` — pykrx(KR), yfinance(US + KRW/USD 환율) 가격 조회, 전체 평가금액 KRW 환산
- `core/alerter.py` — 알람 3종: ① 비중 이탈(`rebalance_band`) ② 종목 손익률 임계값 ③ 당일 포트폴리오 손익률 임계값
- `core/rebalancer.py` — 현재 비중 vs 목표 비중 델타 계산, 매수/매도 금액 제안
- `core/news_fetcher.py` — DuckDuckGo Search로 보유 종목 헤드라인 수집 (API 키 불필요)
- `core/reporter.py` — Claude API 리포트 생성 (system prompt `cache_control` 캐싱 적용)
- `core/notifier.py` — Telegram Bot API 전송, 4096자 초과 시 `split_message()`로 분할
- `core/storage.py` — SQLite 시계열 스냅샷 저장 (`data/` 디렉토리)

### 설정 파일

- `config/holdings.yaml` — **수동 관리**: 매매 후 직접 편집하는 현재 보유 수량/평균단가
- `config/portfolio.yaml` — 목표 비중(`target_pct`), 리밸런싱 밴드(`rebalance_band`), 알람 임계값

### 데이터 흐름

```
config/holdings.yaml  →  holdings.py  →  PortfolioSnapshot
                                                 ↓
config/portfolio.yaml  →  pricer.py  →  평가금액/손익 계산
                                                 ↓
                          alerter.py  →  알람 목록
                          rebalancer.py →  리밸런싱 제안
                          news_fetcher.py → 뉴스 헤드라인
                                                 ↓
                          reporter.py  →  Claude API 리포트
                                                 ↓
                          notifier.py  →  Telegram 전송
                          storage.py   →  SQLite 저장
```

## Key Constraints

- **KRW 통일**: 모든 평가는 KRW 기준. USD 자산은 `yfinance`로 조회한 KRW/USD 환율로 환산.
- **Claude API 비용**: `reporter.py`의 system prompt는 반드시 `cache_control: {"type": "ephemeral"}` 적용.
- **Telegram 4096자 제한**: `notifier.py`에서 섹션 단위 분할 처리 필수.
- **No auto-trading**: 어떤 코드도 실제 주문을 실행해서는 안 된다.

## Git Hooks

- **post-commit**: 커밋 즉시 `origin`으로 자동 push
- **pre-commit**: `.env`, `secrets.yaml`, `.kis_token*` 포함 커밋 차단
- hooks 경로: `git config core.hooksPath .githooks`로 활성화됨

## Phase Roadmap

- **Phase 1 (현재)**: 일일 모니터링 파이프라인 + Telegram 리포트
- **Phase 2**: 신규 편입 종목 심층 분석 (재무제표, 차트, 프랙탈)
- **Phase 3**: 투자 멘토 에이전트 (버핏/멍거/버리 철학 기반)
