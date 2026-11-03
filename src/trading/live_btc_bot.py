# -*- coding: utf-8 -*-
"""
실전 비트코인 현물 봇 (업비트 KRW-BTC, 소액 전용) — 일봉 돌파(Donchian) 전략.

목적: 백테스트(scripts/backtest_btc.py)에서 검증한 전략 코드(src/strategy)를 그대로 써서
    업비트 KRW-BTC를 자동 매매한다. 백테스트와 실전이 같은 전략 객체를 공유하므로
    "검증한 로직과 돈이 걸린 로직이 다른" 사고가 구조적으로 막힌다.

전략 (기본): DonchianBreakout(entry=20, exit=10)
    - 종가가 직전 20일 최고가를 돌파하면 전량 매수
    - 종가가 직전 10일 최저가를 이탈하면 전량 매도
    - 완성된 일봉만 사용 (진행 중인 오늘 봉은 버린다 → 백테스트의 "다음 봉 체결"과 동일)
    - 업비트 일봉은 UTC 00:00(= 한국시간 09:00)에 갱신되므로 하루 1회, 09:05 이후 실행 권장

한 번 실행(run_once) = 최대 주문 1건:
    1. 시세/잔고/평균매수가 조회 (업비트)
    2. -15% 비상 손절이면 즉시 전량 매도 (이후 전략이 청산 신호를 낼 때까지 재진입 잠금)
    3. 전략 목표 포지션 계산 → 0이면 (보유 시) 전량 매도, 1이면 (미보유 시) 전량 매수
    4. 매수는 RiskGuard(Kill Switch / 낙폭 / 일일 손실 / 주문 횟수) 통과 필수
    5. 결과를 data/live_bot_log.jsonl 에 감사 로그로 남김

운영 모드
---------
- 기본: dry-run (조회는 실제, 주문 전송은 안 함)
      python -m src.trading.live_btc_bot
- 실전: .env 에 LIVE_TRADING=true + LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS
      python -m src.trading.live_btc_bot --live
- 즉시 정지: data/KILL_SWITCH 파일 생성 (신규 매수 차단, 매도는 계속 허용)

자금 상한: capital_cap_krw(기본 5만원)까지만 봇 자금으로 간주한다.
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
from typing import Any, Callable, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.execution.base_broker import BrokerError, OrderRequest, OrderSide
from src.execution.risk_guard import RiskGuard, RiskLimits
from src.execution.upbit_broker import CRYPTO_CATEGORY, MIN_ORDER_KRW, UpbitBroker
from src.strategy.base_strategy import BaseStrategy
from src.strategy.rule_strategies import DonchianBreakout

logger = logging.getLogger(__name__)

DATA_DIR = _PROJECT_ROOT / "data"
#: 돌파 전략의 포지션은 과거 진입 이력에 의존하므로, 충분히 긴 구간을 받아 상태를 안정시킨다.
CANDLE_COUNT = 600


def _default_limits() -> RiskLimits:
    """5만원 실전용 보수적 한도 (일 -5% / 낙폭 -20% / 하루 4회)."""
    return RiskLimits(
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.20,
        max_order_pct_of_cash=1.0,  # 소액이라 비중 상한 대신 capital_cap으로 제어
        min_order_amount=MIN_ORDER_KRW,
        max_orders_per_day=4,
    )


@dataclass(frozen=True)
class LiveBotConfig:
    """실전 봇 설정.

    Attributes:
        market: 업비트 마켓 코드.
        symbol: 코인 심볼.
        capital_cap_krw: 봇이 사용할 수 있는 최대 자금.
        emergency_stop_pct: 평균 매수가 대비 비상 손절 비율 (0.15 = -15%).
            전략 청산(10일 저가 이탈)보다 훨씬 깊은 "최후의 안전망"이다.
        fee_buffer: 수수료(0.05%) 여유 — 투입 금액에 곱한다.
        fresh_signal_only: True면 "오늘 새로 진입 신호가 난 경우"에만 매수한다
            (이미 상승 추세 중간이면 다음 신규 돌파까지 대기). 기본 False(전략과 동일).
        state_file: 일일 손실/주문 횟수/재진입 잠금 상태 파일.
        log_file: 감사 로그(JSON Lines) 파일.
        limits: RiskGuard 한도.
    """

    market: str = "KRW-BTC"
    symbol: str = "BTC"
    capital_cap_krw: float = 50_000.0
    emergency_stop_pct: float = 0.15
    fee_buffer: float = 0.995
    fresh_signal_only: bool = False
    state_file: Path = DATA_DIR / "live_bot_state.json"
    log_file: Path = DATA_DIR / "live_bot_log.jsonl"
    limits: RiskLimits = field(default_factory=_default_limits)


@dataclass
class BotDecision:
    """1회 실행 결과 (감사 로그 단위)."""

    timestamp: str = ""
    dry_run: bool = True
    strategy: str = ""
    target_position: Optional[float] = None  # 전략의 목표 포지션 (0=현금, 1=보유)
    last_close: Optional[float] = None  # 마지막 "완성된" 일봉 종가
    action: str = "NONE"  # NONE | BUY | SELL
    reason: str = ""
    executed: bool = False
    message: str = ""
    error: Optional[str] = None
    price: float = 0.0
    qty: float = 0.0
    avg_buy_price: float = 0.0
    krw_cash: float = 0.0


def drop_incomplete_candle(df: Any, now_utc: Optional[datetime] = None) -> Any:
    """진행 중인(아직 닫히지 않은) 오늘 일봉을 제거한다.

    업비트 일봉의 open_time은 UTC 00:00이다. open_time이 "오늘(UTC)" 이후인 봉은
    아직 종가가 확정되지 않았으므로 전략 입력에서 뺀다.

    Args:
        df: open_time(UTC, tz-naive) 컬럼이 있는 OHLCV DataFrame.
        now_utc: 현재 UTC 시각 (테스트 주입용).

    Returns:
        완성된 봉만 남은 DataFrame (인덱스 재설정).
    """
    import pandas as pd

    now = now_utc or datetime.now(timezone.utc)
    today_start = pd.Timestamp(now.date())  # tz-naive UTC 자정
    return df[df["open_time"] < today_start].reset_index(drop=True)


class LiveBtcBot:
    """업비트 BTC 현물 실전 봇 (전략 주입형).

    Args:
        broker: UpbitBroker (dry_run 여부는 브로커가 결정).
        strategy: BaseStrategy 구현체 (기본 DonchianBreakout 20/10 — 백테스트 검증값).
        config: 봇 설정.
        risk_guard: RiskGuard (생략 시 config.limits로 생성).
        candles_fn: 완성된 일봉 DataFrame을 돌려주는 함수 (테스트 주입용).
        today_fn: 오늘 날짜(로컬) 반환 함수 (테스트 주입용).
    """

    def __init__(
        self,
        broker: UpbitBroker,
        strategy: Optional[BaseStrategy] = None,
        config: Optional[LiveBotConfig] = None,
        risk_guard: Optional[RiskGuard] = None,
        candles_fn: Optional[Callable[[], Any]] = None,
        today_fn: Callable[[], date] = date.today,
    ) -> None:
        self.broker = broker
        self.strategy = strategy or DonchianBreakout(entry=20, exit=10)
        self.config = config or LiveBotConfig()
        self.risk_guard = risk_guard or RiskGuard(limits=self.config.limits)
        self._candles_fn = candles_fn or self._default_candles
        self._today_fn = today_fn

    # ------------------------------------------------------------------
    # 상태 파일 (일일 손실 기준선 / 주문 횟수 / 재진입 잠금)
    # ------------------------------------------------------------------

    def _load_state(self, current_total: float) -> dict[str, Any]:
        today = self._today_fn().isoformat()
        try:
            state = json.loads(self.config.state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            state = {}
        if state.get("date") != today:
            # 날짜가 바뀌면 일일 값은 리셋하되, 재진입 잠금은 며칠이고 유지한다.
            state = {
                "date": today,
                "day_start_total": current_total,
                "orders_today": 0,
                "stop_lock": bool(state.get("stop_lock", False)),
            }
        state.setdefault("stop_lock", False)
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def _append_log(self, decision: BotDecision) -> None:
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # 데이터
    # ------------------------------------------------------------------

    def _default_candles(self) -> Any:
        """업비트 KRW 일봉을 받아 완성된 봉만 반환한다 (비정상 종가는 수집기에서 제거됨)."""
        from src.exchange.upbit_client import UpbitQuotationClient

        df = UpbitQuotationClient().get_ohlcv(self.config.market, "1d", count=CANDLE_COUNT)
        return drop_incomplete_candle(df)

    # ------------------------------------------------------------------
    # 핵심 로직
    # ------------------------------------------------------------------

    def run_once(self) -> BotDecision:
        """봇을 1회 실행한다 (최대 주문 1건). 예외를 던지지 않고 BotDecision에 기록한다."""
        decision = BotDecision(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            dry_run=bool(getattr(self.broker, "dry_run", True)),
            strategy=self.strategy.describe(),
        )
        try:
            self._run(decision)
        except BrokerError as exc:
            decision.error = f"브로커 오류: {exc}"
            logger.error(decision.error)
        except Exception as exc:  # noqa: BLE001 - 봇이 죽지 않도록
            decision.error = f"예상치 못한 오류: {type(exc).__name__}: {exc}"
            logger.exception("live_btc_bot 실행 중 오류")
        self._append_log(decision)
        return decision

    def _run(self, d: BotDecision) -> None:
        cfg = self.config
        price = self.broker.get_price(cfg.market)
        qty, avg = self.broker.get_position(cfg.symbol)
        cash = self.broker.get_cash(CRYPTO_CATEGORY)

        cost_basis = qty * avg
        investable = max(0.0, min(cash, cfg.capital_cap_krw - cost_basis))
        current_total = investable + qty * price
        d.price, d.qty, d.avg_buy_price, d.krw_cash = price, qty, avg, cash

        state = self._load_state(current_total)
        has_position = qty * price >= MIN_ORDER_KRW

        # 1) 비상 손절 — 전략/Kill Switch와 무관하게 허용, 이후 재진입 잠금
        if has_position and avg > 0:
            pnl = price / avg - 1.0
            if pnl <= -cfg.emergency_stop_pct:
                state["stop_lock"] = True
                self._sell(d, state, f"비상 손절 {pnl:+.1%} (한도 -{cfg.emergency_stop_pct:.0%})")
                return

        # 2) 전략 목표 포지션 (완성된 일봉 기준)
        df = self._candles_fn()
        positions = self.strategy.generate_positions(df)
        target = float(positions.iloc[-1])
        prev_target = float(positions.iloc[-2]) if len(positions) > 1 else 0.0
        d.target_position = target
        d.last_close = float(df["close"].iloc[-1])

        if target < 0.5:
            state["stop_lock"] = False  # 전략이 청산 신호를 냈으므로 잠금 해제
            if has_position:
                self._sell(d, state, f"전략 청산 신호 ({self.strategy.describe()})")
                return
            d.message = "전략: 현금 보유 구간 — 매매 없음"
            self._save_state(state)
            return

        # target == 1
        if has_position:
            d.message = "전략: 보유 유지"
        elif state["stop_lock"]:
            d.message = "비상 손절 후 재진입 잠금 — 전략이 청산 신호를 낼 때까지 매수하지 않음"
        elif cfg.fresh_signal_only and prev_target >= 0.5:
            d.message = "이미 진행 중인 추세 — 신규 돌파 신호까지 대기(fresh_signal_only)"
        else:
            self._buy(d, state, investable, current_total)
            return
        self._save_state(state)

    def _buy(self, d: BotDecision, state: dict[str, Any], investable: float, current_total: float) -> None:
        cfg = self.config
        amount = float(int(investable * cfg.fee_buffer))
        verdict = self.risk_guard.check_buy(
            amount=amount,
            available_cash=investable,
            initial_balance=cfg.capital_cap_krw,
            current_total=current_total,
            day_start_total=state["day_start_total"],
            orders_today=state["orders_today"],
        )
        if not verdict.allowed:
            d.message = f"🛡️ RiskGuard 차단: {verdict.reason}"
            self._save_state(state)
            return

        d.action, d.reason = "BUY", f"전략 진입 신호 ({self.strategy.describe()})"
        req = OrderRequest(
            category=CRYPTO_CATEGORY, symbol=cfg.symbol, name="비트코인", side=OrderSide.BUY,
            price=d.price, amount=amount, source="AUTO_RULE", ai_signal="BUY",
            ai_confidence=None, ai_reason=d.reason,
        )
        self._execute(d, state, req)

    def _sell(self, d: BotDecision, state: dict[str, Any], reason: str) -> None:
        cfg = self.config
        d.action, d.reason = "SELL", reason
        req = OrderRequest(
            category=CRYPTO_CATEGORY, symbol=cfg.symbol, name="비트코인", side=OrderSide.SELL,
            price=d.price, amount=0.0, source="AUTO_RULE", ai_signal="SELL",
            ai_confidence=None, ai_reason=reason,
        )
        self._execute(d, state, req)

    def _execute(self, d: BotDecision, state: dict[str, Any], req: OrderRequest) -> None:
        result = self.broker.place_order(req)
        d.executed = result.success
        d.message = result.message
        if result.success and result.is_live:
            state["orders_today"] = int(state["orders_today"]) + 1
        self._save_state(state)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _build_broker(live: bool) -> UpbitBroker:
    """CLI용 브로커 생성. 실전은 broker_factory의 이중 잠금을 반드시 통과해야 한다."""
    if live:
        from src.execution.broker_factory import get_broker

        broker = get_broker({}, dry_run=False)
        if not isinstance(broker, UpbitBroker):
            raise BrokerError(
                "실전 모드가 아닙니다. .env에 LIVE_TRADING=true 와 "
                "LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS 를 설정하세요."
            )
        return broker
    # dry-run: 주문 전송이 구조적으로 불가능(dry_run=True)하므로 키만 있으면 허용
    return UpbitBroker(
        access_key=os.getenv("UPBIT_ACCESS_KEY", "").strip(),
        secret_key=os.getenv("UPBIT_SECRET_KEY", "").strip(),
        dry_run=True,
    )


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 진입점. 기본은 dry-run, --live일 때만 실제 주문."""
    parser = argparse.ArgumentParser(description="업비트 BTC 현물 봇 — 일봉 돌파 전략 (기본 dry-run)")
    parser.add_argument("--live", action="store_true", help="실제 주문 실행 (LIVE_TRADING 이중 잠금 필요)")
    parser.add_argument("--fresh-only", action="store_true", help="진행 중인 추세 중간 진입 금지(신규 돌파만 매수)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from src.common.env_loader import load_environment

    load_environment()

    try:
        broker = _build_broker(args.live)
    except BrokerError as exc:
        logger.error(str(exc))
        return 2

    bot = LiveBtcBot(broker=broker, config=LiveBotConfig(fresh_signal_only=args.fresh_only))
    d = bot.run_once()
    mode = "DRY-RUN" if d.dry_run else "🔴 LIVE"
    tp = "—" if d.target_position is None else ("보유(1)" if d.target_position >= 0.5 else "현금(0)")
    print(f"[{mode}] {d.strategy} | 전략 목표={tp} | 마지막 종가={d.last_close or 0:,.0f}원")
    print(f"  현재가={d.price:,.0f}원 | 보유={d.qty:.8f} BTC | KRW={d.krw_cash:,.0f}원")
    print(f"  → action={d.action} executed={d.executed} | {d.error or d.message or d.reason}")
    return 1 if d.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
