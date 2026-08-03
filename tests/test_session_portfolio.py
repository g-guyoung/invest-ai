# -*- coding: utf-8 -*-
"""
src/portfolio/session_portfolio.py 에 대한 pytest 테스트.

buy/sell/get_summary의 계산 로직 자체(정상/실패/엣지 케이스)와,
매매 체결 시 저장소(repository)의 record_trade가 올바른 인자로
호출되는지(Repository Pattern 연동)를 함께 검증한다.
"""

from __future__ import annotations

import pytest

from src.portfolio import repository_factory, session_portfolio as sp


@pytest.fixture(autouse=True)
def _reset_factory_cache():
    repository_factory.reset_cache()
    yield
    repository_factory.reset_cache()


@pytest.fixture(autouse=True)
def _force_session_repository(monkeypatch):
    """Supabase 키가 우연히 환경에 남아있어도 세션 저장소만 쓰도록 강제한다."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


CATEGORY = "🇰🇷 한국 주식"


# ── 정상 케이스 ──────────────────────────────────────────────
def test_buy_success_deducts_cash_and_adds_holding():
    state: dict = {}

    ok, msg = sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)

    assert ok is True
    book = state["portfolio"][CATEGORY]
    assert book["cash"] == pytest.approx(300_000.0)
    assert book["holdings"]["005930"]["qty"] == pytest.approx(10.0)
    assert book["holdings"]["005930"]["avg_price"] == pytest.approx(70000.0)
    assert len(book["history"]) == 1
    assert book["history"][0]["type"] == "BUY"


def test_buy_twice_averages_price():
    state: dict = {}
    sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)  # 10주 @ 70000

    ok, _ = sp.buy(state, CATEGORY, "005930", "삼성전자", 90000.0, 90000.0)  # +1주 @ 90000

    holding = state["portfolio"][CATEGORY]["holdings"]["005930"]
    assert ok is True
    assert holding["qty"] == pytest.approx(11.0)
    assert holding["avg_price"] == pytest.approx((700000.0 + 90000.0) / 11.0)


def test_sell_partial_reduces_qty_and_keeps_holding():
    state: dict = {}
    sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)  # 10주

    ok, msg = sp.sell(state, CATEGORY, "005930", 80000.0, qty=4.0)

    book = state["portfolio"][CATEGORY]
    assert ok is True
    assert book["holdings"]["005930"]["qty"] == pytest.approx(6.0)
    assert book["cash"] == pytest.approx(300_000.0 + 4 * 80000.0)


def test_sell_all_removes_holding():
    state: dict = {}
    sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)

    ok, msg = sp.sell(state, CATEGORY, "005930", 80000.0)

    assert ok is True
    assert "005930" not in state["portfolio"][CATEGORY]["holdings"]


# ── 실패 케이스 ──────────────────────────────────────────────
def test_buy_fails_when_amount_exceeds_cash():
    state: dict = {}

    ok, msg = sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 10_000_000.0)

    assert ok is False
    assert "현금이 부족" in msg
    assert state["portfolio"][CATEGORY]["cash"] == sp.INITIAL_BALANCE


def test_buy_fails_when_price_is_zero():
    state: dict = {}

    ok, msg = sp.buy(state, CATEGORY, "005930", "삼성전자", 0.0, 100000.0)

    assert ok is False
    assert "가격" in msg


def test_buy_fails_when_amount_is_negative():
    state: dict = {}

    ok, msg = sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, -1.0)

    assert ok is False


def test_sell_fails_when_not_holding():
    state: dict = {}

    ok, msg = sp.sell(state, CATEGORY, "005930", 70000.0)

    assert ok is False
    assert "보유하고" in msg


def test_sell_fails_when_qty_exceeds_holding():
    state: dict = {}
    sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)  # 10주

    ok, msg = sp.sell(state, CATEGORY, "005930", 70000.0, qty=100.0)

    assert ok is False
    assert "보유 수량보다" in msg


# ── 엣지 케이스 / 저장소 연동 ────────────────────────────────
def test_get_summary_computes_pnl():
    state: dict = {}
    sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 700000.0)

    summary = sp.get_summary(state, CATEGORY, current_prices={"005930": 77000.0})

    # 보유 10주 * (77000-70000) = 70000 이익, 현금은 그대로 300000
    assert summary["pnl"] == pytest.approx(70000.0)
    assert summary["holdings"][0]["손익"] == pytest.approx(70000.0)


class _SpyRepository:
    """buy/sell이 저장소 훅을 올바른 인자로 호출하는지 검증하기 위한 스파이."""

    def __init__(self):
        self.calls = []

    def load_into(self, session_state):
        if "portfolio" not in session_state:
            session_state["portfolio"] = {
                CATEGORY: {"cash": sp.INITIAL_BALANCE, "holdings": {}, "history": []}
            }

    def record_trade(self, category, symbol, name, trade_type, qty, price, amount, book,
                      source="MANUAL", ai_signal=None, ai_confidence=None, ai_reason=None):
        self.calls.append({
            "category": category, "symbol": symbol, "trade_type": trade_type,
            "source": source, "ai_signal": ai_signal, "ai_confidence": ai_confidence,
        })


def test_buy_invokes_repository_record_trade_with_auto_ai_metadata(monkeypatch):
    spy = _SpyRepository()
    # session_portfolio.py는 `from ... import get_repository`로 이름을 직접 가져다 쓰므로,
    # repository_factory 모듈이 아니라 session_portfolio 모듈에 바인딩된 이름을 patch해야 한다.
    monkeypatch.setattr(sp, "get_repository", lambda *a, **kw: spy)

    state: dict = {}
    sp.buy(
        state, CATEGORY, "005930", "삼성전자", 70000.0, 70000.0,
        source="AUTO_AI", ai_signal="BUY", ai_confidence=0.9, ai_reason="테스트 근거",
    )

    assert len(spy.calls) == 1
    assert spy.calls[0]["source"] == "AUTO_AI"
    assert spy.calls[0]["ai_signal"] == "BUY"
    assert spy.calls[0]["ai_confidence"] == 0.9


def test_failed_buy_does_not_invoke_repository_record_trade(monkeypatch):
    """검증 실패(현금 부족 등)로 매매가 체결되지 않으면 저장소 훅도 호출되면 안 된다."""
    spy = _SpyRepository()
    monkeypatch.setattr(sp, "get_repository", lambda *a, **kw: spy)

    state: dict = {}
    ok, _ = sp.buy(state, CATEGORY, "005930", "삼성전자", 70000.0, 10_000_000.0)

    assert ok is False
    assert spy.calls == []
