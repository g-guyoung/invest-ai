# -*- coding: utf-8 -*-
"""
기술적 지표 계산 모듈.

목적: BinanceFetcher가 반환하는 OHLCV DataFrame에 RSI, MACD, 이동평균,
    볼린저밴드 등 기술적 지표 컬럼을 추가한다. 계산 결과는 AI 분석 엔진
    (src/engine/claude_analyzer.py)의 입력으로 사용된다.

설계 노트
---------
- 개별 학교 과제 프로토타입(`20221169 인공지능 최종 과제.py`)의 피처
  엔지니어링 로직을 참고하되, 컬럼명은 BinanceFetcher의 출력
  (open, high, low, close, volume)에 맞춘다.
- 각 지표는 독립적인 순수 함수로 분리하여 재사용/테스트가 쉽도록 한다.
- 입력 DataFrame은 변경하지 않고(사이드이펙트 없이) 새 DataFrame을 반환한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI(상대강도지수)를 계산한다.

    Args:
        close: 종가 시계열.
        period: 계산 기간(기본 14).

    Returns:
        RSI 값(0~100) 시계열. 초기 `period`개 구간은 NaN이다.
    """
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


def calc_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD와 시그널선을 계산한다.

    Args:
        close: 종가 시계열.
        fast: 단기 EMA 기간.
        slow: 장기 EMA 기간.
        signal: 시그널선 EMA 기간.

    Returns:
        columns=["macd", "macd_signal"]를 가진 DataFrame.
    """
    macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd, "macd_signal": macd_signal})


def calc_bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """볼린저밴드를 계산한다.

    Args:
        close: 종가 시계열.
        period: 이동평균 기간.
        num_std: 표준편차 배수.

    Returns:
        columns=["bb_upper", "bb_lower", "bb_width"]를 가진 DataFrame.
    """
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    width = (upper - lower) / (ma + 1e-9)
    return pd.DataFrame({"bb_upper": upper, "bb_lower": lower, "bb_width": width})


def calc_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """스토캐스틱 %K를 계산한다."""
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    return 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-9)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """OBV(누적 거래량 지표)를 계산한다."""
    return (volume * np.sign(close.diff())).fillna(0).cumsum()


def calc_atr(high: pd.Series, low: pd.Series, period: int = 14) -> pd.Series:
    """ATR(단순화된 변동폭 지표: 고가-저가의 롤링 평균)을 계산한다."""
    return (high - low).rolling(period).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV DataFrame에 모든 기술적 지표 컬럼을 추가한다.

    Args:
        df: columns=[open, high, low, close, volume]을 포함하는 DataFrame
            (BinanceFetcher.get_klines()의 반환값 형식).

    Returns:
        원본 컬럼 + [rsi, macd, macd_signal, ma5, ma20, ma60, bb_upper,
        bb_lower, bb_width, stoch, obv, atr, momentum_10, volume_ratio,
        trend] 가 추가된 새 DataFrame. 원본 df는 수정하지 않는다.

    Raises:
        ValueError: 필수 컬럼(open, high, low, close, volume)이 없는 경우.
    """
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")

    result = df.copy()
    close, high, low, volume = result["close"], result["high"], result["low"], result["volume"]

    result["rsi"] = calc_rsi(close)

    macd_df = calc_macd(close)
    result["macd"] = macd_df["macd"]
    result["macd_signal"] = macd_df["macd_signal"]

    result["ma5"] = close.rolling(5).mean()
    result["ma20"] = close.rolling(20).mean()
    result["ma60"] = close.rolling(60).mean()

    bb_df = calc_bollinger_bands(close)
    result["bb_upper"] = bb_df["bb_upper"]
    result["bb_lower"] = bb_df["bb_lower"]
    result["bb_width"] = bb_df["bb_width"]

    result["stoch"] = calc_stochastic(high, low, close)
    result["obv"] = calc_obv(close, volume)
    result["atr"] = calc_atr(high, low)
    result["momentum_10"] = close.pct_change(10)

    vol_ma = volume.rolling(20).mean()
    result["volume_ratio"] = volume / (vol_ma + 1e-9)
    result["trend"] = (result["ma20"] - result["ma60"]) / (result["ma60"] + 1e-9)

    return result
