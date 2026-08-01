# 🗄️ Invest AI - 데이터베이스 스키마 설계

**Database**: PostgreSQL (Supabase)  
**목적**: 멀티마켓 투자 AI 플랫폼의 데이터 저장소

---

## 📋 테이블 설계

### 1️⃣ `symbols` - 종목 정보 테이블

**목적**: 추적하는 모든 종목의 기본 정보 저장

```sql
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,      -- BTC, AAPL, 005930.KS
    name VARCHAR(100) NOT NULL,               -- Bitcoin, Apple Inc., 삼성전자
    market VARCHAR(50) NOT NULL,              -- binance, yahoo
    market_type VARCHAR(50),                  -- crypto, stock_us, stock_kr
    exchange VARCHAR(50),                     -- NASDAQ, KRX, etc.
    currency VARCHAR(10),                     -- USD, KRW, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_symbols_market ON symbols(market);
CREATE INDEX idx_symbols_type ON symbols(market_type);
```

**샘플 데이터:**
```
| symbol  | name           | market    | market_type | currency |
|---------|----------------|-----------|-------------|----------|
| BTC     | Bitcoin        | binance   | crypto      | USD      |
| AAPL    | Apple Inc.     | yahoo     | stock_us    | USD      |
| 005930  | Samsung        | yahoo     | stock_kr    | KRW      |
```

---

### 2️⃣ `prices` - OHLCV 가격 데이터

**목적**: 각 종목의 시간별 가격 데이터 저장

```sql
CREATE TABLE prices (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    open_time TIMESTAMP NOT NULL,
    open DECIMAL(20, 8),
    high DECIMAL(20, 8),
    low DECIMAL(20, 8),
    close DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    interval VARCHAR(10),                     -- 1m, 5m, 15m, 1h, 1d
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol_id, open_time, interval)
);

-- 인덱스: 성능 최적화
CREATE INDEX idx_prices_symbol_time ON prices(symbol_id, open_time DESC);
CREATE INDEX idx_prices_interval ON prices(interval);
```

**샘플:**
```
| symbol_id | open_time           | close  | volume   | interval |
|-----------|---------------------|--------|----------|----------|
| 1         | 2026-08-01 09:00:00 | 45000  | 1000.5   | 1d       |
| 2         | 2026-08-01 14:30:00 | 150.25 | 5000000  | 1h       |
```

---

### 3️⃣ `analysis` - AI 분석 결과

**목적**: Claude AI의 분석 신호, 신뢰도, 위험도 저장

```sql
CREATE TABLE analysis (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    signal VARCHAR(20) NOT NULL,              -- BUY, SELL, HOLD
    confidence DECIMAL(5, 2),                 -- 0.00 ~ 1.00 (0~100%)
    risk_score DECIMAL(5, 2),                 -- 0.00 ~ 10.00
    reason TEXT,                              -- 분석 이유
    rsi DECIMAL(10, 4),
    macd DECIMAL(20, 8),
    bb_upper DECIMAL(20, 8),
    bb_lower DECIMAL(20, 8),
    analyzed_at TIMESTAMP NOT NULL,           -- 분석 시각
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
);

-- 인덱스
CREATE INDEX idx_analysis_symbol_time ON analysis(symbol_id, analyzed_at DESC);
CREATE INDEX idx_analysis_signal ON analysis(signal);
```

**샘플:**
```
| symbol_id | signal | confidence | risk_score | analyzed_at         |
|-----------|--------|------------|------------|---------------------|
| 1         | BUY    | 0.85       | 3.2        | 2026-08-01 15:00:00 |
| 2         | HOLD   | 0.65       | 5.1        | 2026-08-01 14:30:00 |
```

---

### 4️⃣ `portfolio` - 사용자 포트폴리오

**목적**: 각 사용자의 포트폴리오 구성 저장

```sql
CREATE TABLE portfolio (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    quantity DECIMAL(20, 8) NOT NULL,         -- 보유 수량
    average_price DECIMAL(20, 8),             -- 평균 매수가
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, symbol_id)
);

CREATE INDEX idx_portfolio_user ON portfolio(user_id);
```

---

### 5️⃣ `orders` - 거래 기록 (페이퍼 트레이딩)

**목적**: 모의 거래 주문 기록 (미실행 거래)

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    order_type VARCHAR(20) NOT NULL,          -- BUY, SELL
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    total_amount DECIMAL(20, 8),              -- quantity * price
    status VARCHAR(20) DEFAULT 'pending',     -- pending, filled, cancelled
    order_date TIMESTAMP DEFAULT NOW(),
    filled_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
);

CREATE INDEX idx_orders_user_status ON orders(user_id, status);
CREATE INDEX idx_orders_date ON orders(order_date DESC);
```

---

### 6️⃣ `users` - 사용자 정보

**목적**: 플랫폼 사용자 관리

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255),                -- bcrypt 해시
    initial_balance DECIMAL(20, 2),            -- 시작 자본
    current_balance DECIMAL(20, 2),            -- 현재 자산
    total_profit DECIMAL(20, 2),               -- 누적 수익
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
```

---

### 7️⃣ `portfolio_history` - 포트폴리오 변동 기록

**목적**: 포트폴리오 가치의 시간별 변화 추적

```sql
CREATE TABLE portfolio_history (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_value DECIMAL(20, 2),                -- 총 자산가
    profit_loss DECIMAL(20, 2),                -- 손익
    profit_loss_pct DECIMAL(5, 2),             -- 손익률 (%)
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_portfolio_history_user_time ON portfolio_history(user_id, recorded_at DESC);
```

---

## 📊 데이터 흐름 다이어그램

```
┌─────────────────┐
│  Binance API    │
│  Yahoo Finance  │
└────────┬────────┘
         │ (OHLCV 데이터)
         ▼
┌─────────────────┐
│   symbols       │ ◄─── 종목 정보
│   prices        │ ◄─── 가격 데이터
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Claude AI       │ (기술적 지표 + 분석)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  analysis       │ ◄─── 신호, 신뢰도, 위험도
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Streamlit Dashboard (실시간 표시)  │
│  - 가격 차트                        │
│  - 기술적 지표                      │
│  - AI 분석 결과                     │
│  - 포트폴리오 추적                  │
└─────────────────────────────────────┘
```

---

## 🔑 Key Design Decisions

1. **DECIMAL 타입**: 금융 데이터는 부동소수점 오차를 피하기 위해 DECIMAL 사용
2. **Timestamp**: 모든 레코드에 `created_at`, `updated_at` 기록 (감사 추적)
3. **Foreign Keys**: 데이터 무결성 보장
4. **인덱스**: 조회 성능 최적화 (symbol, time, user 기준)
5. **Partitioning** (향후): `prices`, `analysis` 테이블은 시간 기반 파티셀 고려

---

## 🚀 마이그레이션 스크립트

초기화 SQL은 `scripts/init_db.sql`에 저장됨.

```bash
# Supabase에서 직접 실행하거나
psql -U postgres -d invest_ai -f scripts/init_db.sql
```

---

## 📈 확장 계획 (향후)

- [ ] 실시간 데이터 스트리밍 (WebSocket)
- [ ] 사용자별 설정 저장 (preferences, alerts)
- [ ] 거래 API 로그 (주문 실행 기록)
- [ ] 머신러닝 학습 데이터 저장

---

**작성일**: 2026-08-01  
**상태**: Phase 5, Part 2 - 클라우드 배포
