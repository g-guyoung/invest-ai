# -*- coding: utf-8 -*-
"""NaN 가격 방어 회귀 테스트 (2026-11-03).

사고 경위: 2026-09-04 Yahoo가 SOFI 마지막 봉 종가를 NaN으로 반환 →
AutoTrader가 NaN 가격으로 전량 매도 → 보유분은 삭제됐지만 현금(NaN)은 저장되지 않아
미국 주식 지갑의 약 23%가 유실, 이후 낙폭 -23.4%가 고정되어 9/6부터 미국 주식 매수가
전면 차단됐다.

방어선 3겹을 각각 고정한다.
1. YahooFetcher: 종가가 NaN인 봉을 버린다.
2. AutoTrader: 현재가가 유효하지 않으면 매매하지 않는다.
3. session_portfolio.buy()/sell(): NaN/0/음수 가격을 거부하고 상태를 바꾸지 않는다.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.engine.base_analyzer import AnalysisResult, BaseAnalyzer, Signal
from src.fetcher.base_fetcher import FetcherError
from src.fetcher.yahoo_fetcher import YahooFetcher
from src.portfolio import repository_factory, session_portfolio as sp
from src.trading.auto_trader import AutoTrader, WatchlistItem
from src.trading.deployment_pacing import CAMPAIGN_START_DATE

US = "🇺🇸 미국 주식"
SOFI = WatchlistItem(US, "SOFI", "SOFI", "SoFi Technologies")


@pytest.fixture(autouse=True)
def _session_repository(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    repository_factory.reset_cache()
    yield
    repository_factory.reset_cache()


class _SellAnalyzer(BaseAnalyzer):
    def analyze(self, df, symbol, market_context=None):
        return AnalysisResult(signal=Signal.SELL, confidence=0.9, reason="test", risk_score=0.2)


def _ohlcv_with_last_close(last_close: float, n: int = 60) -> pd.DataFrame:
    close = np.linspace(10.0, 20.0, n)
    close[-1] = last_close
    return pd.DataFrame({
        "open_time": pd.date_range("2026-08-01", periods=n, freq="D"),
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": np.full(n, 1_000_000.0),
    })


# ── 3. 포트폴리오 레벨 ───────────────────────────────────────
@pytest.mark.parametrize("bad_price", [float("nan"), float("inf"), 0.0, -1.0])
def test_sell_rejects_invalid_price_and_keeps_state(bad_price):
    state: dict = {}
    sp.buy(state, US, "SOFI", "SoFi Technologies", 20.0, 100_000.0)
    before = {"cash": state["portfolio"][US]["cash"], "qty": state["portfolio"][US]["holdings"]["SOFI"]["qty"]}

    ok, _ = sp.sell(state, US, "SOFI", bad_price)

    assert ok is False
    book = state["portfolio"][US]
    assert book["holdings"]["SOFI"]["qty"] == before["qty"]  # 보유분이 사라지지 않음
    assert book["cash"] == before["cash"]


@pytest.mark.parametrize("bad_price", [float("nan"), float("inf")])
def test_buy_rejects_non_finite_price(bad_price):
    state: dict = {}
    ok, _ = sp.buy(state, US, "SOFI", "SoFi Technologies", bad_price, 100_000.0)
    assert ok is False
    assert "SOFI" not in state["portfolio"][US]["holdings"]


# ── 2. 자동매매 엔진 레벨 ────────────────────────────────────
def test_auto_trader_skips_trade_when_last_close_is_nan(monkeypatch):
    monkeypatch.setattr(
        "src.trading.auto_trader.FetcherRegistry.get_ohlcv",
        lambda **kwargs: _ohlcv_with_last_close(float("nan")),
    )
    trader = AutoTrader(
        analyzer=_SellAnalyzer(), watchlist=[SOFI],
        today=CAMPAIGN_START_DATE + timedelta(days=1),
    )
    state: dict = {}
    sp.buy(state, US, "SOFI", "SoFi Technologies", 20.0, 100_000.0)

    decision = trader.run_once(state, SOFI)

    assert decision.executed is False
    assert decision.error and "유효하지 않은 현재가" in decision.error
    assert "SOFI" in state["portfolio"][US]["holdings"]


# ── 1. 데이터 수집 레벨 ──────────────────────────────────────
@patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
def test_yahoo_fetcher_drops_rows_with_nan_close(mock_yf):
    history = pd.DataFrame({
        "Open": [10.0, 11.0, 12.0], "High": [11.0, 12.0, 13.0],
        "Low": [9.0, 10.0, 11.0], "Close": [10.5, 11.5, np.nan],
        "Volume": [1e6, 1e6, 0.0],
    }, index=pd.date_range("2026-09-02", periods=3, name="Date"))
    mock_yf.Ticker.return_value = Mock(history=Mock(return_value=history))

    df = YahooFetcher().get_ohlcv(symbol="SOFI", limit=100)

    assert len(df) == 2
    assert df["close"].iloc[-1] == pytest.approx(11.5)
    assert df["close"].notna().all()


@patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
def test_yahoo_fetcher_raises_when_all_closes_missing(mock_yf):
    history = pd.DataFrame({
        "Open": [10.0], "High": [11.0], "Low": [9.0], "Close": [np.nan], "Volume": [0.0],
    }, index=pd.date_range("2026-09-04", periods=1, name="Date"))
    mock_yf.Ticker.return_value = Mock(history=Mock(return_value=history))

    with pytest.raises(FetcherError):
        YahooFetcher().get_ohlcv(symbol="SOFI", limit=100)
