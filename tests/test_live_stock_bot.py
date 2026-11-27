# -*- coding: utf-8 -*-
"""LiveStockBot 단위 테스트 (가짜 브로커/전략 — 네트워크/실돈 없음)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import pytest

from src.execution.base_broker import BaseBroker, OrderRequest, OrderResult, OrderSide
from src.execution.market_hours import KR_CATEGORY
from src.execution.risk_guard import RiskGuard
from src.strategy.base_strategy import BaseStrategy
from src.trading.live_stock_bot import (
    LiveStockBot,
    StockMarketConfig,
    default_limits,
    load_market_config,
)

KR_OPEN = datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc)
CLOSED = datetime(2026, 11, 28, 1, 0, tzinfo=timezone.utc)


class FixedStrategy(BaseStrategy):
    """마지막 두 봉의 목표 포지션을 고정해서 돌려주는 테스트 전략."""

    name = "고정"
    default_params = {"prev": 0.0, "last": 1.0}

    def _positions(self, df: pd.DataFrame) -> pd.Series:
        s = pd.Series(0.0, index=df.index)
        s.iloc[-2], s.iloc[-1] = self.params["prev"], self.params["last"]
        return s


class FakeBroker(BaseBroker):
    def __init__(self, cash: float = 300_000, positions: Optional[dict] = None,
                 prices: Optional[dict] = None, dry_run: bool = False, success: bool = True) -> None:
        self.cash, self.dry_run, self.success = cash, dry_run, success
        self.positions = positions or {}
        self.prices = prices or {"005930": 70_000.0, "000660": 100_000.0}
        self.orders: list[OrderRequest] = []
        self.mode_label = "FAKE"

    def place_order(self, request: OrderRequest) -> OrderResult:
        self.orders.append(request)
        return OrderResult(success=self.success, message="ok" if self.success else "rejected",
                           request=request, order_id="1" if self.success else None)

    def get_cash(self, category: str) -> float:
        return self.cash

    def get_holding_qty(self, category: str, symbol: str) -> float:
        return self.positions.get(symbol, (0.0, 0.0))[0]

    def get_position(self, category: str, symbol: str) -> tuple[float, float]:
        return self.positions.get(symbol, (0.0, 0.0))

    def get_price(self, category: str, symbol: str) -> float:
        return self.prices[symbol]


def candles(category: str, symbol: str) -> pd.DataFrame:
    n = 30
    return pd.DataFrame({
        "open_time": pd.date_range("2026-10-01", periods=n), "open": [1.0] * n, "high": [1.0] * n,
        "low": [1.0] * n, "close": [1.0] * n, "volume": [1.0] * n,
    })


def market(symbols: tuple[str, ...] = ("005930", "000660"), cap: float = 300_000) -> StockMarketConfig:
    return StockMarketConfig(key="kr", category=KR_CATEGORY, symbols=symbols, capital_cap=cap,
                             currency="원", limits=default_limits(1_000.0))


def make_bot(tmp_path: Path, broker: FakeBroker, prev: float = 0.0, last: float = 1.0,
             now: datetime = KR_OPEN, mk: Optional[StockMarketConfig] = None, **kw: Any) -> LiveStockBot:
    mk = mk or market()
    return LiveStockBot(
        broker=broker, market=mk, strategy=FixedStrategy(prev=prev, last=last),
        risk_guard=RiskGuard(limits=mk.limits, kill_switch_file=tmp_path / "KILL"),
        candles_fn=candles, today_fn=lambda: date(2026, 11, 27), now_fn=lambda: now,
        state_file=tmp_path / "state.json", log_file=tmp_path / "log.jsonl", **kw,
    )


def test_buys_each_symbol_with_equal_allocation(tmp_path: Path) -> None:
    broker = FakeBroker()
    decisions = make_bot(tmp_path, broker).run_once()
    assert [o.side for o in broker.orders] == [OrderSide.BUY, OrderSide.BUY]
    assert broker.orders[0].amount == pytest.approx(150_000 * 0.995)
    assert all(d.executed for d in decisions)
    assert json.loads((tmp_path / "state.json").read_text())["orders_today"] == 2


def test_capital_cap_limits_spend_even_with_more_cash(tmp_path: Path) -> None:
    broker = FakeBroker(cash=10_000_000)
    make_bot(tmp_path, broker).run_once()
    assert sum(o.amount for o in broker.orders) <= 300_000


def test_existing_holdings_reduce_investable(tmp_path: Path) -> None:
    broker = FakeBroker(positions={"005930": (2.0, 70_000.0)})  # 원가 14만 → 남은 16만
    make_bot(tmp_path, broker).run_once()
    assert len(broker.orders) == 1 and broker.orders[0].symbol == "000660"
    assert broker.orders[0].amount == pytest.approx(150_000 * 0.995)


def test_exit_signal_sells_position(tmp_path: Path) -> None:
    broker = FakeBroker(positions={"005930": (2.0, 70_000.0)})
    make_bot(tmp_path, broker, prev=1.0, last=0.0).run_once()
    assert [(o.symbol, o.side, o.amount) for o in broker.orders] == [("005930", OrderSide.SELL, 0.0)]


def test_emergency_stop_sells_and_locks(tmp_path: Path) -> None:
    broker = FakeBroker(positions={"005930": (2.0, 100_000.0)}, prices={"005930": 80_000.0})
    bot = make_bot(tmp_path, broker, mk=market(("005930",)))
    bot.run_once()
    assert broker.orders[-1].side == OrderSide.SELL
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["stop_lock"]["005930"] is True

    # 다음날: 보유 없음 + 전략은 여전히 보유 신호 → 잠금 때문에 매수 안 함
    broker2 = FakeBroker(prices={"005930": 80_000.0})
    bot2 = make_bot(tmp_path, broker2, mk=market(("005930",)))
    bot2._today_fn = lambda: date(2026, 11, 30)
    decisions = bot2.run_once()
    assert broker2.orders == [] and "재진입 잠금" in decisions[0].message


def test_lock_released_on_exit_signal(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"date": "2026-11-27", "day_start_total": 300000,
                                                     "orders_today": 0, "stop_lock": {"005930": True}}))
    broker = FakeBroker()
    make_bot(tmp_path, broker, last=0.0, mk=market(("005930",))).run_once()
    assert json.loads((tmp_path / "state.json").read_text())["stop_lock"]["005930"] is False


def test_kill_switch_blocks_buy(tmp_path: Path) -> None:
    (tmp_path / "KILL").touch()
    broker = FakeBroker()
    decisions = make_bot(tmp_path, broker).run_once()
    assert broker.orders == [] and "KILL SWITCH" in decisions[0].message


def test_kill_switch_still_allows_sell(tmp_path: Path) -> None:
    (tmp_path / "KILL").touch()
    broker = FakeBroker(positions={"005930": (2.0, 70_000.0)})
    make_bot(tmp_path, broker, last=0.0).run_once()
    assert [o.side for o in broker.orders] == [OrderSide.SELL]


def test_daily_order_limit(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"date": "2026-11-27", "day_start_total": 300000,
                                                     "orders_today": 6, "stop_lock": {}}))
    broker = FakeBroker()
    decisions = make_bot(tmp_path, broker).run_once()
    assert broker.orders == [] and "주문 횟수" in decisions[0].message


def test_fresh_signal_only_skips_ongoing_trend(tmp_path: Path) -> None:
    broker = FakeBroker()
    make_bot(tmp_path, broker, prev=1.0, last=1.0, fresh_signal_only=True).run_once()
    assert broker.orders == []


def test_market_closed_skips_when_live(tmp_path: Path) -> None:
    broker = FakeBroker()
    decisions = make_bot(tmp_path, broker, now=CLOSED).run_once()
    assert broker.orders == [] and "정규장" in decisions[0].message


def test_market_closed_dry_run_still_validates(tmp_path: Path) -> None:
    broker = FakeBroker(dry_run=True)
    make_bot(tmp_path, broker, now=CLOSED).run_once()
    assert len(broker.orders) == 2
    assert not (tmp_path / "state.json").exists() or \
        json.loads((tmp_path / "state.json").read_text())["orders_today"] == 0  # dry-run은 횟수 미집계


def test_one_symbol_error_does_not_stop_others(tmp_path: Path) -> None:
    broker = FakeBroker()

    def price(category: str, symbol: str) -> float:
        if symbol == "000660":
            raise ValueError("시세 없음")
        return 70_000.0

    broker.get_price = price  # type: ignore[method-assign]
    decisions = make_bot(tmp_path, broker).run_once()
    assert len(broker.orders) == 1
    assert any(d.error for d in decisions)


def test_cash_failure_recorded_not_raised(tmp_path: Path) -> None:
    from src.execution.base_broker import BrokerError

    broker = FakeBroker()

    def boom(category: str) -> float:
        raise BrokerError("down")

    broker.get_cash = boom  # type: ignore[method-assign]
    decisions = make_bot(tmp_path, broker).run_once()
    assert decisions[0].error and "down" in decisions[0].error
    assert (tmp_path / "log.jsonl").exists()


def test_rejected_order_does_not_count(tmp_path: Path) -> None:
    broker = FakeBroker(success=False)
    make_bot(tmp_path, broker).run_once()
    assert json.loads((tmp_path / "state.json").read_text())["orders_today"] == 0


def test_audit_log_written(tmp_path: Path) -> None:
    make_bot(tmp_path, FakeBroker()).run_once()
    lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["action"] == "BUY"


def test_empty_symbols_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_bot(tmp_path, FakeBroker(), mk=market(()))


def test_load_market_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_US_MODE", "list")
    monkeypatch.setenv("KIS_US_SYMBOLS", "aapl, nvda")
    monkeypatch.setenv("KIS_US_CAPITAL_USD", "2,000")
    cfg = load_market_config("us")
    assert cfg.symbols == ("AAPL", "NVDA") and cfg.capital_cap == 2000 and not cfg.is_universe
    with pytest.raises(ValueError):
        load_market_config("jp")


# ----------------------------------------------------------------------
# 전 종목(universe) 모드
# ----------------------------------------------------------------------


def uni_market(max_positions: int = 2, cap: float = 300_000) -> StockMarketConfig:
    return StockMarketConfig(key="kr", category=KR_CATEGORY, symbols=(), capital_cap=cap, currency="원",
                             limits=default_limits(1_000.0), mode="universe", max_positions=max_positions)


def uni_bot(tmp_path: Path, broker: FakeBroker, candidates: Any, last: float = 1.0, max_positions: int = 2) -> LiveStockBot:
    fn = candidates if callable(candidates) else (lambda: list(candidates))
    return make_bot(tmp_path, broker, last=last, mk=uni_market(max_positions), candidates_fn=fn)


def test_universe_buys_screened_candidates_with_slot_budget(tmp_path: Path) -> None:
    broker = FakeBroker(prices={"005930": 70_000.0, "000660": 100_000.0, "035420": 50_000.0})
    uni_bot(tmp_path, broker, ["005930", "000660", "035420"]).run_once()
    assert [o.symbol for o in broker.orders] == ["005930", "000660"]  # 최대 2종목
    assert broker.orders[0].amount == pytest.approx(150_000 * 0.995)  # 300,000 ÷ 2
    assert json.loads((tmp_path / "state.json").read_text())["owned"] == ["005930", "000660"]


def test_universe_skips_manual_holdings(tmp_path: Path) -> None:
    broker = FakeBroker(positions={"005930": (5.0, 60_000.0)})
    decisions = uni_bot(tmp_path, broker, ["005930"], last=0.0).run_once()
    assert broker.orders == []  # 청산 신호여도 봇이 산 종목이 아니면 팔지 않음
    assert "수동 투자" in decisions[0].message


def test_universe_manages_owned_even_if_not_screened(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"date": "2026-11-26", "day_start_total": 1,
                                                     "orders_today": 0, "stop_lock": {}, "owned": ["000660"]}))
    broker = FakeBroker(positions={"000660": (1.0, 100_000.0)})
    uni_bot(tmp_path, broker, [], last=0.0).run_once()
    assert [(o.symbol, o.side) for o in broker.orders] == [("000660", OrderSide.SELL)]
    assert json.loads((tmp_path / "state.json").read_text())["owned"] == []


def test_universe_screening_failure_still_sells(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"owned": ["000660"]}))
    broker = FakeBroker(positions={"000660": (1.0, 100_000.0)})

    def boom() -> list[str]:
        raise RuntimeError("network down")

    decisions = uni_bot(tmp_path, broker, boom, last=0.0).run_once()
    assert any(d.error and "스크리닝 실패" in d.error for d in decisions)
    assert [o.side for o in broker.orders] == [OrderSide.SELL]


def test_universe_max_positions_counts_existing(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(json.dumps({"owned": ["000660"]}))
    broker = FakeBroker(positions={"000660": (1.0, 100_000.0)}, prices={"000660": 100_000.0, "005930": 70_000.0})
    decisions = uni_bot(tmp_path, broker, ["005930"], max_positions=1).run_once()
    assert broker.orders == []
    assert any("최대 보유 종목 수" in d.message for d in decisions)


def test_universe_no_candidates_no_owned(tmp_path: Path) -> None:
    decisions = uni_bot(tmp_path, FakeBroker(), []).run_once()
    assert "후보가 없고" in decisions[0].message


def test_universe_mode_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["KIS_KR_MODE", "KIS_KR_SYMBOLS", "KIS_KR_MAX_POSITIONS"]:
        monkeypatch.delenv(name, raising=False)
    cfg = load_market_config("kr")
    assert cfg.is_universe and cfg.max_positions == 5 and cfg.per_symbol_budget == 60_000
    assert cfg.min_traded_value == 1_000_000_000


def test_list_mode_requires_symbols(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KIS_KR_MODE", "list")
    monkeypatch.delenv("KIS_KR_SYMBOLS", raising=False)
    cfg = load_market_config("kr")
    with pytest.raises(ValueError, match="list 모드"):
        make_bot(tmp_path, FakeBroker(), mk=cfg)


def test_bad_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_US_MODE", "all")
    with pytest.raises(ValueError, match="universe 또는 list"):
        load_market_config("us")
