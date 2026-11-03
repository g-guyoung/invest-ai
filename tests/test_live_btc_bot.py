# -*- coding: utf-8 -*-
"""LiveBtcBot 단위 테스트 — 진짜 DonchianBreakout + 가짜 브로커 (네트워크/실돈 없음)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.execution.base_broker import BrokerError, OrderResult, OrderSide
from src.execution.risk_guard import RiskGuard
from src.strategy.rule_strategies import DonchianBreakout
from src.trading.live_btc_bot import LiveBotConfig, LiveBtcBot, drop_incomplete_candle


# ---------- 합성 가격 데이터 (Donchian 20/10 기준) ----------

def frame(closes: list[float]) -> pd.DataFrame:
    s = pd.Series(closes, dtype=float)
    return pd.DataFrame({"open": s, "high": s * 1.01, "low": s * 0.99, "close": s, "volume": 1.0})


UPTREND = frame([100.0] * 30 + [100.0 + 2 * i for i in range(1, 20)])  # 돌파 후 상승 지속 → 목표 1 (진행 중 추세)
FRESH = frame([100.0] * 30 + [103.0])                                   # 마지막 봉에서 막 돌파 → 목표 1 (신규)
FLAT = frame([100.0] * 40)                                              # 돌파 없음 → 목표 0
EXITED = frame([100.0] * 30 + [100.0 + 2 * i for i in range(1, 20)] + [60.0])  # 상승 후 10일 저가 이탈 → 목표 0


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


def mk(tmp_path: Path, df=UPTREND, broker=None, kill: bool = False, **cfg_kw):
    cfg = LiveBotConfig(state_file=tmp_path / "s.json", log_file=tmp_path / "l.jsonl", **cfg_kw)
    ks = tmp_path / "KILL"
    if kill:
        ks.write_text("x")
    holder = {"df": df}
    bot = LiveBtcBot(
        broker=broker or FakeBroker(), strategy=DonchianBreakout(entry=20, exit=10), config=cfg,
        risk_guard=RiskGuard(limits=cfg.limits, kill_switch_file=ks),
        candles_fn=lambda: holder["df"], today_fn=lambda: date(2026, 11, 3),
    )
    bot.holder = holder  # 테스트에서 시세 데이터를 바꿔치기하기 위함
    return bot


# ---------- 전략 신호 ----------

def test_synthetic_frames_give_expected_targets():
    s = DonchianBreakout(entry=20, exit=10)
    assert s.generate_positions(UPTREND).iloc[-1] == 1.0
    assert s.generate_positions(FRESH).iloc[-1] == 1.0 and s.generate_positions(FRESH).iloc[-2] == 0.0
    assert s.generate_positions(FLAT).iloc[-1] == 0.0
    assert s.generate_positions(EXITED).iloc[-1] == 0.0


def test_default_strategy_is_validated_donchian_20_10(tmp_path):
    bot = LiveBtcBot(broker=FakeBroker(), config=LiveBotConfig(state_file=tmp_path / "s", log_file=tmp_path / "l"),
                     candles_fn=lambda: FLAT)
    assert bot.strategy.params == {"entry": 20, "exit": 10}


# ---------- 매수 ----------

def test_buy_when_signal_on_and_flat(tmp_path):
    bot = mk(tmp_path)
    d = bot.run_once()
    assert d.action == "BUY" and d.executed and d.target_position == 1.0
    req = bot.broker.orders[0]
    assert req.side == OrderSide.BUY and 5_000 <= req.amount <= 50_000 * 0.995


def test_capital_cap_limits_spend_even_if_account_is_bigger(tmp_path):
    bot = mk(tmp_path, broker=FakeBroker(cash=5_000_000.0))
    bot.run_once()
    assert bot.broker.orders[0].amount <= 50_000


def test_no_buy_in_cash_zone(tmp_path):
    bot = mk(tmp_path, df=FLAT)
    d = bot.run_once()
    assert d.action == "NONE" and d.target_position == 0.0 and not bot.broker.orders


def test_no_double_buy_when_already_holding(tmp_path):
    broker = FakeBroker(qty=0.0004, avg=100_000_000.0, cash=10_000.0)
    d = mk(tmp_path, broker=broker).run_once()
    assert d.action == "NONE" and not broker.orders


def test_fresh_signal_only_skips_mid_trend_but_takes_new_breakout(tmp_path):
    assert mk(tmp_path, df=UPTREND, fresh_signal_only=True).run_once().action == "NONE"
    (tmp_path / "x").mkdir()
    bot = mk(tmp_path / "x", df=FRESH, fresh_signal_only=True)
    assert bot.run_once().action == "BUY"


# ---------- 매도 ----------

def test_strategy_exit_sells_all(tmp_path):
    broker = FakeBroker(qty=0.0005, avg=100_000_000.0, cash=0.0)
    d = mk(tmp_path, df=EXITED, broker=broker).run_once()
    assert d.action == "SELL" and "전략 청산" in d.reason and d.executed
    assert broker.orders[0].side == OrderSide.SELL


def test_exit_signal_without_position_does_nothing(tmp_path):
    assert mk(tmp_path, df=EXITED).run_once().action == "NONE"


# ---------- 비상 손절 + 재진입 잠금 ----------

def test_emergency_stop_sells_and_locks_reentry_until_strategy_exits(tmp_path):
    broker = FakeBroker(price=84_000_000.0, qty=0.0005, avg=100_000_000.0, cash=0.0)  # -16%
    bot = mk(tmp_path, df=UPTREND, broker=broker)
    d = bot.run_once()
    assert d.action == "SELL" and "비상 손절" in d.reason

    # 매도 후: 현금 상태, 전략은 여전히 '보유' → 재진입 잠금으로 매수 금지
    broker.qty, broker.cash = 0.0, 42_000.0
    d2 = bot.run_once()
    assert d2.action == "NONE" and "잠금" in d2.message

    # 전략이 청산 신호(0)를 내면 잠금 해제 → 이후 새 진입 신호에서 다시 매수 가능
    bot.holder["df"] = FLAT
    bot.run_once()
    bot.holder["df"] = UPTREND
    assert bot.run_once().action == "BUY"


def test_emergency_stop_works_even_with_kill_switch(tmp_path):
    broker = FakeBroker(price=84_000_000.0, qty=0.0005, avg=100_000_000.0, cash=0.0)
    d = mk(tmp_path, broker=broker, kill=True).run_once()
    assert d.action == "SELL" and d.executed


# ---------- RiskGuard ----------

def test_kill_switch_blocks_buy(tmp_path):
    bot = mk(tmp_path, kill=True)
    d = bot.run_once()
    assert not bot.broker.orders and "KILL" in d.message


def test_kill_switch_still_allows_strategy_exit(tmp_path):
    broker = FakeBroker(qty=0.0005, avg=100_000_000.0, cash=0.0)
    d = mk(tmp_path, df=EXITED, broker=broker, kill=True).run_once()
    assert d.action == "SELL" and d.executed


def test_daily_order_limit_enforced(tmp_path):
    bot = mk(tmp_path)
    (tmp_path / "s.json").write_text(json.dumps({"date": "2026-11-03", "day_start_total": 50_000.0, "orders_today": 4, "stop_lock": False}))
    d = bot.run_once()
    assert not bot.broker.orders and "한도" in d.message


def test_daily_loss_limit_blocks_buy(tmp_path):
    bot = mk(tmp_path, broker=FakeBroker(cash=45_000.0))
    (tmp_path / "s.json").write_text(json.dumps({"date": "2026-11-03", "day_start_total": 50_000.0, "orders_today": 0, "stop_lock": False}))
    d = bot.run_once()
    assert not bot.broker.orders and "손실" in d.message


# ---------- 로그/오류/유틸 ----------

def test_dry_run_does_not_count_orders_and_logs_without_secrets(tmp_path):
    bot = mk(tmp_path, broker=FakeBroker(dry_run=True))
    d = bot.run_once()
    assert d.dry_run and d.executed
    assert json.loads((tmp_path / "s.json").read_text())["orders_today"] == 0
    line = json.loads((tmp_path / "l.jsonl").read_text().splitlines()[-1])
    assert line["action"] == "BUY" and line["strategy"].startswith("돌파")
    assert "secret" not in json.dumps(line).lower()


def test_broker_error_is_captured_not_raised(tmp_path):
    class Boom(FakeBroker):
        def get_price(self, market): raise BrokerError("net down")

    d = mk(tmp_path, broker=Boom()).run_once()
    assert d.error and "net down" in d.error


def test_drop_incomplete_candle_removes_today_utc_bar():
    df = pd.DataFrame({
        "open_time": pd.to_datetime(["2026-11-01", "2026-11-02", "2026-11-03"]),
        "close": [1.0, 2.0, 3.0],
    })
    out = drop_incomplete_candle(df, now_utc=datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc))
    assert out["close"].tolist() == [1.0, 2.0]
