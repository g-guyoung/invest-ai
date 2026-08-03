# -*- coding: utf-8 -*-
"""
Supabase 기반 포트폴리오 저장소 (영구 저장, Phase 5 Part 3).

목적: 시장별(한국/미국/암호화폐) 가상 현금/보유종목/거래내역을
    Supabase(PostgreSQL)에 영구 저장해, 새로고침/재배포/자동매매
    스케줄러 재실행에도 상태가 유지되도록 한다.

전제 조건
---------
- 환경변수 SUPABASE_URL / SUPABASE_KEY가 설정되어 있어야 한다.
- scripts/init_db.sql의 wallets / wallet_holdings / wallet_trades
  테이블이 Supabase에 먼저 생성되어 있어야 한다.

설계 노트
---------
- 기존 symbols 테이블은 사전 등록된 종목만 FK로 참조할 수 있어
  자유 검색 심볼(예: 처음 조회하는 종목)과 맞지 않는다. 그래서 이
  저장소는 symbol을 문자열로 직접 저장하는 별도 테이블(wallet_*)을 쓴다.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.database.supabase_client import SupabaseClient
from src.portfolio.base_repository import PortfolioRepository
from src.portfolio.constants import CATEGORIES, INITIAL_BALANCE

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = 1


class SupabasePortfolioRepository(PortfolioRepository):
    """Supabase(PostgreSQL)에 현금/보유종목/거래내역을 영구 저장하는 저장소."""

    def __init__(
        self, client: Optional[SupabaseClient] = None, user_id: int = DEFAULT_USER_ID
    ) -> None:
        """SupabasePortfolioRepository를 초기화한다.

        Args:
            client: 외부에서 주입할 SupabaseClient (테스트 시 mock 주입용).
                생략하면 .env/Streamlit secrets의 SUPABASE_URL/KEY로 새로 만든다.
            user_id: 사용자 ID. 현재는 단일 사용자(1)만 지원한다.

        Raises:
            SupabaseError: client가 없고 SUPABASE_URL/KEY도 없거나
                supabase-py가 설치되어 있지 않은 경우 (SupabaseClient가 던짐).
        """
        self.client = client or SupabaseClient()
        self.user_id = user_id

    def health_check(self) -> bool:
        """Supabase 연결 상태를 확인한다 (repository_factory의 폴백 판단에 사용)."""
        return self.client.health_check()

    def load_into(self, session_state: dict) -> None:
        """Supabase에서 카테고리별 현금/보유종목/최근 거래내역을 읽어 온다.

        지갑이 아직 없는 카테고리는 초기 자금으로 새로 만든다 (최초 1회).
        """
        if "portfolio" in session_state:
            return

        portfolio: dict = {}
        for category in CATEGORIES:
            wallet = self.client.get_wallet(self.user_id, category)
            if wallet is None:
                self.client.init_wallet(self.user_id, category, INITIAL_BALANCE)
                cash = INITIAL_BALANCE
            else:
                cash = float(wallet["cash"])

            holdings = {
                row["symbol"]: {
                    "name": row.get("name") or row["symbol"],
                    "qty": float(row["qty"]),
                    "avg_price": float(row["avg_price"]),
                }
                for row in self.client.get_holdings(self.user_id, category)
            }

            history = [
                {
                    "time": str(t.get("executed_at") or "")[:16].replace("T", " "),
                    "symbol": t["symbol"],
                    "type": t["trade_type"],
                    "qty": float(t["qty"]),
                    "price": float(t["price"]),
                    "amount": float(t["amount"]),
                }
                for t in self.client.get_wallet_trades(self.user_id, category, limit=20)
            ]

            portfolio[category] = {"cash": cash, "holdings": holdings, "history": history}

        session_state["portfolio"] = portfolio

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
        """현금 잔액 / 보유종목 / 거래내역을 Supabase에 반영한다.

        저장 실패는 로깅만 하고 예외를 올리지 않는다 — 매매 자체는 이미
        메모리상 성공했으므로 UI가 죽으면 안 된다 (Graceful Degradation).
        """
        try:
            self.client.update_wallet_cash(self.user_id, category, book["cash"])

            holding = book["holdings"].get(symbol)
            if holding:
                self.client.upsert_holding(
                    self.user_id, category, symbol, holding["name"],
                    holding["qty"], holding["avg_price"],
                )
            else:
                self.client.delete_holding(self.user_id, category, symbol)

            self.client.add_wallet_trade(
                self.user_id, category, symbol, name, trade_type, qty, price, amount,
                source=source, ai_signal=ai_signal, ai_confidence=ai_confidence,
                ai_reason=ai_reason,
            )
        except Exception as exc:  # noqa: BLE001 - 저장 실패가 매매 자체를 막으면 안 됨
            logger.error(f"Supabase 포트폴리오 저장 실패({symbol}, {trade_type}): {exc}")
