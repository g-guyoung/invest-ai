# 🗺️ Invest AI - 프로젝트 로드맵 & 우선순위

**작성일**: 2026-08-01 (최종 업데이트: 2026-08-03)
**목표**: AI 자동 트레이딩 플랫폼 (300만원 × 1-2개월)

> ⚠️ **2026-08-03 업데이트**: 아래 최초 로드맵에서 TradingView 위젯 사용 계획이 있었으나,
> 실제 배포 후 TradingView 무료 위젯이 한국거래소(KRX)를 지원하지 않는 문제가 발견되어
> **자체 제작 Plotly 통합 차트로 전환**했다. 또한 암호화폐 데이터소스도 Binance API가
> Streamlit Cloud에서 차단(451 에러)되어 **Yahoo Finance로 전환**했다. 최신 진행상황은
> `CLAUDE.md`의 "6. 현재 진행 상황"을 우선 참고할 것 — 이 문서는 최초 계획의 기록으로 남긴다.

---

## 📊 **현재 상황 (2026-08-01)**

### ✅ **완료된 작업**

#### Phase 1-4: 기본 대시보드 구현 ✅
```
✓ Binance Fetcher (암호화폐: BTC, ETH, XRP 등)
✓ Yahoo Fetcher (미국/한국 주식: AAPL, 005930.KS 등)
✓ FetcherRegistry (멀티마켓 자동 감지)
✓ 기술적 지표 (RSI, MACD, 볼린저 밴드)
✓ Claude AI 분석 엔진 (신호, 신뢰도, 위험도)
✓ Streamlit 대시보드 (한글화)
✓ 22개 pytest 테스트
```

#### Phase 5 Part 1: 멀티마켓 대시보드 ✅
```
✓ 한국 주식 지원 (.KS 매핑)
✓ 미국 주식 지원 (AAPL, TSLA)
✓ 비트코인 다중 지원 (BTC, ETH, XRP 등)
✓ 가격 차트 (plotly)
✓ 기술적 지표 시각화
✓ AI 분석 결과 표시
✓ 포트폴리오 요약
✓ 로컬 실행 (streamlit run src/ui/streamlit_app.py)
```

#### Phase 5 Part 2: 클라우드 기반 구조 ✅ (진행 중)
```
✓ 데이터베이스 설계 (PostgreSQL 스키마)
✓ Supabase 연동 모듈 (CRUD 함수)
✓ 초기화 SQL 스크립트
✓ requirements.txt 업데이트 (supabase-py, psycopg2)
```

---

## 🚧 **진행 중 / 할 일**

### ⏳ **즉시 필요한 작업** (우선순위 1-2순위)

#### 1️⃣ Streamlit Cloud 배포 (★★★ 긴급)
**왜 먼저?** 클라우드에서 계속 운영해야 자동 트레이딩 가능
```
필요한 것:
- GitHub 푸시 (.gitignore, .streamlit/config.toml)
- Streamlit Cloud 설정 (secrets.toml)
- 환경변수 (SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY)

소요 시간: 1-2시간
위험도: 낮음
```

#### 2️⃣ AI 자동 트레이딩 엔진 (★★★ 핵심)
**왜 필요?** 이게 없으면 페이퍼 트레이딩 불가능
```
구현 내용:
- src/trading/auto_trader.py (자동 매매 로직)
  ├── Claude AI 분석 → 신호 생성
  ├── 신호 기반 자동 주문 (BUY/SELL/HOLD)
  └── 포트폴리오 업데이트 + DB 저장

- 투자 규모 설정:
  ├── 한국 주식: 100만원
  ├── 미국 주식: 100만원
  └── 비트코인: 100만원

소요 시간: 4-6시간
위험도: 중간 (로직 검증 필요)
```

#### 3️⃣ 스케줄러 (매일 자동 실행) (★★ 높음)
**왜 필요?** 매일 정해진 시간에 AI 분석 + 자동 매매
```
구현 내용:
- src/scheduler/job_scheduler.py
  ├── 매일 09:00 - 미국/한국 주식 분석
  ├── 매일 15:00 - 비트코인 분석
  └── 결과 저장 + DB 갱신

기술: APScheduler 또는 schedule
소요 시간: 2-3시간
위험도: 낮음
```

---

### 🔧 **다음 필요한 작업** (우선순위 3-4순위)

#### 4️⃣ 실시간 대시보드 개선 (★★ 중간)
**왜 필요?** 가격/포트폴리오 실시간 반영
```
구현 내용:
- src/ui/streamlit_app.py 개선
  ├── Auto-refresh (30초/1분마다)
  ├── 실시간 가격 업데이트
  ├── 실시간 포트폴리오 수익률
  ├── 거래 기록 실시간 표시
  └── AI 분석 결과 실시간 갱신

소요 시간: 2-3시간
위험도: 낮음
```

#### 5️⃣ 포트폴리오 트래킹 고도화 (★ 중간)
**왜 필요?** 수익률, 손실률, 리스크 계산
```
구현 내용:
- src/portfolio/portfolio_tracker.py
  ├── 일일 손익 계산
  ├── 누적 수익률 추적
  ├── 시장별 수익률 분석
  └── 최대낙폭(MDD) 계산

소요 시간: 2-3시간
위험도: 낮음
```

---

## 📈 **추천 실행 순서 (가장 중요)**

