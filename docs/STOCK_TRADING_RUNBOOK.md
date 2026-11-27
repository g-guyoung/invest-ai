# 주식 자동매매 런북 (한국투자증권 KIS — 한국 주식 + 미국 주식)

업비트 BTC 봇(`docs/LIVE_TRADING_RUNBOOK.md`)과 같은 구조·안전장치를 주식에 적용한 것이다.
**모의투자 → 소액 실전** 순서를 반드시 지킨다.

## 구성

```
.env (KIS_*)
   │
   ▼
broker_factory.get_kis_broker()  ── KIS_ENV=vts → 모의투자 서버 (가짜 돈, 기본)
   │                              └ KIS_ENV=prod → LIVE_TRADING 이중 잠금 없으면 BrokerError
   ▼
KisBroker (src/execution/kis_broker.py)
   ├ 토큰 발급·캐시 (data/kis_token_<env>.json, 24시간)
   ├ 조회: 재시도(지수 백오프) / 주문: 재시도 금지
   ├ 검증: 종목코드 형식, 화이트리스트, 1회 주문 상한, 잔고, 장 운영 시간
   ├ 한국: 시장가 / 미국: 시장성 지정가(현재가 ± 0.5%)
   └ 체결 확인: 주문번호로 체결 조회 → OrderResult(order_id, filled_qty, avg_fill_price)
   ▲
LiveStockBot (src/trading/live_stock_bot.py)
   ├ 전략: DonchianBreakout 20/10 (BTC 봇과 같은 코드), 완성된 일봉만 사용
   ├ 시장별 자금 상한 ÷ 종목 수 = 종목당 매수 금액
   ├ RiskGuard: Kill Switch / 일일 손실 5% / 낙폭 20% / 하루 6건
   └ 비상 손절 -15% + 재진입 잠금
src/execution/market_hours.py — KRX 09:00~15:30 KST, 미국 09:30~16:00 ET (서머타임 자동)
```

## 매매 대상: 전 종목 모드 (기본) / 지정 종목 모드

`KIS_KR_MODE`, `KIS_US_MODE` = `universe`(기본) 또는 `list`.

**전 종목 모드 (universe)** — 매 실행마다:
1. KIS 종목 마스터(공개 파일)로 전체 목록 수집: 코스피·코스닥 / NASDAQ·NYSE·AMEX
   (일반 주식만, `KIS_INCLUDE_ETF=true`면 ETF 포함). 하루 1회 `data/universe/`에 캐시
2. Yahoo 일봉을 200종목씩 묶음 다운로드 (`src/strategy/screener.py`)
3. 필터: 최소 주가, 20일 평균 거래대금(유동성), **1주 가격 ≤ 종목당 예산**
4. 봇과 같은 돌파 전략이 **오늘 새로 진입 신호**를 낸 종목만 → 거래대금 큰 순 상위 10개
5. 봇: 후보 + 봇이 산 종목을 함께 판단. 최대 보유 `KIS_*_MAX_POSITIONS`(기본 5)종목,
   종목당 예산 = 자금 상한 ÷ 최대 보유 수

안전 규칙:
- **봇이 산 종목만 판다.** 같은 계좌에 수동으로 산 종목은 "수동 투자"로 표시하고 건드리지 않음
  (봇 보유 목록은 `data/live_stock_state_<kr|us>.json`의 `owned`)
- 스크리닝이 실패해도(네트워크 등) 봇 보유 종목의 손절/청산은 계속 진행
- 마스터 파일 형식이 바뀌어 종목이 50개 미만으로 읽히면 매매하지 않고 멈춤 → `list` 모드로 운영
- 미국 전 종목(약 6천 개) 스캔은 수 분 걸림. 같은 날 재실행은 캐시 사용
  (미리 돌려두려면 `python -m src.trading.live_stock_bot --scan --market us`)

**지정 종목 모드 (list)** — `KIS_*_SYMBOLS`에 적은 종목만 매매 (브로커 화이트리스트도 그 종목으로 제한).

## 안전장치

