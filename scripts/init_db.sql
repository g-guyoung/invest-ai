-- ============================================================================
-- Invest AI - PostgreSQL Database Initialization Script
-- ============================================================================
-- Purpose: Supabase PostgreSQL에서 실행
-- Usage: Supabase SQL Editor 또는 psql에서 이 파일 실행

-- ============================================================================
-- 1. Users 테이블 (사용자 정보)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    initial_balance DECIMAL(20, 2) DEFAULT 100000.00,
    current_balance DECIMAL(20, 2) DEFAULT 100000.00,
    total_profit DECIMAL(20, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ============================================================================
-- 2. Symbols 테이블 (종목 정보)
-- ============================================================================

CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    market VARCHAR(50) NOT NULL,
    market_type VARCHAR(50),
    exchange VARCHAR(50),
    currency VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_symbols_market ON symbols(market);
CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(market_type);
CREATE INDEX IF NOT EXISTS idx_symbols_symbol ON symbols(symbol);

-- ============================================================================
-- 3. Prices 테이블 (OHLCV 데이터)
-- ============================================================================

CREATE TABLE IF NOT EXISTS prices (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    open_time TIMESTAMP NOT NULL,
    open DECIMAL(20, 8),
    high DECIMAL(20, 8),
    low DECIMAL(20, 8),
    close DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    interval VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol_id, open_time, interval)
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_time ON prices(symbol_id, open_time DESC);
CREATE INDEX IF NOT EXISTS idx_prices_interval ON prices(interval);

-- ============================================================================
-- 4. Analysis 테이블 (AI 분석 결과)
-- ============================================================================

CREATE TABLE IF NOT EXISTS analysis (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    signal VARCHAR(20) NOT NULL,
    confidence DECIMAL(5, 4),
    risk_score DECIMAL(5, 2),
    reason TEXT,
    rsi DECIMAL(10, 4),
    macd DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    bb_upper DECIMAL(20, 8),
    bb_lower DECIMAL(20, 8),
    analyzed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_symbol_time ON analysis(symbol_id, analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_signal ON analysis(signal);

-- ============================================================================
-- 5. Portfolio 테이블 (사용자 포트폴리오)
-- ============================================================================

CREATE TABLE IF NOT EXISTS portfolio (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    quantity DECIMAL(20, 8) NOT NULL,
    average_price DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol_id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);

-- ============================================================================
-- 6. Orders 테이블 (거래 기록 - 페이퍼 트레이딩)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    order_type VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    total_amount DECIMAL(20, 8),
    status VARCHAR(20) DEFAULT 'pending',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date DESC);

-- ============================================================================
-- 7. Portfolio History 테이블 (포트폴리오 변동 기록)
-- ============================================================================

CREATE TABLE IF NOT EXISTS portfolio_history (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_value DECIMAL(20, 2),
    profit_loss DECIMAL(20, 2),
    profit_loss_pct DECIMAL(5, 2),
    recorded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portfolio_history_user_time ON portfolio_history(user_id, recorded_at DESC);

-- ============================================================================
-- 8. Wallets / Wallet Holdings / Wallet Trades (페이퍼 트레이딩 v2)
-- ============================================================================
-- 목적: 자유 검색 심볼(symbols 테이블에 사전 등록되지 않은 종목 포함)을
--       지원하는 시장별(한국/미국/암호화폐) 가상 현금/보유종목/거래내역을
--       영구 저장한다.
-- 배경: 기존 portfolio/orders 테이블은 symbols FK를 요구해, 사용자가
--       자유 텍스트로 검색하는 아무 종목이나 사전 등록 없이 거래할 수 있는
--       현재 UI(symbol_catalog.py)와 맞지 않는다. 그래서 symbol을 문자열로
--       직접 저장하는 별도 테이블로 분리했다 (Phase 5 Part 3, 2026-08-04).
--       portfolio/orders 테이블은 삭제하지 않고 그대로 둔다 (향후 사전 등록
--       종목 기반 기능에 재사용 가능).

CREATE TABLE IF NOT EXISTS wallets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    category VARCHAR(20) NOT NULL,          -- UI 카테고리 라벨 (예: '🇰🇷 한국 주식')
    cash DECIMAL(20, 2) NOT NULL,
    initial_balance DECIMAL(20, 2) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, category)
);

CREATE TABLE IF NOT EXISTS wallet_holdings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    category VARCHAR(20) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    qty DECIMAL(20, 8) NOT NULL,
    avg_price DECIMAL(20, 8) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, category, symbol)
);

