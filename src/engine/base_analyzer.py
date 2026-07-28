# -*- coding: utf-8 -*-
"""
AI 분석 엔진의 공통 인터페이스와 결과 스키마.

목적: Claude/GPT/Gemini/로컬 LLM 등 여러 AI 분석기를 동일한 인터페이스
    (BaseAnalyzer)로 다룰 수 있게 하여, 향후 Phase 7(Multi AI)에서
    분석기를 손쉽게 교체/추가할 수 있도록 한다.

설계 노트
---------
- 모든 분석기는 BaseAnalyzer를 상속하고 analyze()만 구현하면 된다
  (Strategy Pattern + Interface First Design).
- 분석 결과는 신뢰할 수 없는 LLM 출력을 검증해야 하므로 Pydantic
  모델(AnalysisResult)로 강제한다 — 값 범위를 벗어나면 즉시 오류가 난다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd
from pydantic import BaseModel, Field


class Signal(str, Enum):
    """투자 신호."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AnalysisResult(BaseModel):
    """AI 분석 결과 스키마.

    Attributes:
        signal: BUY/SELL/HOLD 신호.
        confidence: 신호에 대한 확신도 (0.0~1.0).
        reason: 신호 판단 근거 (자연어 설명).
        risk_score: 리스크 점수 (0.0~1.0, 높을수록 위험).
    """

    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    risk_score: float = Field(ge=0.0, le=1.0)


class AnalyzerError(Exception):
    """AI 분석 과정에서 발생하는 모든 오류의 기반 클래스."""


class BaseAnalyzer(ABC):
    """모든 AI 분석기가 구현해야 하는 공통 인터페이스."""

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> AnalysisResult:
        """지표가 포함된 OHLCV DataFrame을 분석하여 투자 신호를 반환한다.

        Args:
            df: src.engine.indicators.add_indicators()를 거친 DataFrame.
            symbol: 분석 대상 심볼 (예: "BTCUSDT").

        Returns:
            AnalysisResult.

        Raises:
            AnalyzerError: 분석에 실패한 경우.
        """
        raise NotImplementedError
