# -*- coding: utf-8 -*-
"""
주식 자동매매 봇 (한국투자증권 KIS — 한국 주식 / 미국 주식) — 일봉 돌파 전략.

목적: 업비트 BTC 봇(live_btc_bot)과 같은 구조·안전장치로 주식을 매매한다.
    백테스트와 같은 전략 객체(src/strategy)를 쓰므로 "검증한 로직 = 돈이 걸린 로직"이다.

단계별 운영 (반드시 이 순서)
----------------------------
1. 연결 점검:   python -m src.trading.live_stock_bot --check
2. DRY-RUN:     python -m src.trading.live_stock_bot --market kr      (주문 미전송, 검증만)
3. 모의투자:     KIS_ENV=vts + --live  → KIS 모의투자 서버로 실제 주문 (가짜 돈)
4. 실전:         KIS_ENV=prod + LIVE_TRADING 이중 잠금 + --live (실제 돈, 소액부터)

전략 (기본): DonchianBreakout(entry=20, exit=10), 종목별 독립 적용
    - 완성된 일봉만 사용 (장중이면 오늘 봉은 버림 → 백테스트의 "다음 봉 체결"과 동일)
    - 목표=1(보유)인데 미보유 → 매수 (종목당 자금 = 시장 자금 상한 ÷ 종목 수)
    - 목표=0(현금)인데 보유 → 전량 매도
    - 평균 매입가 대비 -15%면 비상 손절 + 전략이 청산 신호를 낼 때까지 재진입 잠금

실행 시각 권장 (Windows 작업 스케줄러)
    - 한국 주식: 평일 09:10 (KST)
    - 미국 주식: 평일 23:40 (KST) — 서머타임 여부와 무관하게 미국 장중

안전장치: Kill Switch(data/KILL_SWITCH) / 일일 손실 / 최대 낙폭 / 하루 주문 횟수
    (RiskGuard) + 시장별 자금 상한 + 브로커 1회 주문 상한 + 장외 실주문 차단.
감사 로그: data/live_stock_log.jsonl, 상태: data/live_stock_state_<kr|us>.json (git 제외)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.execution.base_broker import BrokerError, OrderRequest, OrderResult, OrderSide
from src.execution.market_hours import (
    KR_CATEGORY,
    US_CATEGORY,
    drop_incomplete_stock_candle,
    is_market_open,
)
from src.execution.risk_guard import RiskGuard, RiskLimits
from src.strategy.base_strategy import BaseStrategy
from src.strategy.rule_strategies import DonchianBreakout

logger = logging.getLogger(__name__)

DATA_DIR = _PROJECT_ROOT / "data"
CANDLE_LIMIT = 250  # 약 1년치 일봉 — 돌파 전략 상태를 안정시키기에 충분


class StockBroker(Protocol):
    """봇이 필요로 하는 브로커 기능 (KisBroker가 구현, 테스트에서는 가짜 브로커)."""

    def place_order(self, request: OrderRequest) -> OrderResult: ...

    def get_cash(self, category: str) -> float: ...

    def get_price(self, category: str, symbol: str) -> float: ...

    def get_position(self, category: str, symbol: str) -> tuple[float, float]: ...


@dataclass(frozen=True)
class StockMarketConfig:
    """시장(한국/미국) 단위 봇 설정.

    Attributes:
        key: "kr" | "us" (상태 파일 이름·CLI 인자).
        category: 포트폴리오 카테고리 문자열.
        symbols: 매매 대상 종목 (한국 6자리 코드 / 미국 티커).
        capital_cap: 이 시장에서 봇이 쓸 수 있는 최대 자금 (현지 통화).
        currency: 표시용 통화 단위.
        limits: RiskGuard 한도.
    """

    key: str
    category: str
    symbols: tuple[str, ...]
    capital_cap: float
    currency: str
    limits: RiskLimits = field(default_factory=RiskLimits)


def default_limits(min_order_amount: float) -> RiskLimits:
    """주식 소액 실전용 보수적 한도 (일 -5% / 낙폭 -20% / 하루 6회)."""
    return RiskLimits(
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.20,
        max_order_pct_of_cash=1.0,  # 비중은 capital_cap ÷ 종목 수로 제어
        min_order_amount=min_order_amount,
        max_orders_per_day=6,
    )


def _split_symbols(raw: str) -> tuple[str, ...]:
    return tuple(s.strip().upper() for s in (raw or "").split(",") if s.strip())


def load_market_config(key: str) -> StockMarketConfig:
    """.env에서 시장 설정을 읽는다.

    .env:
        KIS_KR_SYMBOLS (기본 "005930"), KIS_KR_CAPITAL_KRW (기본 300000)
        KIS_US_SYMBOLS (기본 "AAPL,MSFT"), KIS_US_CAPITAL_USD (기본 1000)

    Raises:
        ValueError: key가 kr/us가 아니거나 숫자 형식 오류.
    """
    if key == "kr":
        return StockMarketConfig(
            key="kr", category=KR_CATEGORY,
            symbols=_split_symbols(os.getenv("KIS_KR_SYMBOLS", "005930")),
            capital_cap=float(os.getenv("KIS_KR_CAPITAL_KRW", "300000").replace(",", "")),
            currency="원", limits=default_limits(1_000.0),
        )
    if key == "us":
        return StockMarketConfig(
            key="us", category=US_CATEGORY,
            symbols=_split_symbols(os.getenv("KIS_US_SYMBOLS", "AAPL,MSFT")),
            capital_cap=float(os.getenv("KIS_US_CAPITAL_USD", "1000").replace(",", "")),
            currency="달러", limits=default_limits(1.0),
        )
    raise ValueError(f"market은 kr 또는 us여야 합니다: {key}")


@dataclass
class StockDecision:
    """종목 1개에 대한 1회 실행 결과 (감사 로그 단위)."""

    timestamp: str = ""
    mode: str = ""
    category: str = ""
    symbol: str = ""
    strategy: str = ""
    target_position: Optional[float] = None
    last_close: Optional[float] = None
    action: str = "NONE"  # NONE | BUY | SELL
    reason: str = ""
    executed: bool = False
    message: str = ""
    error: Optional[str] = None
    price: float = 0.0
    qty: float = 0.0
    avg_buy_price: float = 0.0
    order_id: Optional[str] = None


def default_stock_candles(category: str, symbol: str) -> Any:
    """Yahoo 일봉을 받아 완성된 봉만 반환한다 (한국은 .KS → .KQ 순으로 시도).

    Raises:
        BrokerError: 어떤 심볼로도 데이터를 받지 못한 경우.
    """
    from src.fetcher.fetcher_registry import FetcherRegistry

    candidates = [f"{symbol}.KS", f"{symbol}.KQ"] if category == KR_CATEGORY else [symbol]
    last_exc: Optional[Exception] = None
    for ysym in candidates:
        try:
            df = FetcherRegistry.get_ohlcv(symbol=ysym, market="yahoo", interval="1d", limit=CANDLE_LIMIT)
            if df is not None and not df.empty:
                return drop_incomplete_stock_candle(df, category)
        except Exception as exc:  # noqa: BLE001 - 다음 후보로
            last_exc = exc
    raise BrokerError(f"{symbol}: 일봉 데이터를 가져오지 못했습니다 ({last_exc or '빈 데이터'})")


class LiveStockBot:
    """KIS 주식 봇 (시장 1개, 종목 여러 개, 전략 주입형).

    Args:
        broker: KisBroker 등 get_price/get_position/get_cash를 제공하는 브로커.
        market: 시장 설정.
        strategy: BaseStrategy (기본 DonchianBreakout 20/10).
        risk_guard: RiskGuard (생략 시 market.limits).
        candles_fn: (category, symbol) → 완성된 일봉 DataFrame (테스트 주입용).
        today_fn: 오늘 날짜 함수 (일일 상태 리셋 기준).
        now_fn: 현재 UTC 시각 함수 (장 시간 판단).
        emergency_stop_pct: 비상 손절 비율.
        fee_buffer: 매수 금액에 곱할 수수료 여유.
        fresh_signal_only: True면 신규 돌파 신호가 난 날에만 매수.
        state_file / log_file: 상태·감사 로그 경로.
    """

    def __init__(
        self,
        broker: StockBroker,
        market: StockMarketConfig,
        strategy: Optional[BaseStrategy] = None,
        risk_guard: Optional[RiskGuard] = None,
        candles_fn: Callable[[str, str], Any] = default_stock_candles,
        today_fn: Callable[[], date] = date.today,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        emergency_stop_pct: float = 0.15,
        fee_buffer: float = 0.995,
        fresh_signal_only: bool = False,
        state_file: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ) -> None:
        if not market.symbols:
            raise ValueError(f"{market.category}: 매매 종목이 비어 있습니다 (.env KIS_{market.key.upper()}_SYMBOLS).")
        if market.capital_cap <= 0:
            raise ValueError(f"{market.category}: 자금 상한은 0보다 커야 합니다.")
        self.broker = broker
        self.market = market
        self.strategy = strategy or DonchianBreakout(entry=20, exit=10)
        self.risk_guard = risk_guard or RiskGuard(limits=market.limits)
        self._candles_fn = candles_fn
        self._today_fn = today_fn
        self._now_fn = now_fn
        self.emergency_stop_pct = emergency_stop_pct
        self.fee_buffer = fee_buffer
        self.fresh_signal_only = fresh_signal_only
        self.state_file = state_file or DATA_DIR / f"live_stock_state_{market.key}.json"
        self.log_file = log_file or DATA_DIR / "live_stock_log.jsonl"

    @property
    def dry_run(self) -> bool:
        return bool(getattr(self.broker, "dry_run", True))

    @property
    def mode(self) -> str:
        return str(getattr(self.broker, "mode_label", "DRY-RUN" if self.dry_run else "LIVE"))

    # ------------------------------------------------------------------
    # 상태 / 로그
    # ------------------------------------------------------------------

    def _load_state(self, current_total: float) -> dict[str, Any]:
        today = self._today_fn().isoformat()
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            state = {}
        locks = state.get("stop_lock") if isinstance(state.get("stop_lock"), dict) else {}
        if state.get("date") != today:
            # 날짜가 바뀌면 일일 값만 리셋. 종목별 재진입 잠금은 유지.
            state = {"date": today, "day_start_total": current_total, "orders_today": 0}
        state["stop_lock"] = locks
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def _append_log(self, decisions: list[StockDecision]) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            for d in decisions:
                f.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")

    def _new_decision(self, symbol: str = "") -> StockDecision:
        return StockDecision(
            timestamp=datetime.now().isoformat(timespec="seconds"), mode=self.mode,
            category=self.market.category, symbol=symbol, strategy=self.strategy.describe(),
        )

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------

    def run_once(self) -> list[StockDecision]:
        """시장 1회 실행 (종목마다 최대 주문 1건). 예외를 던지지 않고 결과에 기록한다."""
        decisions: list[StockDecision] = []
        try:
            self._run(decisions)
        except BrokerError as exc:
            d = self._new_decision()
            d.error = f"브로커 오류: {exc}"
            decisions.append(d)
            logger.error(d.error)
        except Exception as exc:  # noqa: BLE001 - 봇이 죽지 않도록
            d = self._new_decision()
            d.error = f"예상치 못한 오류: {type(exc).__name__}: {exc}"
            decisions.append(d)
            logger.exception("live_stock_bot 실행 중 오류")
        self._append_log(decisions)
        return decisions

    def _run(self, decisions: list[StockDecision]) -> None:
        mk = self.market
        if not self.dry_run and not is_market_open(mk.category, self._now_fn()):
            d = self._new_decision()
            d.message = "정규장 시간이 아니라 실행하지 않습니다."
            decisions.append(d)
            return

        # 1) 시장 단위 스냅샷 — 자금 상한/리스크 계산 기준
        cash = self.broker.get_cash(mk.category)
        snapshots: dict[str, StockDecision] = {}
        for symbol in mk.symbols:
            d = self._new_decision(symbol)
            try:
                d.price = self.broker.get_price(mk.category, symbol)
                d.qty, d.avg_buy_price = self.broker.get_position(mk.category, symbol)
                snapshots[symbol] = d
            except (BrokerError, ValueError) as exc:
                d.error = f"시세/잔고 조회 실패: {exc}"
                decisions.append(d)

        cost_basis = sum(d.qty * d.avg_buy_price for d in snapshots.values())
        investable = max(0.0, min(cash, mk.capital_cap - cost_basis))
        current_total = investable + sum(d.qty * d.price for d in snapshots.values())
        state = self._load_state(current_total)
        per_symbol = mk.capital_cap / len(mk.symbols)

        # 2) 종목별 판단
        for symbol, d in snapshots.items():
            try:
                investable -= self._decide(d, state, per_symbol, investable, current_total)
            except BrokerError as exc:
                d.error = f"브로커 오류: {exc}"
            except Exception as exc:  # noqa: BLE001 - 한 종목 오류가 나머지를 막지 않도록
                d.error = f"{type(exc).__name__}: {exc}"
                logger.exception(f"{symbol} 처리 중 오류")
            decisions.append(d)
        self._save_state(state)

    def _decide(
        self, d: StockDecision, state: dict[str, Any], per_symbol: float,
        investable: float, current_total: float,
    ) -> float:
        """종목 1개 판단·실행. 반환값 = 이번에 매수에 쓴 금액(투자 가능액 차감용)."""
        locks: dict[str, bool] = state["stop_lock"]
        has_position = d.qty >= 1

        # 비상 손절 — 전략/Kill Switch와 무관하게 허용
        if has_position and d.avg_buy_price > 0:
            pnl = d.price / d.avg_buy_price - 1.0
            if pnl <= -self.emergency_stop_pct:
                locks[d.symbol] = True
                self._order(d, state, OrderSide.SELL, 0.0, f"비상 손절 {pnl:+.1%} (한도 -{self.emergency_stop_pct:.0%})")
                return 0.0

        df = self._candles_fn(self.market.category, d.symbol)
        if df is None or len(df) < 2:
            d.error = "일봉 데이터 부족"
            return 0.0
        positions = self.strategy.generate_positions(df)
        target = float(positions.iloc[-1])
        prev = float(positions.iloc[-2])
        d.target_position, d.last_close = target, float(df["close"].iloc[-1])

        if target < 0.5:
            locks[d.symbol] = False
            if has_position:
                self._order(d, state, OrderSide.SELL, 0.0, f"전략 청산 신호 ({self.strategy.describe()})")
            else:
                d.message = "전략: 현금 보유 구간 — 매매 없음"
            return 0.0

        if has_position:
            d.message = "전략: 보유 유지"
            return 0.0
        if locks.get(d.symbol):
            d.message = "비상 손절 후 재진입 잠금 — 전략 청산 신호 전까지 매수하지 않음"
            return 0.0
        if self.fresh_signal_only and prev >= 0.5:
            d.message = "진행 중인 추세 — 신규 돌파 신호까지 대기(fresh_signal_only)"
            return 0.0

        amount = float(int(min(per_symbol, investable) * self.fee_buffer * 100) / 100)
        verdict = self.risk_guard.check_buy(
            amount=amount, available_cash=investable, initial_balance=self.market.capital_cap,
            current_total=current_total, day_start_total=state["day_start_total"],
            orders_today=int(state["orders_today"]),
        )
        if not verdict.allowed:
            d.message = f"🛡️ RiskGuard 차단: {verdict.reason}"
            return 0.0
        executed = self._order(d, state, OrderSide.BUY, amount, f"전략 진입 신호 ({self.strategy.describe()})")
        return amount if executed else 0.0

    def _order(self, d: StockDecision, state: dict[str, Any], side: OrderSide, amount: float, reason: str) -> bool:
        d.action, d.reason = side.value, reason
        req = OrderRequest(
            category=self.market.category, symbol=d.symbol, name=d.symbol, side=side,
            price=d.price, amount=amount, source="AUTO_RULE", ai_signal=side.value, ai_reason=reason,
        )
        result = self.broker.place_order(req)
        d.executed, d.message, d.order_id = result.success, result.message, result.order_id
        if not self.dry_run and (result.success or result.order_id):
            state["orders_today"] = int(state["orders_today"]) + 1  # 미체결 접수도 1건으로 센다
        return result.success


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _print_check(broker: Any, market: StockMarketConfig) -> int:
    """연결 점검: 토큰 발급 → 현금 → 종목별 시세/보유 (주문 없음)."""
    print(f"\n[{market.category}] {broker.mode_label} | 장 운영중={is_market_open(market.category)}")
    errors = 0
    try:
        print(f"  주문 가능 현금: {broker.get_cash(market.category):,.2f}{market.currency}")
    except BrokerError as exc:
        errors += 1
        print(f"  ❌ 현금 조회 실패: {exc}")
    for symbol in market.symbols:
        try:
            price = broker.get_price(market.category, symbol)
            qty, avg = broker.get_position(market.category, symbol)
            print(f"  {symbol}: 현재가 {price:,.2f} | 보유 {qty:g}주 (평단 {avg:,.2f})")
        except (BrokerError, ValueError) as exc:
            errors += 1
            print(f"  ❌ {symbol}: {exc}")
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 진입점. 기본은 DRY-RUN, --live일 때만 주문 전송 (모의투자/실전은 KIS_ENV가 결정)."""
    parser = argparse.ArgumentParser(description="KIS 주식 봇 — 일봉 돌파 전략 (기본 DRY-RUN)")
    parser.add_argument("--market", choices=["kr", "us", "all"], default="all")
    parser.add_argument("--live", action="store_true", help="주문 전송 (KIS_ENV=vts면 모의투자, prod면 실전+이중 잠금)")
    parser.add_argument("--check", action="store_true", help="연결/잔고/시세 점검만 (주문 없음)")
    parser.add_argument("--fresh-only", action="store_true", help="신규 돌파 신호가 난 날에만 매수")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from src.common.env_loader import load_environment
    from src.execution.broker_factory import get_kis_broker

    load_environment()
    keys = ["kr", "us"] if args.market == "all" else [args.market]
    try:
        markets = [load_market_config(k) for k in keys]
        allowed = [s for m in markets for s in m.symbols]
        broker = get_kis_broker(dry_run=args.check or not args.live, allowed_symbols=allowed)
    except (BrokerError, ValueError) as exc:
        logger.error(str(exc))
        return 2

    if args.check:
        return 1 if sum(_print_check(broker, m) for m in markets) else 0

    exit_code = 0
    for market in markets:
        bot = LiveStockBot(broker=broker, market=market, fresh_signal_only=args.fresh_only)
        print(f"\n[{bot.mode}] {market.category} | {bot.strategy.describe()} | 자금 상한 {market.capital_cap:,.0f}{market.currency}")
        for d in bot.run_once():
            tp = "—" if d.target_position is None else ("보유" if d.target_position >= 0.5 else "현금")
            print(f"  {d.symbol or '-'}: 목표={tp} 현재가={d.price:,.2f} 보유={d.qty:g} → "
                  f"{d.action} executed={d.executed} | {d.error or d.message}")
            if d.error:
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
