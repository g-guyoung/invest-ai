# -*- coding: utf-8 -*-
"""
세션 전용 포트폴리오 저장소 (Supabase 미설정 시 기본 폴백).

목적: Supabase 키가 없거나 연결에 실패했을 때도 앱이 죽지 않고
    기존 MVP와 동일하게(새로고침 시 초기화되는 세션 기반으로) 동작하도록 한다.
"""

from __future__ import annotations

from typing import Optional

from src.portfolio.base_repository import PortfolioRepository
from src.portfolio.constants import CATEGORIES, INITIAL_BALANCE


class SessionPortfolioRepository(PortfolioRepository):
    """st.session_state(또는 plain dict)에만 상태를 두는 저장소.

    영구 저장을 하지 않으므로 새로고침/프로세스 재시작 시 초기화된다.
    """

    def load_into(self, session_state: dict) -> None:
        """포트폴리오 구조가 없으면 카테고리별 초기 현금으로 새로 만든다."""
        if "portfolio" not in session_state:
            session_state["portfolio"] = {
                category: {"cash": INITIAL_BALANCE, "holdings": {}, "history": []}
                for category in CATEGORIES
            }

    def record_trade(
        self,
        category: str,
        symbol: str,
        name: str,
        trade_type: str,
        qty: float,
        price: float,
        amount: float,
        book: dict,
        source: str = "MANUAL",
        ai_signal: Optional[str] = None,
        ai_confidence: Optional[float] = None,
        ai_reason: Optional[str] = None,
    ) -> None:
        """세션 저장소는 book 자체가 이미 session_state 안의 객체이므로 별도 작업이 필요 없다."""
        return None
