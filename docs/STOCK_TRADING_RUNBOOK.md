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

## 안전장치

| 장치 | 내용 |
|---|---|
| 기본 모드 | `--live` 없으면 DRY-RUN (주문 미전송). `KIS_ENV` 기본값은 모의투자 |
| 실전 잠금 | `KIS_ENV=prod` + `LIVE_TRADING=true` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS` + `--live` |
| 자금 상한 | `KIS_KR_CAPITAL_KRW` / `KIS_US_CAPITAL_USD`까지만 사용 (계좌 잔액과 무관) |
| 1회 주문 상한 | `KIS_MAX_ORDER_KRW` / `KIS_MAX_ORDER_USD` — 봇 버그가 있어도 넘지 못함 |
| 화이트리스트 | 봇은 `.env`에 적은 종목만 주문 가능 |
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
   → 현금, 종목별 현재가/보유 수량이 나오면 성공
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
- `get_cash(미국)`은 KIS 해외 주문가능금액 API 특성상 기준 종목(AAPL) 가격으로 조회
- KIS API 명세(tr_id 등)는 KIS가 바꿀 수 있음 → 모의투자에서 먼저 확인하는 이유
