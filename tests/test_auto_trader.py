# -*- coding: utf-8 -*-
"""
src/trading/auto_trader.py 에 대한 pytest 테스트.

실제 Yahoo Finance/Claude API는 호출하지 않는다.
- FetcherRegistry.get_ohlcv: monkeypatch로 고정된 OHLCV DataFrame을 반환.
- analyzer: BaseAnalyzer를 흉내내는 가짜 분석기(_FixedAnalyzer)로 원하는
  {signal, confidence, risk_score}를 그대로 반환하도록 제어.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.engine.base_analyzer import AnalysisResult, AnalyzerError, BaseAnalyzer, Signal
from src.fetcher.base_fetcher import FetcherError
from src.portfolio import repository_factory
from src.trading.auto_trader import (
    CANDIDATE_POOLS,
    AutoTrader,
    TradingConfig,
    WatchlistItem,
    build_daily_watchlist,
)


def _make_ohlcv_df(n: int = 60, last_close: float = 70000.0) -> pd.DataFrame:
    rng = np.arange(n, dtype=float)
    close = last_close - (n - 1 - rng) * 10  # 마지막 값이 last_close가 되도록 선형 증가
    return pd.DataFrame({
        "open_time": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": close - 5,
        "high": close + 10,
        "low": close - 10,
        "close": close,
        "volume": np.full(n, 1_000_000.0),
    })


class _FixedAnalyzer(BaseAnalyzer):
    """미리 정해둔 AnalysisResult(혹은 예외)를 그대로 돌려주는 테스트용 분석기."""

    def __init__(self, result: AnalysisResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.call_count = 0
        self.last_market_context: str | None = None

    def analyze(
        self, df: pd.DataFrame, symbol: str, market_context: str | None = None
    ) -> AnalysisResult:
        self.call_count += 1
        self.last_market_context = market_context
        if self._error:
            raise self._error
        return self._result


@pytest.fixture(autouse=True)
def _force_session_repository(monkeypatch):
    """Supabase 미설정 상태(세션 저장소)로 고정해 테스트를 독립적으로 만든다."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    repository_factory.reset_cache()
    yield
    repository_factory.reset_cache()


ITEM = WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자")


def _patch_ohlcv(monkeypatch, df: pd.DataFrame | None):
    monkeypatch.setattr(
        "src.trading.auto_trader.FetcherRegistry.get_ohlcv",
        lambda **kwargs: df,
    )


# ── 정상 케이스 ──────────────────────────────────────────────
def test_run_once_executes_buy_on_high_confidence_signal(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df(last_close=70000.0))
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="테스트 매수 근거", risk_score=0.2,
    ))
    trader = AutoTrader(analyzer=analyzer, watchlist=[ITEM])
    state: dict = {}

    decision = trader.run_once(state, ITEM)

    assert decision.executed is True
    assert decision.signal == Signal.BUY
    book = state["portfolio"][ITEM.category]
    assert book["cash"] < 1_000_000.0
    assert "005930" in book["holdings"]
    assert book["history"][-1]["type"] == "BUY"


def test_run_once_sells_existing_holding_on_sell_signal(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df(last_close=80000.0))
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.SELL, confidence=0.8, reason="테스트 매도 근거", risk_score=0.3,
    ))
    trader = AutoTrader(analyzer=analyzer, watchlist=[ITEM])

    state: dict = {}
    from src.portfolio import session_portfolio as sp
    sp.init_portfolio(state)
    sp.buy(state, ITEM.category, "005930", "삼성전자", 70000.0, 700000.0)  # 미리 10주 보유

    decision = trader.run_once(state, ITEM)

    assert decision.executed is True
    assert "005930" not in state["portfolio"][ITEM.category]["holdings"]


def test_run_all_iterates_every_watchlist_item(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.HOLD, confidence=0.9, reason="관망", risk_score=0.1,
    ))
    watchlist = [
        WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자"),
        WatchlistItem("🇺🇸 미국 주식", "AAPL", "AAPL", "Apple"),
    ]
    trader = AutoTrader(analyzer=analyzer, watchlist=watchlist)

    decisions = trader.run_all()

    assert len(decisions) == 2
    assert all(d.signal == Signal.HOLD for d in decisions)
    assert all(not d.executed for d in decisions)


# ── 리스크 규칙(관망/보류) 케이스 ────────────────────────────
def test_run_once_holds_off_when_confidence_below_threshold(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.3, reason="확신 부족", risk_score=0.2,
    ))
    trader = AutoTrader(analyzer=analyzer, config=TradingConfig(min_confidence=0.6))

    decision = trader.run_once({}, ITEM)

    assert decision.executed is False
    assert "신뢰도 부족" in decision.message


def test_run_once_holds_off_buy_when_risk_score_too_high(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="위험한 매수", risk_score=0.95,
    ))
    trader = AutoTrader(analyzer=analyzer, config=TradingConfig(max_risk_score=0.7))

    decision = trader.run_once({}, ITEM)

    assert decision.executed is False
    assert "위험도 과다" in decision.message


def test_run_once_skips_sell_when_no_holding(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.SELL, confidence=0.9, reason="매도 신호지만 보유 없음", risk_score=0.2,
    ))
    trader = AutoTrader(analyzer=analyzer)

    decision = trader.run_once({}, ITEM)

    assert decision.executed is False
    assert "보유 중이 아니므로" in decision.message


# ── 실패 케이스 ──────────────────────────────────────────────
def test_run_once_handles_missing_price_data_gracefully(monkeypatch):
    _patch_ohlcv(monkeypatch, None)
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="x", risk_score=0.1,
    ))
    trader = AutoTrader(analyzer=analyzer)

    decision = trader.run_once({}, ITEM)

    assert decision.executed is False
    assert decision.error is not None
    assert analyzer.call_count == 0  # 데이터가 없으면 분석 자체를 시도하지 않는다.


