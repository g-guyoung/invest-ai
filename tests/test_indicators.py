# -*- coding: utf-8 -*-
"""src/engine/indicators.py 에 대한 pytest 테스트."""

import numpy as np
import pandas as pd
import pytest

from src.engine.indicators import add_indicators, calc_rsi


def _make_ohlcv(n: int = 80, trend: str = "up") -> pd.DataFrame:
    """테스트용 합성 OHLCV DataFrame을 생성한다."""
    rng = np.arange(n, dtype=float)
    base = 100 + (rng if trend == "up" else -rng)
    close = base + np.sin(rng / 3)  # 약간의 변동성 추가
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.5
    volume = np.full(n, 1000.0)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


# ── 정상 케이스 ──────────────────────────────────────────────
def test_add_indicators_adds_expected_columns():
    df = _make_ohlcv()
    result = add_indicators(df)

    expected_new_cols = {
        "rsi", "macd", "macd_signal", "ma5", "ma20", "ma60",
        "bb_upper", "bb_lower", "bb_width", "stoch", "obv", "atr",
        "momentum_10", "volume_ratio", "trend",
    }
    assert expected_new_cols.issubset(set(result.columns))
    assert len(result) == len(df)


def test_add_indicators_does_not_mutate_input():
    df = _make_ohlcv()
    original_cols = list(df.columns)
    add_indicators(df)
    assert list(df.columns) == original_cols


def test_rsi_high_for_consistent_uptrend():
    # 꾸준히 상승하는 종가는 RSI가 높은 값(과매수 근접)이어야 한다.
    close = pd.Series(np.linspace(100, 200, 60))
    rsi = calc_rsi(close)
    assert rsi.iloc[-1] > 70


def test_add_indicators_short_dataframe_no_crash():
    # 지표 계산에 필요한 기간보다 짧은 데이터도 예외 없이 처리되어야 한다(NaN으로 채워짐).
    df = _make_ohlcv(n=5)
    result = add_indicators(df)
    assert len(result) == 5
    assert result["ma60"].isna().all()


# ── 실패 케이스 ──────────────────────────────────────────────
def test_add_indicators_missing_columns_raises_value_error():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})  # open/high/low/volume 누락
    with pytest.raises(ValueError):
        add_indicators(df)


def test_add_indicators_empty_dataframe_returns_empty():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    # 컬럼은 있지만 데이터가 없는 경우 -> 예외 없이 빈 결과를 반환해야 한다.
    result = add_indicators(df)
    assert result.empty