CREATE INDEX IF NOT EXISTS idx_wallet_holdings_user_cat ON wallet_holdings(user_id, category);

CREATE TABLE IF NOT EXISTS wallet_trades (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    category VARCHAR(20) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    trade_type VARCHAR(10) NOT NULL,        -- BUY / SELL
    qty DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    amount DECIMAL(20, 2) NOT NULL,
    source VARCHAR(20) DEFAULT 'MANUAL',    -- MANUAL(수동) / AUTO_AI(자동매매)
    ai_signal VARCHAR(10),                  -- 자동매매인 경우 AI 신호 (감사 추적용)
    ai_confidence DECIMAL(5, 4),
    ai_reason TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wallet_trades_user_cat_time ON wallet_trades(user_id, category, executed_at DESC);

-- ============================================================================
-- 샘플 데이터 삽입
-- ============================================================================

-- 1. 샘플 사용자
INSERT INTO users (email, username, initial_balance, current_balance)
VALUES
    ('user@example.com', 'investor1', 100000, 100000),
    ('jaicobib@gmail.com', 'gyuyoung', 500000, 500000)
ON CONFLICT DO NOTHING;

-- 2. 샘플 종목
INSERT INTO symbols (symbol, name, market, market_type, currency)
VALUES
    ('BTC', 'Bitcoin', 'binance', 'crypto', 'USD'),
    ('ETH', 'Ethereum', 'binance', 'crypto', 'USD'),
    ('AAPL', 'Apple Inc.', 'yahoo', 'stock_us', 'USD'),
    ('TSLA', 'Tesla Inc.', 'yahoo', 'stock_us', 'USD'),
    ('005930.KS', 'Samsung Electronics', 'yahoo', 'stock_kr', 'KRW'),
    ('000660.KS', 'SK Hynix', 'yahoo', 'stock_kr', 'KRW')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Views (선택사항 - 성능 최적화)
-- ============================================================================

-- 최신 분석 결과 View
CREATE OR REPLACE VIEW latest_analysis AS
SELECT
    s.symbol,
    s.name,
    s.market_type,
    a.signal,
    a.confidence,
    a.risk_score,
    a.analyzed_at,
    ROW_NUMBER() OVER (PARTITION BY s.id ORDER BY a.analyzed_at DESC) as rn
FROM analysis a
JOIN symbols s ON a.symbol_id = s.id
WHERE a.analyzed_at >= NOW() - INTERVAL '24 hours';

-- 사용자 포트폴리오 상세 View
CREATE OR REPLACE VIEW portfolio_details AS
SELECT
    p.user_id,
    s.symbol,
    s.name,
    s.market_type,
    p.quantity,
    p.average_price,
    (SELECT close FROM prices WHERE symbol_id = s.id ORDER BY open_time DESC LIMIT 1) as current_price,
    p.quantity * (SELECT close FROM prices WHERE symbol_id = s.id ORDER BY open_time DESC LIMIT 1) as current_value
FROM portfolio p
JOIN symbols s ON p.symbol_id = s.id;

-- ============================================================================
-- 함수 (선택사항)
-- ============================================================================

-- 포트폴리오 수익률 계산 함수
CREATE OR REPLACE FUNCTION calculate_profit_loss(
    p_user_id INTEGER,
    p_total_current_value DECIMAL
)
RETURNS TABLE (
    profit_loss DECIMAL,
    profit_loss_pct DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (p_total_current_value - initial_balance) as profit_loss,
        ROUND(((p_total_current_value - initial_balance) / initial_balance * 100)::NUMERIC, 2) as profit_loss_pct
    FROM users
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 완료
-- ============================================================================

-- 테이블 존재 확인
SELECT table_name FROM information_schema.tables WHERE table_schema='public';

-- 마지막 업데이트
COMMENT ON SCHEMA public IS 'Invest AI Platform - Database Schema v1.0 (2026-08-01)';
