# -*- coding: utf-8 -*-
"""LiveBtcBot 단위 테스트 (가짜 브로커/분석기 — 네트워크/실돈 없음)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from src.execution.base_broker import OrderResult, OrderSide
from src.execution.risk_guard import RiskGuard
from src.trading.live_btc_bot import LiveBotConfig, LiveBtcBot


class FakeBroker:
    def __init__(self, price=100_000_000.0, qty=0.0, avg=0.0, cash=50_000.0, dry_run=False) -> None:
        self.price, self.qty, self.avg, self.cash, self.dry_run = price, qty, avg, cash, dry_run
        self.orders: list = []

    def get_price(self, market: str) -> float: return self.price
    def get_position(self, symbol: str): return (self.qty, self.avg)
    def get_cash(self, category: str) -> float: return self.cash

    def place_order(self, req):
        self.orders.append(req)
        return OrderResult(True, "ok", req, is_live=not self.dry_run)


class FakeAnalyzer:
    def __init__(self, signal="BUY", confidence=0.9, risk=0.3) -> None:
        self.r = SimpleNamespace(signal=SimpleNamespace(value=signal), confidence=confidence, risk_score=risk, reason="test")
        self.calls = 0

    def analyze(self, df, symbol, market_context="") -> Any:
        self.calls += 1
        return self.r


def mk(tmp_path: Path, broker=None, analyzer=None, kill: bool = False, **cfg_kw):
    cfg = LiveBotConfig(state_file=tmp_path / "s.json", log_file=tmp_path / "l.jsonl", **cfg_kw)
    ks = tmp_path / "KILL"
    if kill:
        ks.write_text("x")
    bot = LiveBtcBot(
        broker=broker or FakeBroker(), analyzer=analyzer or FakeAnalyzer(), config=cfg,
        risk_guard=RiskGuard(limits=cfg.limits, kill_switch_file=ks),
        ohlcv_fn=lambda: pd.DataFrame({"close": [1.0] * 60}), today_fn=lambda: date(2026, 11, 3),
    )
    return bot


def test_buy_when_flat_and_confident(tmp_path):
    bot = mk(tmp_path)
    d = bot.run_once()
    assert d.action == "BUY" and d.executed
    req = bot.broker.orders[0]
    assert req.side == OrderSide.BUY and 5_000 <= req.amount <= 50_000 * 0.995


def test_capital_cap_limits_spend_even_if_account_is_bigger(tmp_path):
    bot = mk(tmp_path, broker=FakeBroker(cash=5_000_000.0))
    bot.run_once()
    assert bot.broker.orders[0].amount <= 50_000


def test_low_confidence_holds(tmp_path):
    bot = mk(tmp_path, analyzer=FakeAnalyzer(confidence=0.5))
    d = bot.run_once()
    assert d.action == "NONE" and not bot.broker.orders


def test_high_risk_blocks_buy(tmp_path):
    bot = mk(tmp_path, analyzer=FakeAnalyzer(risk=0.9))
    assert bot.run_once().action == "NONE" and not bot.broker.orders


def test_kill_switch_blocks_buy(tmp_path):
    bot = mk(tmp_path, kill=True)
    d = bot.run_once()
    assert not bot.broker.orders and "KILL" in d.message


def test_stop_loss_sells_without_calling_ai_even_with_kill_switch(tmp_path):
    broker = FakeBroker(price=94_000_000.0, qty=0.0005, avg=100_000_000.0, cash=0.0)  # -6%
    ai = FakeAnalyzer()
    bot = mk(tmp_path, broker=broker, analyzer=ai, kill=True)
    d = bot.run_once()
    assert d.action == "SELL" and "손절" in d.reason and ai.calls == 0
    assert broker.orders[0].side == OrderSide.SELL


def test_take_profit_sells(tmp_path):
    broker = FakeBroker(price=111_000_000.0, qty=0.0005, avg=100_000_000.0, cash=0.0)  # +11%
    d = mk(tmp_path, broker=broker).run_once()
    assert d.action == "SELL" and "익절" in d.reason


def test_ai_sell_signal_when_holding(tmp_path):
    broker = FakeBroker(qty=0.0005, avg=100_000_000.0, cash=0.0)  # 평가 5만원, 손익 0%
    d = mk(tmp_path, broker=broker, analyzer=FakeAnalyzer(signal="SELL")).run_once()
    assert d.action == "SELL" and d.executed


def test_no_double_buy_when_already_holding(tmp_path):
    broker = FakeBroker(qty=0.0004, avg=100_000_000.0, cash=10_000.0)
    d = mk(tmp_path, broker=broker).run_once()
    assert d.action == "NONE" and not broker.orders


def test_sell_signal_without_position_is_ignored(tmp_path):
    bot = mk(tmp_path, analyzer=FakeAnalyzer(signal="SELL"))
    assert bot.run_once().action == "NONE" and not bot.broker.orders


def test_daily_order_limit_enforced_across_runs(tmp_path):
    bot = mk(tmp_path)
    (tmp_path / "s.json").write_text(json.dumps({"date": "2026-11-03", "day_start_total": 50_000.0, "orders_today": 4}))
    d = bot.run_once()
    assert not bot.broker.orders and "한도" in d.message


def test_daily_loss_limit_blocks_buy(tmp_path):
    # 하루 시작 총자산 50,000 → 현재 45,000 (-10% > 5%)
    bot = mk(tmp_path, broker=FakeBroker(cash=45_000.0))
    (tmp_path / "s.json").write_text(json.dumps({"date": "2026-11-03", "day_start_total": 50_000.0, "orders_today": 0}))
    d = bot.run_once()
    assert not bot.broker.orders and "손실" in d.message


def test_dry_run_does_not_count_orders_and_logs(tmp_path):
    bot = mk(tmp_path, broker=FakeBroker(dry_run=True))
    d = bot.run_once()
    assert d.dry_run and d.executed
    assert json.loads((tmp_path / "s.json").read_text())["orders_today"] == 0
    line = json.loads((tmp_path / "l.jsonl").read_text().splitlines()[-1])
    assert line["action"] == "BUY" and "key" not in json.dumps(line).lower()


def test_broker_error_is_captured_not_raised(tmp_path):
    from src.execution.base_broker import BrokerError

    class Boom(FakeBroker):
        def get_price(self, market): raise BrokerError("net down")

    d = mk(tmp_path, broker=Boom()).run_once()
    assert d.error and "net down" in d.error
