# Phase 6 설계: 대시보드 고도화 + 성과 분석

**목표**: Paper Trading 데이터를 실시간으로 모니터링하고, 거래 성과를 체계적으로 분석하는 대시보드 완성

---

## 🎯 Phase 6 구성

### Part 1: 자동매매 모니터링 대시보드 (1주일)
**파일**: `src/ui/monitoring_dashboard.py`

```python
# 구현 요소
- 자동매매 실행 이력 (최근 100건)
- 일일/주간/월간 거래량 차트
- AI 신호 별 승률 (BUY/SELL/HOLD)
- 카테고리별 손익률 추적
- 경고: 일일 손실률 > 5% 시 알림
```

**데이터 소스**: `SUPABASE trades 테이블`

---

### Part 2: 백테스트 엔진 (2주일)
**파일**: `src/backtest/backtester.py`

```python
# 구현 내용
def backtest(
    symbol: str,
    start_date: str,
    end_date: str,
    signal_generator: BaseAnalyzer,  # Claude AI
    initial_capital: float = 1_000_000,
    # → 거래 신호 자동 생성하며 회귀 테스트
):
    """과거 데이터로 Claude AI의 성과를 검증"""
    return BacktestResult(
        trades=[],
        metrics={
            "total_return": 12.5,  # %
            "sharpe_ratio": 1.8,
            "sortino_ratio": 2.1,
            "max_drawdown": -8.3,  # %
            "win_rate": 0.61,
            "profit_factor": 2.3,
        }
    )
```

**메트릭**:
- Sharpe Ratio (위험 조정 수익률)
- Sortino Ratio (하향 변동성 조정)
- Calmar Ratio (최대 낙폭 대비 수익)
- Profit Factor (손익비)
- Win Rate (승률)
- Max Drawdown (최대 낙폭)

---

### Part 3: 거래 분석 탭 (1주일)
**위치**: Streamlit 앱 새 탭 추가

```
Tabs:
├── 📊 차트            (기존)
├── 🤖 AI 분석         (기존)
├── 💰 포트폴리오      (기존)
├── 📈 성과 분석       (신규) ← Part 3
│   ├── 일일 손익
│   ├── AI 신호별 성과
│   ├── 카테고리별 수익률
│   └── 위험도 분석
└── 🔄 자동매매 현황   (신규) ← Part 1 모니터링
```

---

## 📋 세부 구현 계획

### Step 1: 데이터 수집 준비
```sql
-- Supabase trades 테이블 인덱스 추가
CREATE INDEX idx_trades_date ON trades(created_at DESC);
CREATE INDEX idx_trades_category ON trades(category);
```

### Step 2: 백테스트 구현
```
백테스트 로직:
1. 과거 OHLCV 데이터 로드
2. 날짜별로 루프
3. 매 날짜마다:
   a. 지표 계산 (indicators.py)
   b. Claude AI 신호 생성 (claude_analyzer.py)
   c. 신호에 따라 가상 거래 실행
   d. 손익 계산
4. 최종 메트릭 산출
```

### Step 3: 모니터링 대시보드
```
화면 구성:
[좌측]                [우측]
- 실시간 수익률      - 거래 내역 (최근)
- 카테고리별 현황    - AI 신호 성과
- 경고/알림          - 위험도 지표
```

---

## 🔗 의존성 구조

```
src/
├── backtest/
│   ├── __init__.py
│   └── backtester.py (신규)
│       ├── uses: fetcher_registry.py (OHLCV 로드)
│       ├── uses: indicators.py (기술 지표)
│       ├── uses: claude_analyzer.py (AI 신호)
│       └── uses: session_portfolio.py (거래 계산)
│
├── ui/
│   ├── streamlit_app.py (기존 + 신규 탭)
│   └── monitoring_dashboard.py (신규)
│       ├── uses: supabase_client.py (거래 기록 조회)
│       ├── uses: backtester.py (성과 분석)
│       └── uses: indicators.py (시각화)
│
└── database/
    └── supabase_client.py (기존)
```

---

## 📊 구현 순서

| 순번 | 작업 | 예상 시간 | 상태 |
|------|------|----------|------|
| 1 | Supabase 스키마 최적화 | 1일 | 📋 설계 |
| 2 | 백테스트 엔진 핵심 | 4일 | 📋 설계 |
| 3 | 백테스트 메트릭 | 2일 | 📋 설계 |
| 4 | 모니터링 대시보드 | 3일 | 📋 설계 |
| 5 | 분석 탭 UI | 2일 | 📋 설계 |
| 6 | 테스트 + 배포 | 2일 | 📋 설계 |

**총 소요 시간**: ~2주

---

## 🧪 테스트 계획

```python
# tests/test_backtester.py
def test_backtest_simple():
    """단순 BUY-HOLD 전략으로 백테스트"""
    # BTC 1년 데이터, 매수 후 홀드
    # 실제 수익률과 비교

def test_backtest_claude_ai():
    """Claude AI 신호로 백테스트"""
    # Mock Claude 응답으로 신뢰도 있는 테스트

def test_metrics_calculation():
    """메트릭 계산 정확성"""
    # Sharpe Ratio 수동 계산과 비교
```

---

## 🚀 다음 단계 (Phase 7+)

- **Phase 7**: 다중 AI (GPT, Gemini, 로컬 LLM 비교)
- **Phase 8**: 실시간 모니터링 (WebSocket, Slack 알림)
- **Phase 9**: Cloud Deployment (AWS Lambda)
- **Phase 10**: 실거래 연동 (업비트, 영웅문 API)

---

**작성일**: 2026-08-29
**상태**: 설계 완료, 구현 준비 완료