def test_run_once_handles_fetcher_error_without_raising(monkeypatch):
    def _raise(**kwargs):
        raise FetcherError("가격 조회 실패")

    monkeypatch.setattr("src.trading.auto_trader.FetcherRegistry.get_ohlcv", _raise)
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="x", risk_score=0.1,
    ))
    trader = AutoTrader(analyzer=analyzer)

    decision = trader.run_once({}, ITEM)  # 예외를 던지지 않아야 한다.

    assert decision.executed is False
    assert decision.error is not None


def test_run_once_handles_analyzer_error_without_raising(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(error=AnalyzerError("AI 분석 실패"))
    trader = AutoTrader(analyzer=analyzer)

    decision = trader.run_once({}, ITEM)

    assert decision.executed is False
    assert decision.error is not None


# ── 시장별 맥락 / 리스크 설정 자동 적용 ─────────────────────
def test_run_once_passes_market_context_to_analyzer(monkeypatch):
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.HOLD, confidence=0.9, reason="x", risk_score=0.1,
    ))
    crypto_item = WatchlistItem("₿ 암호화폐", "BTC-USD", "BTC", "Bitcoin")
    trader = AutoTrader(analyzer=analyzer)

    trader.run_once({}, crypto_item)

    assert analyzer.last_market_context is not None
    assert "24시간" in analyzer.last_market_context  # 암호화폐 프로필의 맥락 문구


def test_default_config_uses_stricter_crypto_profile(monkeypatch):
    """config를 명시하지 않으면 암호화폐는 주식보다 더 보수적인 리스크 설정을 써야 한다."""
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    # 위험도 0.65는 주식 기본값(max_risk_score=0.7)은 통과하지만
    # 암호화폐 기본값(max_risk_score=0.6)은 통과하지 못해야 한다.
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="x", risk_score=0.65,
    ))
    crypto_item = WatchlistItem("₿ 암호화폐", "BTC-USD", "BTC", "Bitcoin")
    trader = AutoTrader(analyzer=analyzer)  # config=None -> 시장별 프로필 자동 적용

    decision = trader.run_once({}, crypto_item)

    assert decision.executed is False
    assert "위험도 과다" in decision.message


def test_explicit_config_overrides_market_profile(monkeypatch):
    """config를 명시하면 시장과 상관없이 그 값을 그대로 써야 한다."""
    _patch_ohlcv(monkeypatch, _make_ohlcv_df())
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.BUY, confidence=0.9, reason="x", risk_score=0.65,
    ))
    crypto_item = WatchlistItem("₿ 암호화폐", "BTC-USD", "BTC", "Bitcoin")
    trader = AutoTrader(analyzer=analyzer, config=TradingConfig(max_risk_score=0.9))

    decision = trader.run_once({}, crypto_item)

    assert decision.executed is True  # 명시적 config(0.9)는 risk_score 0.65를 통과시켜야 함


# ── 감시 종목 풀 / 무작위 구성 ──────────────────────────────
def test_candidate_pools_cover_all_categories():
    from src.portfolio.constants import CATEGORIES

    assert set(CANDIDATE_POOLS.keys()) == set(CATEGORIES)
    for category, pool in CANDIDATE_POOLS.items():
        assert len(pool) >= 3
        assert all(item.category == category for item in pool)


def test_build_daily_watchlist_samples_per_category():
    watchlist = build_daily_watchlist(sample_size=2, rng=__import__("random").Random(42))

    by_category: dict[str, int] = {}
    for item in watchlist:
        by_category[item.category] = by_category.get(item.category, 0) + 1

    assert all(count == 2 for count in by_category.values())
    assert len(by_category) == len(CANDIDATE_POOLS)


def test_build_daily_watchlist_is_deterministic_with_same_seed():
    import random

    watchlist_a = build_daily_watchlist(sample_size=2, rng=random.Random(7))
    watchlist_b = build_daily_watchlist(sample_size=2, rng=random.Random(7))

    assert [i.display_symbol for i in watchlist_a] == [i.display_symbol for i in watchlist_b]


def test_auto_trader_without_explicit_watchlist_builds_one(monkeypatch):
    """watchlist를 안 넘기면 후보 풀에서 자동으로 구성돼야 한다 (매번 6개 고정이 아님)."""
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.HOLD, confidence=0.9, reason="x", risk_score=0.1,
    ))
    trader = AutoTrader(analyzer=analyzer, sample_size=2)

    assert len(trader.watchlist) == 2 * len(CANDIDATE_POOLS)


def test_run_all_continues_after_one_item_fails(monkeypatch):
    """감시 종목 하나가 실패해도 나머지는 계속 처리돼야 한다."""
    call_state = {"count": 0}

    def _flaky_ohlcv(**kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            raise FetcherError("첫 종목만 실패")
        return _make_ohlcv_df()

    monkeypatch.setattr("src.trading.auto_trader.FetcherRegistry.get_ohlcv", _flaky_ohlcv)
    analyzer = _FixedAnalyzer(AnalysisResult(
        signal=Signal.HOLD, confidence=0.9, reason="x", risk_score=0.1,
    ))
    watchlist = [
        WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자"),
        WatchlistItem("🇺🇸 미국 주식", "AAPL", "AAPL", "Apple"),
    ]
    trader = AutoTrader(analyzer=analyzer, watchlist=watchlist)

    decisions = trader.run_all()

    assert len(decisions) == 2
    assert decisions[0].error is not None
    assert decisions[1].error is None
    assert decisions[1].signal == Signal.HOLD
