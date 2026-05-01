# Hedge Agent (1인 포트폴리오 모니터링·리밸런싱)

## 1단계 MVP 범위

- [x] 한투 API로 보유 포지션 조회
- [x] SQLite에 일별 스냅샷 저장
- [x] 텔레그램으로 일일 요약 전송
- [ ] 비중 이탈·손익 알람 (2단계)
- [ ] 리밸런싱 거래 리스트 생성 (3단계)
- [ ] LLM 기반 일일 리포트 (4단계)

## 셋업

```bash
cd hedge_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env 채우기 (한투 키, 텔레그램, Anthropic)
mkdir -p data
```

### 한투 API 키 발급
1. [KIS Developers](https://apiportal.koreainvestment.com) 접속
2. 한투 계좌 연동 후 앱키·시크릿 발급
3. **모의투자 신청 별도 필요** (실거래 전 반드시 여기서 테스트)
4. `.env`의 `KIS_VIRTUAL=true`로 시작 권장

### 텔레그램 봇
1. 텔레그램에서 `@BotFather` 검색 → `/newbot`
2. 토큰 받아서 `.env`에 입력
3. 본인 chat_id는 `@userinfobot`에서 확인

## 동작 확인

```bash
# 1. 잔고 조회 단독 테스트
python -m core.broker

# 2. 일일 잡 수동 실행 (DB 저장 + 텔레그램)
python -m jobs.snapshot_daily
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

## cron 등록 (장 마감 후 매일 16:30)

```bash
crontab -e
```

```cron
30 16 * * 1-5 cd /절대경로/hedge_agent && /절대경로/.venv/bin/python -m jobs.snapshot_daily >> data/cron.log 2>&1
```

## 다음 단계로 넘어가기 전 체크리스트

- [ ] 모의투자 계좌로 1주일간 매일 스냅샷이 잘 쌓이는지 확인
- [ ] 텔레그램 메시지가 매일 도착하는지 확인
- [ ] `data/snapshots.db`를 SQLite 뷰어로 열어서 데이터 확인
- [ ] 토큰 만료(24시간)·재발급이 자동으로 되는지 확인 (`keep_token=True`)

## 주의사항

- `.env`와 `secrets.yaml`은 절대 git에 커밋하지 말 것 (`.gitignore` 필수)
- 실거래 전환 전 **모의투자에서 최소 2주 운영** 권장
- 이 시스템은 매매를 자동 실행하지 않음. 리밸런싱 *제안*만 생성하고 본인이 직접 주문
