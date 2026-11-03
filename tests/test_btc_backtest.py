# -*- coding: utf-8 -*-
"""비트코인 실전 봇 Part 1 테스트: 업비트 시세 수집기 / 전략 / 백테스트 엔진 / walk-forward.

핵심 안전 테스트:
    test_no_lookahead_* — 미래 봉을 바꿔도 과거 포지션이 변하지 않아야 한다.
    백테스트 수익률이 부풀려지는 가장 흔한 원인(미래 정보 사용)을 구조적으로 차단한다.
"""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import requests

from src.backtest.engine import run_backtest, walk_forward
from src.exchange.upbit_client import UpbitQuotationClient
from src.fetcher.base_fetcher import FetcherError
from src.strategy.base_strategy import hold_until_exit
from src.strategy.rule_strategies import (
    STRATEGY_REGISTRY,
    BuyAndHold,
    DonchianBreakout,
    EmaTrend,
    RsiMeanReversion,
)


def _ohlcv(n: int = 400, seed: int = 0, drift: float = 0.001) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = pd.Series(50_000_000 * np.exp(np.cumsum(rng.normal(drift, 0.03, n))))
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.02, "low": close * 0.98, "close": close,
        "volume": np.ones(n),
    })


# ── 업비트 시세 수집기 ────────────────────────────────────────
def _candle(ts: str, price: float | None) -> dict:
    return {
        "candle_date_time_utc": ts, "opening_price": price, "high_price": price,
        "low_price": price, "trade_price": price, "candle_acc_trade_volume": 1.0,
    }


def _session(pages: list[list[dict]], status: int = 200) -> Mock:
    responses = []
    for page in pages:
        r = Mock(status_code=status)
        r.json.return_value = page
        r.raise_for_status.return_value = None
        responses.append(r)
    session = Mock(spec=requests.Session)
    session.get.side_effect = responses
    return session


def test_upbit_paginates_and_returns_ascending():
    page1 = [_candle(f"2026-11-0{d}T00:00:00", 100.0 + d) for d in range(3, 0, -1)]  # 최신→과거
    page2 = [_candle("2026-10-31T00:00:00", 99.0)]
    client = UpbitQuotationClient(_session([page1, page2]), request_interval=0)
    import src.exchange.upbit_client as mod
    mod.MAX_PER_REQUEST, orig = 3, mod.MAX_PER_REQUEST
    try:
        df = client.get_ohlcv("KRW-BTC", "1d", count=4)
    finally:
        mod.MAX_PER_REQUEST = orig
    assert df["close"].tolist() == [99.0, 101.0, 102.0, 103.0]
    assert df["open_time"].is_monotonic_increasing
    # 두 번째 요청은 첫 페이지 가장 오래된 봉 시각을 `to`로 사용해야 한다
    assert client.session.get.call_args_list[1].kwargs["params"]["to"] == "2026-11-01T00:00:00"


def test_upbit_drops_invalid_close():
    page = [_candle("2026-11-02T00:00:00", None), _candle("2026-11-01T00:00:00", 100.0)]
    df = UpbitQuotationClient(_session([page]), request_interval=0).get_ohlcv(count=2)
    assert df["close"].tolist() == [100.0]


def test_upbit_raises_fetcher_error_after_retries():
    session = Mock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("down")
    client = UpbitQuotationClient(session, max_retries=2, backoff_seconds=0, request_interval=0)
    with pytest.raises(FetcherError):
        client.get_ohlcv(count=5)
    assert session.get.call_count == 2


@pytest.mark.parametrize("interval,count", [("3d", 10), ("1d", 0)])
def test_upbit_rejects_bad_arguments(interval, count):
    with pytest.raises(ValueError):
        UpbitQuotationClient(Mock()).get_ohlcv(interval=interval, count=count)


# ── 전략 ─────────────────────────────────────────────────────
def test_hold_until_exit_prefers_exit_on_same_bar():
    e = pd.Series([True, False, True])
    x = pd.Series([False, False, True])
    assert hold_until_exit(e, x).tolist() == [1.0, 1.0, 0.0]