```
[지금] ↓

Phase 5-2-1: Streamlit Cloud 배포
└─ 모든 환경변수 설정
└─ GitHub 자동 배포 확인
└─ 핸드폰에서 접근 가능 확인
   (약 1-2시간)

        ↓

Phase 5-2-2: AI 자동 트레이딩 엔진
└─ auto_trader.py 구현
└─ Claude AI → 신호 생성 → 주문 실행
└─ DB에 거래 기록 저장
   (약 4-6시간)

        ↓

Phase 5-2-3: 스케줄러 (자동 실행)
└─ APScheduler 설정
└─ 매일 정해진 시간 자동 실행
└─ Streamlit Cloud에서 백그라운드 실행
   (약 2-3시간)

        ↓

Phase 5-2-4: 실시간 대시보드 개선
└─ Auto-refresh 설정
└─ 실시간 가격/포트폴리오 표시
   (약 2-3시간)

        ↓

Phase 5-2-5: 1-2개월 자동 운영
└─ 모니터링
└─ 로그 분석
└─ 필요시 AI 모델 미세조정
```

---

## ⏱️ **총 소요 시간**

| 단계 | 시간 | 난이도 | 중요도 |
|------|------|--------|--------|
| Streamlit Cloud 배포 | 1-2시간 | 낮음 | ★★★ |
| AI 자동 트레이딩 엔진 | 4-6시간 | 중간 | ★★★ |
| 스케줄러 | 2-3시간 | 낮음 | ★★ |
| 실시간 대시보드 | 2-3시간 | 낮음 | ★★ |
| 포트폴리오 트래킹 | 2-3시간 | 낮음 | ★ |
| **총합** | **11-20시간** | | |

**예상 완료 시점**: 오늘 밤 ~ 내일 오후

---

## 🎯 **각 단계별 상세 계획**

### **1단계: Streamlit Cloud 배포** (지금 시작!)

**필요한 것**:
```
1. GitHub에 최신 코드 푸시
2. .streamlit/config.toml 생성
3. Streamlit Cloud 계정 + 프로젝트 연결
4. secrets.toml 설정 (SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY)
5. 자동 배포 확인
```

**결과**:
```
✓ https://your-app.streamlit.app에서 접근 가능
✓ 핸드폰에서도 접근 가능
✓ 자동 새로고침 설정
```

---

### **2단계: AI 자동 트레이딩 엔진** (가장 중요!)

**생성할 파일**:
```
src/trading/
  ├── __init__.py
  ├── auto_trader.py         # 핵심: AI → 신호 → 주문 실행
  ├── portfolio_manager.py    # 포트폴리오 관리
  └── order_executor.py       # 주문 실행 로직
```

**로직**:
```python
# 의사코드
for symbol in ['005930.KS', 'AAPL', 'BTC']:
    # 1. Claude AI 분석
    result = claude_analyzer.analyze(df)
    # 2. 신호에 따라 자동 주문
    if result.signal == 'BUY':
        order = auto_trader.execute_buy(symbol, amount=1000000)
        supabase.save_order(order)
    # 3. 포트폴리오 업데이트
    portfolio.update(symbol, quantity, price)
    # 4. DB 저장
    supabase.save_analysis(result)
```

---

### **3단계: 스케줄러** (자동화)

**로직**:
```python
# 매일 자동 실행
scheduler.add_job(
    auto_trade_korean_stocks,  # 한국 주식
    'cron',
    hour=9, minute=0
)
scheduler.add_job(
    auto_trade_us_stocks,       # 미국 주식
    'cron',
    hour=9, minute=30
)
scheduler.add_job(
    auto_trade_crypto,          # 비트코인 (24/7)
    'interval',
    hours=1
)
scheduler.start()
```

---

## 📱 **최종 결과 (1-2개월 후)**

```
대시보드 (Streamlit Cloud)
├── 📊 실시간 가격 차트
├── 🤖 AI 분석 결과 + 신호
├── 💰 포트폴리오 수익률
│   ├── 한국 주식: +5% ~ -10%
│   ├── 미국 주식: +3% ~ -8%
│   └── 비트코인: +15% ~ -20%
├── 📈 거래 기록 (매매 내역)
└── 📉 누적 수익률 추적

자동화
├── ⏰ 매일 자동 분석
├── 🤖 AI 기반 자동 매매
├── 📊 DB에 모든 기록 저장
└── 📱 핸드폰에서 실시간 모니터링
```

---

## 🚨 **주의사항**

1. **Streamlit Cloud 비용**: 무료 (조건: 매월 3시간 이상 사용)
2. **Supabase 비용**: 무료 (조건: 월 5만 행 이하)
3. **API 비용**: Anthropic (Claude) API 비용 발생 (약 $1-5/day)
4. **스케줄러 실행**: Streamlit Cloud는 백그라운드 작업이 제한적 → 외부 스케줄러 필요 (GitHub Actions 또는 Render Cron)

---

## ✅ **체크리스트**

- [x] Phase 5-2-1: Streamlit Cloud 배포 완료
- [x] Phase 5-2-2: AI 자동 트레이딩 엔진 완료 (`src/trading/auto_trader.py`, 2026-08-04)
- [x] Phase 5-2-3: 스케줄러 완료 (`.github/workflows/auto_trade.yml`, 2026-08-04 — Secrets 등록만 남음)
- [x] Phase 5-2-4: 실시간 대시보드 완료 (Streamlit "💰 포트폴리오" 탭)
- [x] Phase 5-2-5: 1-2개월 자동 운영 시작 (2026-08-04부터 매일 09:30 KST GitHub Actions로 실제 운영 중)

**예상 완료**: 2026-08-03 (오늘 + 2일)

---

**지금 바로 1단계 시작할 준비 되셨나요?** 🚀
