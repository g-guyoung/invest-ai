# -*- coding: utf-8 -*-
"""
포트폴리오 저장소 인터페이스 (Repository Pattern).

목적: 포트폴리오 상태(현금/보유종목/거래내역)를 "어디에" 저장하든
    session_portfolio.py의 계산 로직(buy/sell/get_summary)은 그 사실을
    전혀 몰라도 되도록 저장 방식을 추상화한다.

구현체
------
- SessionPortfolioRepository: st.session_state(또는 plain dict)에만 저장.
  Supabase 미설정 시 기본 폴백이며, 기존 MVP와 동일하게 동작한다.
- SupabasePortfolioRepository: Supabase(PostgreSQL)에 영구 저장.
  새로고침/재배포/자동매매 스케줄러 재실행에도 상태가 유지된다.

향후 확장: 실거래 브로커 저장소(Phase 5 실거래 단계)도 동일 인터페이스로
추가할 수 있다 (Interface First Design).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class PortfolioRepository(ABC):
    """포트폴리오 영속성 계층의 공통 인터페이스."""

    @abstractmethod
    def load_into(self, session_state: dict) -> None:
        """session_state["portfolio"]가 없으면 채워 넣는다.

        구현체는 이미 "portfolio" 키가 있으면 아무 것도 하지 않아야 한다
        (한 세션/한 실행 내에서 중복 로드를 방지하기 위함).

        Args:
            session_state: st.session_state 또는 일반 dict. 자동매매 엔진처럼
                Streamlit 없이 실행되는 코드에서는 plain dict를 넘겨 동일한
                로직을 그대로 재사용한다.

        Returns:
            None (session_state를 직접 수정한다).
        """
        raise NotImplementedError

    @abstractmethod
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
        """매수/매도 체결 직후, 갱신된 book 상태를 저장소에 반영한다.

        Args:
            category: 시장 카테고리 (예: "🇰🇷 한국 주식").
            symbol: 종목 심볼.
            name: 종목 표시 이름.
            trade_type: "BUY" 또는 "SELL".
            qty: 체결 수량.
            price: 체결 가격.
            amount: 체결 금액 (BUY는 매수금액, SELL은 회수금액).
            book: 해당 카테고리의 갱신된 {"cash", "holdings", "history"} 딕셔너리
                (session_portfolio.buy/sell이 이미 메모리 상에서 계산을 마친 상태).
            source: "MANUAL"(사용자 수동 거래) 또는 "AUTO_AI"(자동매매 엔진).
            ai_signal: 자동매매인 경우 AI 신호 문자열(BUY/SELL/HOLD), 감사 추적용.
            ai_confidence: 자동매매인 경우 AI 신뢰도(0.0~1.0).
            ai_reason: 자동매매인 경우 AI 판단 근거.

        Returns:
            None. 저장 실패는 로깅만 하고 예외를 던지지 않는 것을 권장한다
            (매매 자체는 이미 메모리상 성공했으므로, 저장 실패가 UI 전체를
            막으면 안 된다).
        """
        raise NotImplementedError
