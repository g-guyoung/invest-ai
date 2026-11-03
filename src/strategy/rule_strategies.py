# -*- coding: utf-8 -*-
"""
규칙 기반 비트코인 전략 3종 + 기준선(Buy & Hold).

선정 이유 — 성격이 서로 다른 세 가지 대표 계열을 같은 조건으로 비교한다:
    1. EmaTrend        추세추종: 상승 추세에 올라타고 하락 추세는 피한다.
    2. DonchianBreakout 돌파: N일 신고가 돌파 시 진입, M일 신저가 이탈 시 청산 (터틀 트레이딩 계열).
    3. RsiMeanReversion 평균회귀: 과매도 반등을 노린다. (추세장에선 약한 편 — 비교용)

파라미터 후보(param_grid)는 의도적으로 작게 유지한다. 후보가 많을수록 과거에만 맞는
과적합 전략이 뽑힐 확률이 커지기 때문이다.
"""

from __future__ import annotations

import pandas as pd

from src.engine.indicators import calc_rsi
from src.strategy.base_strategy import BaseStrategy, hold_until_exit


class BuyAndHold(BaseStrategy):
    """기준선: 처음부터 끝까지 들고 있기. 모든 전략은 이것을 이겨야 의미가 있다."""

    name = "BuyAndHold"
    default_params: dict = {}
    param_grid = [{}]

    def _positions(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


class EmaTrend(BaseStrategy):
    """빠른 EMA가 느린 EMA 위에 있으면 보유, 아래면 현금."""

    name = "EMA추세"
    default_params = {"fast": 20, "slow": 60}
    param_grid = [
        {"fast": f, "slow": s} for f, s in [(10, 30), (20, 60), (20, 100), (50, 150), (50, 200)]
    ]

    def _positions(self, df: pd.DataFrame) -> pd.Series:
        fast = df["close"].ewm(span=self.params["fast"], adjust=False).mean()
        slow = df["close"].ewm(span=self.params["slow"], adjust=False).mean()
        pos = (fast > slow).astype(float)
        pos.iloc[: self.params["slow"]] = 0.0  # 워밍업 구간은 거래하지 않음
        return pos


class DonchianBreakout(BaseStrategy):
    """직전 `entry`봉 최고가를 종가가 돌파하면 진입, 직전 `exit`봉 최저가를 이탈하면 청산."""

    name = "돌파"
    default_params = {"entry": 20, "exit": 10}
    param_grid = [
        {"entry": e, "exit": x} for e, x in [(20, 10), (30, 15), (55, 20), (55, 30), (100, 50)]
    ]

    def _positions(self, df: pd.DataFrame) -> pd.Series:
        # shift(1): 현재 봉을 제외한 "직전" 구간 극값과 비교해야 look-ahead가 없다.
        upper = df["high"].rolling(self.params["entry"]).max().shift(1)
        lower = df["low"].rolling(self.params["exit"]).min().shift(1)
        return hold_until_exit(df["close"] > upper, df["close"] < lower)


class RsiMeanReversion(BaseStrategy):
    """RSI가 `buy_below` 아래로 내려가면 진입, `sell_above` 위로 올라가면 청산."""

    name = "RSI역추세"
    default_params = {"period": 14, "buy_below": 30, "sell_above": 55}
    param_grid = [
        {"period": 14, "buy_below": b, "sell_above": s}
        for b, s in [(25, 50), (30, 55), (30, 65), (35, 60), (40, 70)]
    ]

    def _positions(self, df: pd.DataFrame) -> pd.Series:
        rsi = calc_rsi(df["close"], self.params["period"])
        return hold_until_exit(rsi < self.params["buy_below"], rsi > self.params["sell_above"])


#: 백테스트 비교 대상 (기준선 포함). 새 전략은 여기에 추가만 하면 된다 (OCP).
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    cls.name: cls for cls in (BuyAndHold, EmaTrend, DonchianBreakout, RsiMeanReversion)
}