| 장치 | 내용 |
|---|---|
| 기본 모드 | `--live` 없으면 DRY-RUN (주문 미전송). `KIS_ENV` 기본값은 모의투자 |
| 실전 잠금 | `KIS_ENV=prod` + `LIVE_TRADING=true` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS` + `--live` |
| 자금 상한 | `KIS_KR_CAPITAL_KRW` / `KIS_US_CAPITAL_USD`까지만 사용 (계좌 잔액과 무관) |
| 1회 주문 상한 | `KIS_MAX_ORDER_KRW` / `KIS_MAX_ORDER_USD` — 봇 버그가 있어도 넘지 못함 |
| 종목 범위 | 전 종목 모드: 봇이 고른 후보·봇 보유 종목만 주문 / 지정 모드: `.env` 종목만 (화이트리스트) |
| 최대 보유 수 | 전 종목 모드 `KIS_*_MAX_POSITIONS`(기본 5) |
| 장 시간 | 정규장 외 실주문 거부 (DRY-RUN은 경고만) |
| Kill Switch | `data/KILL_SWITCH` 파일 생성 → 신규 매수 차단 (매도는 허용) — BTC 봇과 공용 |
| 재시도 금지 | 주문 POST는 자동 재시도 안 함. 통신 오류 시 "접수 여부 불명" 에러로 멈춤 |
| 비밀 정보 | 앱키/시크릿/계좌번호는 로그·에러에 출력 안 함. 토큰 캐시는 git 제외 |

## 실행 순서

### 1단계 — 모의투자 (가짜 돈)
1. (사용자) 한국투자증권 계좌 + [KIS Developers](https://apiportal.koreainvestment.com) 가입
2. (사용자) **모의투자 신청** 후 모의투자용 앱키/시크릿 발급, 모의 계좌번호 확인
   - 미국 주식 모의투자도 쓰려면 해외주식 모의투자 신청 필요
3. (사용자) `.env`에 `KIS_ENV=vts`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` 입력
   (채팅·커밋에 붙여넣지 말 것)
4. `pip install -r requirements.txt` (Windows는 `tzdata` 필수)
5. 연결 점검: `python -m src.trading.live_stock_bot --check`
   → 현금, 계좌 보유 종목이 나오면 성공
   - 스크리닝만 확인: `python -m src.trading.live_stock_bot --scan --market kr` (KIS 키 불필요)
6. DRY-RUN: `python -m src.trading.live_stock_bot --market kr`
7. 모의 주문: `python -m src.trading.live_stock_bot --market kr --live` (장중에만)
   → KIS 앱(모의투자)에서 체결 내역 대조
8. 1~2주간 매일 실행해 로그(`data/live_stock_log.jsonl`) 확인

### 2단계 — 소액 실전 (실제 돈)
1. (사용자) **실전용** 앱키 별도 발급 (모의투자 앱키로는 실전 서버 접속 불가)
2. `.env`: `KIS_ENV=prod`, 실전 앱키/계좌번호, 자금 상한을 소액으로
   (예: `KIS_KR_CAPITAL_KRW=100000`, `KIS_MAX_ORDER_KRW=100000`)
3. `.env`에 `LIVE_TRADING=true`, `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS`
4. `python -m src.trading.live_stock_bot --check` → `--market kr --live`
5. 첫 체결 후 KIS 앱에서 체결가·수수료 대조

### 반복 실행 (Windows 작업 스케줄러)
- 한국 주식: 평일 **09:10** — `python -m src.trading.live_stock_bot --market kr --live`
- 미국 주식: 평일 **23:40** (KST) — `python -m src.trading.live_stock_bot --market us --live`
  (23:40 KST는 서머타임 여부와 무관하게 미국 정규장 중)

## 비상 정지
- 즉시: `New-Item data\KILL_SWITCH` (신규 매수 차단)
- 완전 중단: `.env`에서 `LIVE_TRADING` 두 줄 삭제 + `KIS_ENV=vts` + KIS Developers에서 앱키 폐기

## 알려진 한계
- **돌파 전략은 BTC로만 백테스트됐다.** 주식에서의 성과는 모의투자 기간에 검증해야 한다.
- 공휴일 달력은 내장하지 않음 → 휴장일 주문은 KIS가 거부 (돈 문제 없음, 로그에 거부로 남음)
- 미국 주식은 지정가라 급변 시 미체결 가능 → "접수됨, 체결 미확인" 메시지 + 주문번호를 남김.
  KIS 앱에서 확인/취소
- 잔고 조회는 첫 페이지(최대 50종목)만 읽음 — 소수 종목 운용 전제
- 종목 마스터 파일 형식은 KIS 공식 샘플 코드 기준으로 파싱했고, 실제 파일로는 아직 검증 전 →
  첫 `--scan` 결과(후보 수, 종목명)를 확인할 것. 거래정지/관리종목은 거래대금 필터로 대부분 걸러지지만 명시적 제외는 아님
- `get_cash(미국)`은 KIS 해외 주문가능금액 API 특성상 기준 종목(AAPL) 가격으로 조회
- KIS API 명세(tr_id 등)는 KIS가 바꿀 수 있음 → 모의투자에서 먼저 확인하는 이유
