-- ============================================================================
-- 1회성 데이터 복구: 2026-09-04 SOFI NaN 가격 매도 사고 (미국 주식 지갑)
-- ============================================================================
-- 사고: Yahoo가 SOFI 종가를 NaN으로 반환 → 10,931.4805주가 NaN 가격으로 전량 매도됨.
--       보유분(wallet_holdings)은 삭제됐지만 매도 대금이 현금(wallets.cash)에 반영되지 않아
--       미국 주식 지갑의 약 23%가 유실 → 낙폭 -23.4% 고정 → 9/6부터 미국 주식 매수 전면 차단.
-- 코드 수정: [Phase5][Fix] NaN 가격 체결 방지 커밋 (재발 방지 완료).
--
-- 실행 위치: Supabase 대시보드 → SQL Editor. STEP 1 → 2 → 3 순서로 하나씩 실행.
-- ============================================================================


-- STEP 1. 진단 — 현재 상태 확인 (읽기 전용, 안전)
SELECT category, cash, initial_balance, updated_at
FROM wallets
WHERE category LIKE '%미국%';

SELECT id, trade_type, qty, price, amount, source, executed_at
FROM wallet_trades
WHERE symbol = 'SOFI'
ORDER BY executed_at;
-- 기대 결과: 2026-09-04 SELL 행의 price/amount가 NaN(또는 비정상)이고,
--           wallets.cash가 매도 대금만큼 모자라야 한다.
-- ※ 만약 wallets.cash 자체가 NaN으로 나오면 STEP 2 대신 아래 장부 재계산을 쓴다
--   (초기자금 − 매수 합계 + 매도 합계; STEP 2의 trade 가격 수정은 먼저 해둘 것):
--   UPDATE wallets w SET cash = w.initial_balance
--     - COALESCE((SELECT SUM(amount) FROM wallet_trades t WHERE t.category = w.category AND t.trade_type = 'BUY'), 0)
--     + COALESCE((SELECT SUM(amount) FROM wallet_trades t WHERE t.category = w.category AND t.trade_type = 'SELL'), 0)
--   WHERE w.category LIKE '%미국%';


-- STEP 2. 복구 — 아래 0.00 을 SOFI의 2026-09-04 (미국 기준) 종가로 바꾼 뒤 실행.
--         종가는 Yahoo Finance > SOFI > Historical Data 에서 확인.
BEGIN;

WITH params AS (
    SELECT 0.00::numeric AS sofi_close_2026_09_04          -- ← 여기에 종가 입력
),
bad AS (
    SELECT t.id, t.qty, p.sofi_close_2026_09_04 AS px
    FROM wallet_trades t, params p
    WHERE t.symbol = 'SOFI' AND t.trade_type = 'SELL'
      AND t.executed_at::date BETWEEN '2026-09-04' AND '2026-09-05'
      AND (t.price = 'NaN' OR t.amount = 'NaN' OR t.price <= 0)
      AND p.sofi_close_2026_09_04 > 0                        -- 종가 미입력 시 아무것도 안 바뀜
),
fixed_trade AS (
    UPDATE wallet_trades t
    SET price = bad.px,
        amount = ROUND(bad.qty * bad.px, 2),
        ai_reason = COALESCE(t.ai_reason, '') || ' [2026-11-03 NaN 가격 사후 복구]'
    FROM bad
    WHERE t.id = bad.id
    RETURNING t.category, t.amount
)
UPDATE wallets w
SET cash = w.cash + f.amount,
    updated_at = NOW()
FROM fixed_trade f
WHERE w.category = f.category;

-- 결과 확인 후 이상 없으면 COMMIT, 이상하면 ROLLBACK
SELECT category, cash FROM wallets WHERE category LIKE '%미국%';
-- COMMIT;
-- ROLLBACK;


-- STEP 3. 확인 — 다음 자동매매 실행 로그에서 미국 주식의
--         "RiskGuard 차단: 최대 낙폭 한도 초과" 메시지가 사라지면 복구 완료.