def test_strategy_rejects_unknown_param():
    with pytest.raises(ValueError):
        EmaTrend(fastest=3)


@pytest.mark.parametrize("cls", list(STRATEGY_REGISTRY.values()))
def test_positions_are_binary_and_aligned(cls):
    df = _ohlcv()
    pos = cls().generate_positions(df)
    assert pos.index.equals(df.index)
    assert set(pos.unique()) <= {0.0, 1.0}


@pytest.mark.parametrize("cls", [EmaTrend, DonchianBreakout, RsiMeanReversion])
def test_no_lookahead(cls):
    """미래 100봉을 완전히 다른 값으로 바꿔도, 그 이전 포지션은 하나도 바뀌면 안 된다."""
    df = _ohlcv(400)
    altered = df.copy()
    cut = 300
    for col in ("open", "high", "low", "close"):
        altered.loc[cut:, col] = altered.loc[cut:, col] * 3.0
    a = cls().generate_positions(df).iloc[:cut]
    b = cls().generate_positions(altered).iloc[:cut]
    pd.testing.assert_series_equal(a, b)


def test_ema_trend_is_flat_during_warmup():
    pos = EmaTrend(fast=5, slow=50).generate_positions(_ohlcv())
    assert (pos.iloc[:50] == 0).all()


# ── 백테스트 엔진 ─────────────────────────────────────────────
def test_backtest_applies_position_from_next_bar():
    df = pd.DataFrame({"close": [100.0, 200.0, 100.0]})
    # t=0에 매수 신호 → t=1 수익(+100%)부터 반영, t=1에 매도 → t=2 하락(-50%) 회피
    r = run_backtest(df, pd.Series([1.0, 0.0, 0.0]), fee=0, slippage=0)
    assert r.total_return == pytest.approx(1.0)


def test_backtest_charges_costs_per_side():
    df = pd.DataFrame({"close": [100.0] * 4})
    r = run_backtest(df, pd.Series([1.0, 0.0, 0.0, 0.0]), fee=0.001, slippage=0.0)
    assert r.total_return == pytest.approx((1 - 0.001) ** 2 - 1)  # 진입 1회 + 청산 1회


def test_backtest_drawdown_and_trades():
    df = pd.DataFrame({"close": [100.0, 120.0, 60.0, 90.0]})
    r = run_backtest(df, pd.Series([1.0, 1.0, 1.0, 1.0]), fee=0, slippage=0)
    assert r.max_drawdown == pytest.approx(-0.5)
    assert r.n_trades == 1
    assert np.isnan(r.win_rate)  # 미청산 거래만 있으면 승률 미정


def test_backtest_rejects_misaligned_input():
    with pytest.raises(ValueError):
        run_backtest(pd.DataFrame({"close": [1.0, 2.0]}), pd.Series([1.0, 1.0], index=[5, 6]))


def test_backtest_uses_initial_capital():
    df = pd.DataFrame({"close": [100.0, 110.0]})
    r = run_backtest(df, pd.Series([1.0, 1.0]), initial_capital=50_000, fee=0, slippage=0)
    assert r.final_equity == pytest.approx(55_000)


# ── Walk-forward ─────────────────────────────────────────────
def test_walk_forward_covers_only_out_of_sample_bars():
    df = _ohlcv(600)
    wf = walk_forward(df, EmaTrend, train_bars=300, test_bars=100)
    assert len(wf.oos.returns) == 300          # 300~599 검증 구간만
    assert wf.oos.returns.index[0] == 300
    assert len(wf.folds) == 3
    assert all(f["params"] in EmaTrend.param_grid for f in wf.folds)


def test_walk_forward_baseline_matches_buy_and_hold_on_oos_window():
    df = _ohlcv(500)
    wf = walk_forward(df, BuyAndHold, train_bars=300, test_bars=100, fee=0, slippage=0)
    expected = df["close"].iloc[-1] / df["close"].iloc[300] - 1
    assert wf.oos.total_return == pytest.approx(expected)


def test_walk_forward_rejects_short_data():
    with pytest.raises(ValueError):
        walk_forward(_ohlcv(100), EmaTrend, train_bars=300, test_bars=100)
