# -*- coding: utf-8 -*-
"""
브로커 공통 인터페이스 (Interface First Design).

목적: 가상 매매(PaperBroker)와 실전 매매(업비트/KIS 등)를 동일한 인터페이스로
    다뤄서, AutoTrader가 "지금이 페이퍼인지 실전인지" 전혀 몰라도 되게 한다.

실전 브로커 추가 방법 (Phase 5 실전 단계):
    class UpbitBroker(BaseBroker):        # 암호화폐
    class KisBroker(BaseBroker):          # 한국/미국 주식 (한국투자증권 OpenAPI)
    → place_order()만 구현하면 AutoTrader 수정 없이 교체 가능.

⚠️ 실전 브로커는 반드시 broker_factory.get_broker()를 통해서만 생성한다.
   (LIVE_TRADING 환경변수 + 명시적 확인 문구가 없으면 절대 실전으로 안 넘어감)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    """주문 방향."""

    BUY = "BUY"
    SELL = "SELL"


class BrokerError(Exception):
    """브로커 계층에서 발생하는 모든 오류의 기반 클래스."""


@dataclass(frozen=True)
class OrderRequest:
    """주문 요청 (브로커 독립적).

    Attributes:
        category: 시장 카테고리 (sp.CATEGORIES 중 하나).
        symbol: 종목 심볼 (표시용, 예: "005930", "AAPL", "BTC").
        name: 종목 이름.
        side: BUY 또는 SELL.
        price: 기준 가격 (시장가 주문이어도 검증/기록용으로 필수).
        amount: 주문 금액 (BUY: 투입 현금, SELL: 0이면 전량 매도).
        source: "MANUAL" | "AUTO_AI".
        ai_signal: AI 원본 신호 (감사 추적용).
        ai_confidence: AI 신뢰도.
        ai_reason: AI 판단 근거.
    """

    category: str
    symbol: str
    name: str
    side: OrderSide
    price: float
    amount: float = 0.0
    source: str = "AUTO_AI"
    ai_signal: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reason: Optional[str] = None


@dataclass
class OrderResult:
    """주문 실행 결과.

    Attributes:
        success: 체결 성공 여부.
        message: 결과/실패 사유 메시지.
        request: 원본 주문 요청.
        executed_at: 체결 시각.
        is_live: 실전 주문이었는지 여부 (감사 추적 필수 필드).
    """

    success: bool
    message: str
    request: OrderRequest
    executed_at: datetime = field(default_factory=datetime.now)
    is_live: bool = False


class BaseBroker(ABC):
    """모든 브로커(가상/실전)가 구현해야 하는 공통 인터페이스."""

    #: 실전 브로커는 True로 오버라이드한다. 로깅/이중확인에 사용.
    IS_LIVE: bool = False

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """주문을 실행한다.

        Args:
            request: 주문 요청.

        Returns:
            OrderResult (성공/실패와 사유).

        Raises:
            BrokerError: 브로커 통신 자체가 불가능한 경우
                (단순 주문 거절은 예외가 아니라 success=False로 반환).
        """
        raise NotImplementedError

    @abstractmethod
    def get_cash(self, category: str) -> float:
        """해당 카테고리의 주문 가능 현금을 반환한다."""
        raise NotImplementedError

    @abstractmethod
    def get_holding_qty(self, category: str, symbol: str) -> float:
        """해당 종목의 보유 수량을 반환한다 (없으면 0)."""
        raise NotImplementedError
