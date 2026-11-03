# 실전 BTC 현물 봇 런북 (업비트 KRW-BTC, 5만원)

## 구성
- `src/execution/upbit_broker.py` — 업비트 브로커 (JWT/SHA512, 시장가 매수·매도, dry-run, 마켓 화이트리스트)
- `src/execution/broker_factory.py` — LIVE_TRADING 이중 잠금 + 업비트 키 확인 후 UpbitBroker 반환
- `src/trading/live_btc_bot.py` — AI 신호 + 손절(-5%)/익절(+10%) + RiskGuard, 최대 주문 1건/회
- 감사 로그: `data/live_bot_log.jsonl`, 상태: `data/live_bot_state.json` (둘 다 git 제외)

## 안전장치
| 장치 | 내용 |
|---|---|
| 자금 상한 | 봇은 5만원까지만 사용 (계좌에 더 있어도 무시) |
| 이중 잠금 | `LIVE_TRADING=true` + `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS` + `--live` 플래그 |
| Kill Switch | `data/KILL_SWITCH` 파일 생성 → 신규 매수 즉시 차단 (손절/익절 매도는 허용) |
| 일일 손실 | 하루 -5% 초과 시 그날 매수 중단 |
| 최대 낙폭 | 초기 자금 대비 -20% 시 매수 전면 중단 |
| 주문 횟수 | 하루 최대 4건 |
| 재시도 금지 | 주문 POST는 자동 재시도하지 않음 (중복 체결 방지) |

## 당일 실행 순서
1. (사용자) 업비트 API 키 발급: 자산조회 + 주문하기만, **출금하기 체크 금지**, 허용 IP 등록
2. (사용자) `.env`에 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 입력 (채팅/커밋에 붙여넣지 말 것)
3. (사용자) 업비트에 KRW 5만원 입금 확인
4. dry-run: `python -m src.trading.live_btc_bot` → 잔고 조회·AI 판단·주문 본문 검증만 수행
5. 이상 없으면 `.env`에 LIVE 두 줄 추가 후 `python -m src.trading.live_btc_bot --live`
6. 첫 체결 후 업비트 앱에서 체결 내역/수수료 대조
7. 반복 실행은 Windows 작업 스케줄러에 `--live` 명령 등록 (예: 4시간마다)

## 비상 정지
- 즉시: `data/KILL_SWITCH` 파일 생성 (예: `New-Item data\KILL_SWITCH`)
- 완전 중단: `.env`에서 LIVE_TRADING 두 줄 삭제 + 업비트에서 API 키 비활성화

## 알려진 한계
- 가격 데이터는 Yahoo BTC-USD 일봉 (AutoTrader와 동일 경로) — KRW 김프 미반영
- 일봉 기반이라 하루 여러 번 실행해도 AI 신호는 크게 안 바뀜
- 수익을 보장하는 전략은 없음. 5만원은 "잃어도 되는 학습 자금"으로 취급할 것
