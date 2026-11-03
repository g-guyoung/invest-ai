# -*- coding: utf-8 -*-
"""
매매 전략 공통 인터페이스 (Strategy Pattern).

목적:
    백테스트와 실전 봇이 **완전히 같은 전략 코드**를 쓰게 한다.
    백테스트에서 검증한 로직과 실제 돈으로 돌아가는 로직이 달라지는 사고를 구조적으로 막는다.

규약 (Look-ahead 방지):
    generate_positions(df)는 각 봉 t의 **종가까지의 정보만으로** "다음 봉부터 들고 있을 목표 포지션"
    (0 = 현금, 1 = 비트코인 전량 보유)을 반환한다. 실제 적용 시점 이동(t → t+1)은
    백테스트 엔진/실전 봇이 담당한다. 전략이 미래 데이터를 쓰면 테스트(test_no_lookahead)가 잡아낸다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd


class BaseStrategy(ABC):
    """롱 온리(현물) 전략 기반 클래스.

    하위 클래스는 `name`, `default_params`, `param_grid`, `_positions()`만 정의하면 된다.
    """

    #: 사람이 읽는 전략 이름
    name: ClassVar[str] = "base"
    #: 기본 파라미터
    default_params: ClassVar[dict[str, Any]] = {}
    #: walk-forward 최적화용 파라미터 후보 (작게 유지 — 과적합 방지)
    param_grid: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **params: Any) -> None:
        """
        Args:
            **params: default_params를 덮어쓸 파라미터. 정의되지 않은 키는 거부한다.

        Raises:
            ValueError: 알 수 없는 파라미터가 들어온 경우.
        """
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: 알 수 없는 파라미터 {sorted(unknown)}")
        self.params: dict[str, Any] = {**self.default_params, **params}

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        """목표 포지션 시계열(0 또는 1, float)을 반환한다.

        Args:
            df: open_time 오름차순 OHLCV DataFrame (open, high, low, close, volume 필수).

        Returns:
            df와 같은 인덱스의 0/1 시계열. 지표 워밍업 구간은 0(현금)이다.

        Raises:
            ValueError: 필수 컬럼이 없을 때.
        """
        missing = {"open", "high", "low", "close"} - set(df.columns)
        if missing:
            raise ValueError(f"OHLC 컬럼 누락: {sorted(missing)}")
        pos = self._positions(df).reindex(df.index)
        return pos.fillna(0.0).clip(0.0, 1.0).astype(float)

    @abstractmethod
    def _positions(self, df: pd.DataFrame) -> pd.Series:
        """전략별 포지션 계산 (하위 클래스 구현)."""

    def describe(self) -> str:
        """로그/리포트용 한 줄 설명. 예: 'EMA추세(fast=20, slow=60)'."""
        args = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({args})"


def hold_until_exit(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """진입 신호가 나오면 청산 신호가 나올 때까지 포지션을 유지하는 상태 머신 (벡터화).

    같은 봉에서 진입과 청산이 동시에 나오면 청산을 우선한다(보수적).

    Args:
        entry: 진입 조건 bool 시계열.
        exit_: 청산 조건 bool 시계열.

    Returns:
        0/1 float 시계열.

    Examples:
        >>> e = pd.Series([False, True, False, False, False])
        >>> x = pd.Series([False, False, False, True, False])
        >>> hold_until_exit(e, x).tolist()
        [0.0, 1.0, 1.0, 0.0, 0.0]
    """
    state = pd.Series(float("nan"), index=entry.index)
    state[entry.fillna(False).astype(bool)] = 1.0
    state[exit_.fillna(False).astype(bool)] = 0.0  # 청산 우선
    return state.ffill().fillna(0.0)
