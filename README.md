# Hedge Agent — 1인 포트폴리오 모니터링·리밸런싱

국내(KR) + 미국(US) 혼합 포트폴리오를 매일 자동 모니터링하고, Claude가 리밸런싱 가이드를 제안하는 에이전트. 실제 주문은 사용자가 직접 수행한다.

## 로드맵

| Phase | 내용 | 상태 |
|-------|------|------|
| 1-MVP | SQLite 스냅샷 + 텔레그램 전송 | ✅ 완료 |
| 1 | 알람·리밸런싱 가이드·LLM 리포트 | ✅ 완료 |
| 2 | 신규 종목 심층 분석 (재무·차트·프렉탈) | 예정 |
| 3 | 투자 대가 에이전트 (버핏·멍거·버리) | 예정 |

## Phase 1 기능

### 두 개의 파이프라인

| 시간 | Job | 내용 |
|------|-----|------|
| **08:00 KST** (평일) | `jobs/us_morning.py` | 미국 전일 종가 기준 **풀 리포트** |
| **16:30 KST** (평일) | `jobs/kr_daily.py` | 국내 당일 종가 기준 **간략 리포트** |

### 알람 3종
- 비중 이탈: 현재 비중이 목표 ± band 벗어날 때
- 개별 손익: 평가손익률 < 설정값 (기본 -10%)
- 일일 손익: 전일 대비 포트폴리오 -3% 이하

### LLM 리포트 (Claude)
- 포트폴리오 현황 요약
- 보유 종목 전일 뉴스 헤드라인 포함
- 리밸런싱 가이드 (수치 계산 + Claude 실행 의견)
- 목표 비중 재검토 제안

---

## 셋업

```bash
cd hedge_agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env 채우기 (텔레그램, Anthropic)
mkdir -p data
```

### 보유 종목 입력

`config/holdings.yaml`을 직접 편집한다. 매매 후 수동으로 업데이트.

```yaml
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

### 목표 비중 설정

`config/portfolio.yaml`에서 목표 비중과 알람 기준을 설정한다.

### 텔레그램 봇
1. 텔레그램에서 `@BotFather` 검색 → `/newbot`
2. 토큰 받아서 `.env`에 입력
3. 본인 chat_id는 `@userinfobot`에서 확인

---

## 동작 확인

```bash
# US 아침 리포트 단독 실행
python -m jobs.us_morning

# KR 마감 리포트 단독 실행
python -m jobs.kr_daily
```

## 스케줄 등록

**Windows (작업 스케줄러):**
```
작업 이름: hedge_us_morning / 트리거: 매일 08:00 평일
동작: .venv\Scripts\python.exe -m jobs.us_morning
시작 위치: C:\절대경로\hedge_agent

작업 이름: hedge_kr_daily / 트리거: 매일 16:30 평일
동작: .venv\Scripts\python.exe -m jobs.kr_daily
시작 위치: C:\절대경로\hedge_agent
```

**Linux/macOS (cron):**
```cron
0 8 * * 1-5   cd /절대경로/hedge_agent && .venv/bin/python -m jobs.us_morning >> data/cron.log 2>&1
30 16 * * 1-5  cd /절대경로/hedge_agent && .venv/bin/python -m jobs.kr_daily  >> data/cron.log 2>&1
```

## GitHub 자동 push

이 디렉토리는 `origin` 원격 저장소로 `https://github.com/yoojeongahn/hedge_agent.git`를 사용한다.

로컬에서 커밋이 만들어지면 `.githooks/post-commit` hook이 현재 브랜치를 자동으로 push한다.

```powershell
git add -A
git commit -m "작업 내용"
```

파일 변경을 감지해서 자동으로 커밋과 push까지 실행하려면 별도 터미널에서 watcher를 켜면 된다.

```powershell
.\scripts\watch-and-push.ps1
```

`.env`, `config/secrets.yaml`, `.kis_token*` 같은 로컬 비밀 파일은 `.gitignore`와 pre-commit hook으로 커밋을 막는다.

---

## 주의사항

- `.env`와 `secrets.yaml`은 절대 git에 커밋하지 말 것 (`.gitignore` 필수)
- 이 시스템은 매매를 자동 실행하지 않는다. 리밸런싱 *제안*만 생성하고 본인이 직접 주문
- `holdings.yaml`을 최신 상태로 유지해야 정확한 분석이 가능하다
