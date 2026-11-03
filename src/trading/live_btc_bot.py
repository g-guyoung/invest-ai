# -*- coding: utf-8 -*-
"""
실전 비트코인 현물 봇 (업비트 KRW-BTC, 소액 전용).

목적: AI 분석 신호 + 하드 손절/익절 + RiskGuard로 BTC 현물을 자동 매매한다.
    기존 AutoTrader(100만원 가상 / 1개월 강제 소진 정책)와는 의도적으로 분리했다 —
    실전 자금에는 "기간 내 전액 소진" 같은 강제 매수 정책이 있으면 안 되기 때문이다.

한 번 실행(run_once) = 최대 주문 1건:
    1. 시세/잔고/평균매수가 조회 (업비트)
    2. 손절/익절 조건이면 AI 호출 없이 즉시 전량 매도
    3. 아니면 AI 분석 → BUY(미보유 시) / SELL(보유 시) / HOLD
    4. 매수는 RiskGuard(Kill Switch / 낙폭 / 일일 손실 / 주문 횟수) 통과 필수
    5. 결과를 data/live_bot_log.jsonl 에 감사 로그로 남김

운영 모드
---------
- 기본: dry-run (조회는 실제, 주문 전송은 안 함)
      python -m src.trading.live_btc_bot
- 실전: .env 에 LIVE_TRADING=true + LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS
      python -m src.trading.live_btc_bot --live
- 즉시 정지: data/KILL_SWITCH 파일 생성 (신규 매수 차단, 손절/익절 매도는 계속 허용)

자금 상한: capital_cap_krw(기본 5만원)까지만 봇 자금으로 간주한다. 계좌에 더 있어도
그 이상은 절대 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.execution.base_broker import BrokerError, OrderRequest, OrderSide
from src.execution.risk_guard import RiskGuard, RiskLimits
from src.execution.upbit_broker import CRYPTO_CATEGORY, MIN_ORDER_KRW, UpbitBroker

logger = logging.getLogger(__name__)

DATA_DIR = _PROJECT_ROOT / "data"


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
        yahoo_symbol: AI 분석용 가격 데이터 심볼.
        capital_cap_krw: 봇이 사용할 수 있는 최대 자금.
        min_confidence: 매매 실행 최소 신뢰도.
        max_risk_score: 매수 허용 최대 위험 점수.
        stop_loss_pct: 평균 매수가 대비 손절 비율 (0.05 = -5%).
        take_profit_pct: 평균 매수가 대비 익절 비율 (0.10 = +10%).
        fee_buffer: 수수료(0.05%) 여유 — 투입 금액에 곱한다.
        state_file: 일일 손실/주문 횟수 상태 파일.
        log_file: 감사 로그(JSON Lines) 파일.
        limits: RiskGuard 한도.
    """

    market: str = "KRW-BTC"
    symbol: str = "BTC"
    yahoo_symbol: str = "BTC-USD"
    capital_cap_krw: float = 50_000.0
    min_confidence: float = 0.65
    max_risk_score: float = 0.6
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    fee_buffer: float = 0.995
    state_file: Path = DATA_DIR / "live_bot_state.json"
    log_file: Path = DATA_DIR / "live_bot_log.jsonl"
    limits: RiskLimits = field(default_factory=_default_limits)


@dataclass
class BotDecision:
    """1회 실행 결과 (감사 로그 단위)."""

    timestamp: str = ""
    dry_run: bool = True
    action: str = "NONE"  # NONE | BUY | SELL
    reason: str = ""
    executed: bool = False
    message: str = ""
    error: Optional[str] = None
    price: float = 0.0
    qty: float = 0.0
    avg_buy_price: float = 0.0
    krw_cash: float = 0.0
    signal: Optional[str] = None
    confidence: Optional[float] = None
    risk_score: Optional[float] = None


