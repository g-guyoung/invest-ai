# Phase 5 아키텍처 설계 — 멀티마켓 자동매매 플랫폼

작성일: 2026-07-29
상태: 설계 확정, 구현 착수 전 (사용자 확인 완료: 클라우드 배포 / 미국주식→한국주식→코인 순 / 토스증권 오픈API / 페이퍼 트레이딩 자체 구현)

---

## 1. 요구사항 요약

### 목적
Binance 단일 마켓 신호 생성기(Phase 1~4)를, **미국주식 · 한국주식 · 업비트 · 바이낸스 4개 시장**에서
AI 신호를 생성하고 궁극적으로 **자동매매까지 수행하는 개인용 웹 플랫폼**으로 확장한다.

### 입력
- 시장별 실시간/과거 시세 (OHLCV, 호가, 잔고)
- 사용자 리스크 설정 (투자 성향, 손절/목표 비율, 종목당 최대 비중)

### 출력
- 시장별 BUY/SELL/HOLD 신호 + Confidence Score + Reason (기존 `AnalysisResult` 스키마 재사용)
- 페이퍼/실거래 주문 실행 결과, 포지션·잔고·수익률
- 웹 대시보드 화면 (Invest AI 디자인 시스템 기반)

### 예외사항
- 토스증권 오픈API는 공식 샌드박스가 없음 → 자체 페이퍼 트레이딩 엔진 필수 (증권사 API 붕괴/장애 시 페이퍼 모드로 자동 폴백)
- 시장별 거래시간 상이 (한국 09:00~15:30, 미국 정규장+애프터마켓, 코인은 24시간) → 스케줄러가 시장별로 독립 동작해야 함
- API Rate Limit 초과, 네트워크 장애 → 기존 `src/common/retry.py` 패턴을 모든 어댑터가 공유

### 확장성
- 새 시장/브로커 추가 시 기존 코드를 고치지 않고 어댑터 클래스 1개만 추가하면 되도록 설계 (OCP)
- 향후 Phase 7 Multi-AI(OpenAI/Gemini/Local LLM)도 기존 `BaseAnalyzer` 인터페이스로 이미 대비되어 있음 (변경 불필요)

---

## 2. 시장 롤아웃 순서 및 브로커 현황

| 순서 | 시장 | 브로커/거래소 | API 상태 | 비고 |
|---|---|---|---|---|
| 1 | 미국주식 | 토스증권 오픈API | 2026-05 출시, REST, 국내+해외 지원. **공식 모의투자 미지원** | 소액 실거래 테스트 권장이나, 우리는 자체 페이퍼 엔진으로 대체 |
| 2 | 한국주식 | 토스증권 오픈API (동일 계정) | 위와 동일 | 미국주식 어댑터와 API 계약 공유 가능성 높음 |
| 3 | 코인 (1차) | 업비트 | 계정 준비됨 | 국내 코인 거래, Open API 성숙 |
| 3 | 코인 (2차) | 바이낸스 | 계정 있음, 연동 미완 | 기존 `binance_fetcher.py` 있으므로 주문 기능만 추가하면 됨 |

> 미래에셋증권은 조사 결과 범용 알고리즘 매매 API가 아닌 적립식 자동매수 위주라 이번 스코프에서 제외.

---

## 3. 핵심 설계 원칙

1. **Broker Adapter Pattern (필수)** — 모든 시장의 "주문 실행"을 동일한 인터페이스로 추상화.
   같은 신호 파이프라인이 페이퍼/토스/업비트/바이낸스 중 무엇이든 동일하게 다룰 수 있어야 한다.
2. **자체 페이퍼 트레이딩 엔진** — 브로커가 모의투자를 지원하든 안 하든 상관없이, 실시간 시세만 받아
   가상 잔고·포지션·체결을 자체 계산. 1~2개월 검증 후 어댑터만 실거래로 교체.
3. **시장 무관 분석 엔진 재사용** — Phase 3에서 만든 `indicators.py` / `base_analyzer.py` / `claude_analyzer.py`는
   시장에 상관없이 OHLCV만 받으면 동작하도록 이미 설계되어 있음. 그대로 재사용, 수정 없음.
4. **리스크 관리 레이어 신설** — Position Size, Stop Loss, Take Profit, Daily Loss Limit, Max Drawdown을
   브로커/신호 로직과 분리된 독립 모듈로 설계 (실거래 전환의 최종 안전장치).

---

## 4. 시스템 구조 (텍스트 다이어그램)

```
                         ┌─────────────────────────┐
                         │        Scheduler         │  (시장별 거래시간 인지)
                         └─────────────┬─────────────┘
                                       │
        ┌───────────────┬─────────────┼─────────────┬───────────────┐
        ▼               ▼             ▼             ▼               ▼
   [US Fetcher]    [KR Fetcher]  [Upbit Fetcher] [Binance Fetcher]  ...
        │               │             │             │
        └───────────────┴─────────────┴─────────────┘
                                       │  OHLCV (공통 스키마)
                                       ▼
                         ┌─────────────────────────┐
                         │   engine/ (기존 재사용)   │
                         │ indicators → analyzer     │
                         │ → AnalysisResult          │
                         │ (signal/confidence/reason)│
                         └─────────────┬─────────────┘
                                       ▼
                         ┌─────────────────────────┐
                         │      risk/ (신규)         │
                         │ position size / stop-loss │
                         │ / daily loss limit 검증   │
                         └─────────────┬─────────────┘
                                       ▼
                         ┌─────────────────────────┐
                         │  BrokerAdapter (신규, 추상)│
                         └─────────────┬─────────────┘
              ┌────────────┬───────────┼───────────┬────────────┐
              ▼            ▼           ▼           ▼            ▼
        [PaperBroker] [TossBroker] [UpbitBroker] [BinanceBroker] ...
        (자체 시뮬레이터, 항상 우선 사용)      (검증 후 활성화)
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   DB (PostgreSQL, 클라우드)│
                         │ 신호/주문/잔고/포지션 이력  │
                         └─────────────┬─────────────┘
                                       ▼
                         ┌─────────────────────────┐
                         │   Web App (신규 UI)       │
                         │ Invest AI 디자인 시스템    │
                         └─────────────────────────┘
```

