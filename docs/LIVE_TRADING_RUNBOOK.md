# 실전 BTC 현물 봇 런북 (업비트 KRW-BTC, 5만원)

## 구성
- `src/execution/upbit_broker.py` — 업비트 브로커 (JWT/SHA512, 시장가 매수·매도, dry-run, 마켓 화이트리스트)
- `src/execution/broker_factory.py` — LIVE_TRADING 이중 잠금 + 업비트 키 확인 후 UpbitBroker 반환
- `src/trading/live_btc_bot.py` — **일봉 돌파(Donchian 20/10) 전략** + RiskGuard, 최대 주문 1건/회
- `src/strategy/`, `src/exchange/upbit_client.py` — 백테스트와 **같은 전략 코드**, 업비트 KRW 시세
- 감사 로그: `data/live_bot_log.jsonl`, 상태: `data/live_bot_state.json` (둘 다 git 제외)

## 전략 (백테스트 근거: `python scripts/backtest_btc.py`)
- 종가가 직전 20일 최고가를 돌파 → 전량 매수 / 직전 10일 최저가 이탈 → 전량 매도
- 완성된 일봉만 사용 (업비트 일봉은 UTC 00:00 = 한국시간 09:00 갱신 → **09:05 이후 하루 1회 실행**)
- 일봉 walk-forward(2018~2026): 샤프 1.34, 최대낙폭 -38% (단순 보유 0.83 / -74%)
- ⚠️ 최근 13개월 하락장(4시간봉 검증)에서는 모든 전략이 손실. 돌파는 -7% (단순 보유 -37%)
- 수익 대부분은 상승장에서 나옴. 횡보/하락장에서는 잔손실이 반복될 수 있음

## 안전장치
| 장치 | 내용 |
|---|---|
| 자금 상한 | 봇은 5만원까지만 사용 (계좌에 더 있어도 무시) |
| 이중 잠금 | `LIVE_TRADING=true` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS` + `--live` 플래그 |
| Kill Switch | `data/KILL_SWITCH` 파일 생성 → 신규 매수 즉시 차단 (매도는 허용) |
| 비상 손절 | 평균 매수가 대비 -15% 시 전량 매도 후, 전략이 청산 신호를 낼 때까지 재진입 잠금 |
| 일일 손실 | 하루 -5% 초과 시 그날 매수 중단 |
| 최대 낙폭 | 초기 자금 대비 -20% 시 매수 전면 중단 |
| 주문 횟수 | 하루 최대 4건 |
| 재시도 금지 | 주문 POST는 자동 재시도하지 않음 (중복 체결 방지) |

## 당일 실행 순서
1. (사용자) 업비트 API 키 발급: 자산조회 + 주문하기만, **출금하기 체크 금지**, 허용 IP 등록
2. (사용자) `.env`에 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 입력 (채팅/커밋에 붙여넣지 말 것)
3. (사용자) 업비트에 KRW 5만원 입금 확인
4. dry-run: `python -m src.trading.live_btc_bot` → 전략 목표(보유/현금), 잔고, 주문 검증만 수행
   - 진행 중인 추세 중간 진입이 싫으면 `--fresh-only` (신규 돌파 신호에서만 매수)
5. 이상 없으면 `.env`에 LIVE 두 줄 추가 후 `python -m src.trading.live_btc_bot --live`
6. 첫 체결 후 업비트 앱에서 체결 내역/수수료 대조
7. 반복 실행은 Windows 작업 스케줄러에 `--live` 명령 등록 (매일 09:05)

## 비상 정지
- 즉시: `data/KILL_SWITCH` 파일 생성 (예: `New-Item data\KILL_SWITCH`)
- 완전 중단: `.env`에서 LIVE_TRADING 두 줄 삭제 + 업비트에서 API 키 비활성화

## 알려진 한계
- 5만원 + 전량 매매 구조라 한 번의 신호 오류가 자금 전체에 영향 (그래서 -15% 비상 손절)
- 백테스트는 다음 봉 체결·편도 0.1% 비용 가정. 실제 슬리피지/수수료와 차이가 있을 수 있음
- 수익을 보장하는 전략은 없음. 5만원은 "잃어도 되는 학습 자금"으로 취급할 것