class LiveBtcBot:
    """업비트 BTC 현물 실전 봇.

    Args:
        broker: UpbitBroker (dry_run 여부는 브로커가 결정).
        analyzer: BaseAnalyzer 구현체 (예: ClaudeAnalyzer).
        config: 봇 설정.
        risk_guard: RiskGuard (생략 시 config.limits로 생성).
        ohlcv_fn: 분석용 지표 포함 DataFrame을 돌려주는 함수 (테스트 주입용).
        market_context: AI 프롬프트에 넣을 시장 맥락 문자열.
        today_fn: 오늘 날짜 반환 함수 (테스트 주입용).
    """

    def __init__(
        self,
        broker: UpbitBroker,
        analyzer: Any,
        config: Optional[LiveBotConfig] = None,
        risk_guard: Optional[RiskGuard] = None,
        ohlcv_fn: Optional[Callable[[], Any]] = None,
        market_context: str = "",
        today_fn: Callable[[], date] = date.today,
    ) -> None:
        self.broker = broker
        self.analyzer = analyzer
        self.config = config or LiveBotConfig()
        self.risk_guard = risk_guard or RiskGuard(limits=self.config.limits)
        self._ohlcv_fn = ohlcv_fn or self._default_ohlcv
        self._market_context = market_context
        self._today_fn = today_fn

    # ------------------------------------------------------------------
    # 상태 파일 (일일 손실 기준선 / 주문 횟수)
    # ------------------------------------------------------------------

    def _load_state(self, current_total: float) -> dict[str, Any]:
        today = self._today_fn().isoformat()
        state: dict[str, Any] = {}
        try:
            state = json.loads(self.config.state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            state = {}
        if state.get("date") != today:
            state = {"date": today, "day_start_total": current_total, "orders_today": 0}
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def _append_log(self, decision: BotDecision) -> None:
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # 데이터/분석
    # ------------------------------------------------------------------

    def _default_ohlcv(self) -> Any:
        from src.engine.indicators import add_indicators
        from src.fetcher.fetcher_registry import FetcherRegistry

        df = FetcherRegistry.get_ohlcv(
            symbol=self.config.yahoo_symbol, market="yahoo", interval="1d", limit=100
        )
        if df is None or df.empty:
            raise BrokerError("가격 데이터를 가져오지 못했습니다.")
        return add_indicators(df)

    # ------------------------------------------------------------------
    # 핵심 로직
    # ------------------------------------------------------------------

    def run_once(self) -> BotDecision:
        """봇을 1회 실행한다 (최대 주문 1건). 예외를 던지지 않고 BotDecision에 기록한다."""
        cfg = self.config
        decision = BotDecision(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            dry_run=bool(getattr(self.broker, "dry_run", True)),
        )
        try:
            self._run(decision)
        except BrokerError as exc:
            decision.error = f"브로커 오류: {exc}"
            logger.error(decision.error)
        except Exception as exc:  # noqa: BLE001 - 봇 루프가 죽지 않도록
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
        holding_value = qty * price
        has_position = holding_value >= MIN_ORDER_KRW

        # 1) 하드 손절/익절 — AI 호출 없이, Kill Switch와 무관하게 허용
        if has_position and avg > 0:
            pnl = price / avg - 1.0
            if pnl <= -cfg.stop_loss_pct:
                self._sell(d, state, f"손절 {pnl:+.1%} (한도 -{cfg.stop_loss_pct:.0%})")
                return
            if pnl >= cfg.take_profit_pct:
                self._sell(d, state, f"익절 {pnl:+.1%} (목표 +{cfg.take_profit_pct:.0%})")
                return

        # 2) AI 분석
        df = self._ohlcv_fn()
        result = self.analyzer.analyze(df.tail(50), symbol=cfg.yahoo_symbol, market_context=self._market_context)
        d.signal = getattr(result.signal, "value", str(result.signal))
        d.confidence, d.risk_score = result.confidence, result.risk_score

        if result.confidence < cfg.min_confidence:
            d.message = f"신뢰도 부족({result.confidence:.2f} < {cfg.min_confidence:.2f}) — 관망"
            self._save_state(state)
            return

        if d.signal == "SELL":
            if not has_position:
                d.message = "SELL 신호지만 보유 중이 아니라 생략"
            else:
                self._sell(d, state, f"AI 매도 신호: {result.reason}")
                return
        elif d.signal == "BUY":
            if has_position:
                d.message = "이미 보유 중 — 추가 매수 없음"
            elif result.risk_score > cfg.max_risk_score:
                d.message = f"위험도 과다({result.risk_score:.2f} > {cfg.max_risk_score:.2f}) — 매수 보류"
            else:
                self._buy(d, state, investable, current_total, result.confidence, result.reason)
                return
        else:
            d.message = "HOLD 신호 — 매매 없음"
        self._save_state(state)

    def _buy(
        self, d: BotDecision, state: dict[str, Any], investable: float,
        current_total: float, confidence: float, reason: str,
    ) -> None:
        cfg = self.config
        # 신뢰도 0.65→현금의 50%, 1.0→100% 선형 (수수료 여유 적용)
        span = max(1e-9, 1.0 - cfg.min_confidence)
        frac = min(1.0, 0.5 + 0.5 * max(0.0, confidence - cfg.min_confidence) / span)
        amount = float(int(investable * frac * cfg.fee_buffer))

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

        d.action, d.reason = "BUY", reason
        req = OrderRequest(
            category=CRYPTO_CATEGORY, symbol=cfg.symbol, name="비트코인", side=OrderSide.BUY,
            price=d.price, amount=amount, source="AUTO_AI",
            ai_signal=d.signal, ai_confidence=d.confidence, ai_reason=reason,
        )
        self._execute(d, state, req)

    def _sell(self, d: BotDecision, state: dict[str, Any], reason: str) -> None:
        cfg = self.config
        d.action, d.reason = "SELL", reason
        req = OrderRequest(
            category=CRYPTO_CATEGORY, symbol=cfg.symbol, name="비트코인", side=OrderSide.SELL,
            price=d.price, amount=0.0, source="AUTO_AI",
            ai_signal=d.signal, ai_confidence=d.confidence, ai_reason=reason,
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
    parser = argparse.ArgumentParser(description="업비트 BTC 현물 실전 봇 (기본 dry-run)")
    parser.add_argument("--live", action="store_true", help="실제 주문 실행 (LIVE_TRADING 이중 잠금 필요)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from src.common.env_loader import load_environment

    load_environment()

    from src.engine.claude_analyzer import ClaudeAnalyzer
    from src.engine.market_profiles import get_profile

    try:
        broker = _build_broker(args.live)
    except BrokerError as exc:
        logger.error(str(exc))
        return 2

    bot = LiveBtcBot(
        broker=broker,
        analyzer=ClaudeAnalyzer(),
        market_context=get_profile(CRYPTO_CATEGORY).prompt_context,
    )
    d = bot.run_once()
    mode = "DRY-RUN" if d.dry_run else "🔴 LIVE"
    print(f"[{mode}] action={d.action} executed={d.executed} signal={d.signal} "
          f"conf={d.confidence} price={d.price:,.0f} qty={d.qty:.8f} cash={d.krw_cash:,.0f}")
    print(f"  → {d.error or d.message or d.reason}")
    return 1 if d.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