---

## 5. 클래스 구조 (핵심만)

```python
# src/broker/base_broker.py
class BrokerAdapter(ABC):
    """모든 브로커/거래소 어댑터가 구현해야 하는 공통 인터페이스."""

    @abstractmethod
    def get_balance(self) -> Balance: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...


# src/broker/paper_broker.py
class PaperBroker(BrokerAdapter):
    """실거래 대신 가상 잔고로 체결을 시뮬레이션. 실시간 시세(MarketDataProvider)만 참조."""
    def __init__(self, initial_cash: float, price_feed: MarketDataProvider): ...


# src/broker/toss_broker.py      → 미국주식 + 한국주식 (동일 API)
# src/broker/upbit_broker.py     → 업비트
# src/broker/binance_broker.py   → 바이낸스 (기존 fetcher 확장)
```

`engine/base_analyzer.py`의 `BaseAnalyzer` / `AnalysisResult`는 변경 없이 그대로 사용 (시장 정보는
`AnalysisResult.symbol` / `market` 필드로만 구분).

---

## 6. 데이터 흐름

1. Scheduler가 시장 거래시간에 맞춰 해당 시장 Fetcher 실행
2. Fetcher → 공통 OHLCV 스키마로 변환 → DB 저장 (기존 Phase 2 방식과 동일)
3. engine/이 분석 → AnalysisResult 생성
4. risk/가 포지션 사이즈·손절 조건 검증 → 통과 시에만 주문 요청 생성
5. BrokerAdapter(현재는 항상 PaperBroker)가 주문 실행 → 체결 결과 DB 기록
6. 웹앱이 DB를 조회해 대시보드에 표시

---

## 7. 프로젝트 구조 업데이트

```
src/
 ├─ fetcher/        # 시장별 데이터 수집 (기존 binance_fetcher.py + 신규 toss_fetcher.py, upbit_fetcher.py)
 ├─ broker/         # [신규] base_broker.py, paper_broker.py, toss_broker.py, upbit_broker.py, binance_broker.py
 ├─ engine/         # 기존 유지 (indicators.py, base_analyzer.py, claude_analyzer.py) — 수정 없음
 ├─ risk/           # [신규] position_sizing.py, stop_loss.py, daily_loss_limit.py
 ├─ common/         # 기존 유지 (retry.py)
 ├─ web/            # [신규] Flask 웹앱 (Phase 4 Streamlit 프로토타입 대체), Invest AI 디자인 시스템 적용
 └─ scheduler/      # [신규] 시장별 거래시간 인지 스케줄러 (APScheduler)
tests/
config/
data/
docs/
 └─ ARCHITECTURE.md # 본 문서
README.md
requirements.txt
CLAUDE.md
```

---

## 8. 디자인 시스템 (프로젝트.pdf 계승)

- 앱명/컨셉: **Invest AI** — "AI가 실시간으로 매수·매도를 도와주는 스마트 투자 파트너"
- 컬러: `#0092F3`(블루) / `#03D8C6`(민트) / `#FFFFFF`(화이트)
- IA: 메인 → 내 투자 / 종목 분석 / AI 추천 / 포트폴리오 / 투자 비교 (하단 탭)
- 기존 학교 과제 프로토타입 화면(인트로/메인/내투자/종목분석/AI추천/포트폴리오/투자비교)을 실제 동작하는 웹앱 화면으로 그대로 구현
- 다음 단계에서 이 IA와 화면들을 와이어프레임 → Figma/FigJam으로 재도식화 (CLAUDE.md 9번 항목 참고)

---

## 9. 배포 구조 (클라우드, 상시구동)

- 후보: Oracle Cloud 무료 티어 또는 저가 VPS (본인 PC 상시 구동 불필요)
- DB: PostgreSQL (관리형 서비스 또는 서버 내 설치)
- 스케줄링: 앱 내장 APScheduler (OS cron 의존 제거)
- 접속: 개인용이므로 외부 노출 최소화 — Tailscale 등 사설 네트워크 우선 고려, 불가피하게 공개 시 로그인 인증 필수
- 인증: `.env` 기반 비밀번호 또는 세션 로그인 (Phase 5 Part1 범위 밖이면 Part6에서 처리)

---

## 10. 리스크 관리 / 보안 체크리스트

- [ ] 모든 브로커 API 키는 `.env`에만 존재, 코드/로그에 노출 금지
- [ ] `risk/` 모듈이 주문 전 최종 검증 없이는 어떤 BrokerAdapter도 주문을 낼 수 없도록 강제
- [ ] 페이퍼 → 실거래 전환은 설정 파일의 명시적 플래그로만 가능 (실수 방지)
- [ ] 일일 손실 한도 초과 시 자동 매매 중단 (Circuit Breaker)

---

## 11. 다음 단계 (Phase 5 Part 1)

**목표**: `BrokerAdapter` 추상 인터페이스 + `PaperBroker` 구현 + pytest 테스트

이 작업부터 시작하는 것을 제안. 완료 후 순서대로 Part 2(웹 UI 리뉴얼) → Part 3(토스 미국주식) →
Part 4(토스 한국주식) → Part 5(업비트/바이낸스) → Part 6(클라우드 배포+실거래 전환)로 진행.
