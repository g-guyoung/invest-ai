# -*- coding: utf-8 -*-
"""
가상 매매 브로커 (PaperBroker).

목적: 기존 session_portfolio.buy()/sell() 로직을 BaseBroker 인터페이스로
    감싸서, AutoTrader가 실전 브로커와 동일한 방식으로 호출할 수 있게 한다.
    (기존 로직을 복사하지 않고 그대로 재사용 — DRY)
"""

from __future__ import annotations

import logging

from src.execution.base_broker import (
    BaseBroker,
    OrderRequest,
    OrderResult,
    OrderSide,
)
from src.portfolio import session_portfolio as sp

logger = logging.getLogger(__name__)


class PaperBroker(BaseBroker):
    """session_portfolio 기반 가상 매매 브로커.

    Args:
        session_state: st.session_state 또는 plain dict.
            AutoTrader처럼 Streamlit 없이 쓸 때는 빈 dict를 넘기면 된다.
    """

    IS_LIVE = False

    def __init__(self, session_state: dict) -> None:
        self._state = session_state
        sp.init_portfolio(self._state)

    def place_order(self, request: OrderRequest) -> OrderResult:
        """가상 주문 실행 (기존 buy/sell 로직 위임)."""
        if request.side == OrderSide.BUY:
            ok, msg = sp.buy(
                self._state,
                request.category,
                request.symbol,
                request.name,
                request.price,
                request.amount,
                source=request.source,
                ai_signal=request.ai_signal,
                ai_confidence=request.ai_confidence,
                ai_reason=request.ai_reason,
            )
        else:
            ok, msg = sp.sell(
                self._state,
                request.category,
                request.symbol,
                request.price,
                source=request.source,
                ai_signal=request.ai_signal,
                ai_confidence=request.ai_confidence,
                ai_reason=request.ai_reason,
            )
        return OrderResult(success=ok, message=msg, request=request, is_live=False)

    def get_cash(self, category: str) -> float:
        return float(self._state["portfolio"][category]["cash"])

    def get_holding_qty(self, category: str, symbol: str) -> float:
        holding = self._state["portfolio"][category]["holdings"].get(symbol)
        return float(holding["qty"]) if holding else 0.0
