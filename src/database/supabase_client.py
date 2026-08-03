# -*- coding: utf-8 -*-
"""
Supabase PostgreSQL 클라이언트.

목적: Streamlit 대시보드에서 Supabase와 통신.
      가격 데이터, AI 분석 결과, 포트폴리오 정보 저장/조회.

설정:
    .env에 다음 필요:
    - SUPABASE_URL: Supabase 프로젝트 URL
    - SUPABASE_KEY: Supabase Public/Anonymous 키
"""

from __future__ import annotations

import os
import logging
from typing import Optional, List, Dict, Any

import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class SupabaseError(Exception):
    """Supabase 연동 에러."""


class SupabaseClient:
    """Supabase PostgreSQL 클라이언트."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None) -> None:
        """
        Supabase 클라이언트 초기화.

        Parameters:
            url: Supabase 프로젝트 URL (기본: .env의 SUPABASE_URL)
            key: Supabase 공개 키 (기본: .env의 SUPABASE_KEY)

        Raises:
            SupabaseError: URL 또는 KEY가 없는 경우
        """
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")

        if not self.url or not self.key:
            raise SupabaseError(
                "SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해주세요."
            )

        try:
            from supabase import create_client
            self.client = create_client(self.url, self.key)
        except ImportError:
            raise SupabaseError(
                "supabase-py가 설치되지 않았습니다. "
                "실행: pip install supabase"
            )

    # ========================================================================
    # Symbols (종목) 관련
    # ========================================================================

    def get_symbols(self, market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        모든 종목 조회.

        Parameters:
            market: 필터링할 시장 (binance, yahoo 등)

        Returns:
            종목 정보 딕셔너리 리스트
        """
        try:
            query = self.client.table("symbols").select("*")
            if market:
                query = query.eq("market", market)
            result = query.execute()
            return result.data
        except Exception as e:
            logger.error(f"종목 조회 실패: {e}")
            return []

    def add_symbol(self, symbol: str, name: str, market: str, **kwargs) -> bool:
        """
        새 종목 추가.

        Parameters:
            symbol: 심볼 (BTC, AAPL, 005930.KS)
            name: 종목명
            market: 시장 (binance, yahoo)
            **kwargs: 추가 필드 (market_type, currency 등)

        Returns:
            성공 여부
        """
        try:
            data = {
                "symbol": symbol,
                "name": name,
                "market": market,
                **kwargs
            }
            self.client.table("symbols").insert(data).execute()
            logger.info(f"종목 추가: {symbol}")
            return True
        except Exception as e:
            logger.error(f"종목 추가 실패: {e}")
            return False

    # ========================================================================
    # Prices (가격 데이터) 관련
    # ========================================================================

    def save_prices(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        가격 데이터 저장 (배치).

        Parameters:
            symbol: 심볼
            df: OHLCV DataFrame (open_time, open, high, low, close, volume)

        Returns:
            성공 여부
        """
        try:
            # 심볼 ID 조회
            symbol_result = self.client.table("symbols").select("id").eq(
                "symbol", symbol
            ).execute()
            if not symbol_result.data:
                logger.warning(f"심볼 {symbol}을 찾을 수 없습니다.")
                return False

            symbol_id = symbol_result.data[0]["id"]

            # 데이터 준비
            records = []
            for _, row in df.iterrows():
                records.append({
                    "symbol_id": symbol_id,
                    "open_time": row["open_time"].isoformat() if hasattr(row["open_time"], "isoformat") else row["open_time"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "interval": "1d",  # 기본값
                })

            # 배치 삽입 (중복 무시)
            self.client.table("prices").upsert(records).execute()
            logger.info(f"{symbol}: {len(records)}개 가격 데이터 저장")
            return True

        except Exception as e:
            logger.error(f"가격 데이터 저장 실패: {e}")
            return False

    def get_latest_prices(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """
        최신 가격 데이터 조회.

        Parameters:
            symbol: 심볼
            limit: 조회 개수

        Returns:
            OHLCV DataFrame
        """
        try:
            result = self.client.table("prices").select(
                "open_time, open, high, low, close, volume"
            ).join("symbols", "symbol_id").eq("symbols.symbol", symbol).order(
                "open_time", descending=True
            ).limit(limit).execute()

            if not result.data:
                logger.warning(f"심볼 {symbol}의 가격 데이터가 없습니다.")
                return pd.DataFrame()

            df = pd.DataFrame(result.data)
            df["open_time"] = pd.to_datetime(df["open_time"])
            return df.sort_values("open_time").reset_index(drop=True)

        except Exception as e:
            logger.error(f"가격 데이터 조회 실패: {e}")
            return pd.DataFrame()

    # ========================================================================
    # Analysis (AI 분석) 관련
    # ========================================================================

    def save_analysis(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        risk_score: float,
        reason: str,
        **indicators
    ) -> bool:
        """
        AI 분석 결과 저장.

        Parameters:
            symbol: 심볼
            signal: 신호 (BUY, SELL, HOLD)
            confidence: 신뢰도 (0.0~1.0)
            risk_score: 위험도 (0~10)
            reason: 분석 이유
            **indicators: 기술적 지표 (rsi, macd 등)

        Returns:
            성공 여부
        """
        try:
            # 심볼 ID 조회
            symbol_result = self.client.table("symbols").select("id").eq(
                "symbol", symbol
            ).execute()
            if not symbol_result.data:
                logger.warning(f"심볼 {symbol}을 찾을 수 없습니다.")
                return False

            symbol_id = symbol_result.data[0]["id"]

            data = {
                "symbol_id": symbol_id,
                "signal": signal,
                "confidence": confidence,
                "risk_score": risk_score,
                "reason": reason,
                "analyzed_at": datetime.utcnow().isoformat(),
                **indicators,
            }

            self.client.table("analysis").insert(data).execute()
            logger.info(f"분석 결과 저장: {symbol} - {signal}")
            return True

        except Exception as e:
            logger.error(f"분석 결과 저장 실패: {e}")
            return False

    def get_latest_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        최신 분석 결과 조회.

        Parameters:
            symbol: 심볼

        Returns:
            분석 결과 딕셔너리 또는 None
        """
        try:
            result = self.client.table("analysis").select("*").join(
                "symbols", "symbol_id"
            ).eq("symbols.symbol", symbol).order(
                "analyzed_at", descending=True
            ).limit(1).execute()

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"분석 결과 조회 실패: {e}")
            return None

    # ========================================================================
    # Portfolio (포트폴리오) 관련
    # ========================================================================

    def get_portfolio(self, user_id: int = 1) -> pd.DataFrame:
        """
        사용자 포트폴리오 조회.

        Parameters:
            user_id: 사용자 ID (기본: 1)

        Returns:
            포트폴리오 DataFrame
        """
        try:
            result = self.client.table("portfolio").select(
                "*, symbols(symbol, name)"
            ).eq("user_id", user_id).execute()

            if not result.data:
                return pd.DataFrame()

            df = pd.DataFrame(result.data)
            return df

        except Exception as e:
            logger.error(f"포트폴리오 조회 실패: {e}")
            return pd.DataFrame()

    def update_portfolio(
        self, user_id: int, symbol: str, quantity: float, average_price: float
    ) -> bool:
        """
        포트폴리오 업데이트.

        Parameters:
            user_id: 사용자 ID
            symbol: 심볼
            quantity: 보유 수량
            average_price: 평균 매수가

        Returns:
            성공 여부
        """
        try:
            # 심볼 ID 조회
            symbol_result = self.client.table("symbols").select("id").eq(
                "symbol", symbol
            ).execute()
            if not symbol_result.data:
                return False

            symbol_id = symbol_result.data[0]["id"]

            data = {
                "user_id": user_id,
                "symbol_id": symbol_id,
                "quantity": quantity,
                "average_price": average_price,
            }

            self.client.table("portfolio").upsert(data).execute()
            logger.info(f"포트폴리오 업데이트: {symbol} - {quantity}개")
            return True

        except Exception as e:
            logger.error(f"포트폴리오 업데이트 실패: {e}")
            return False

    # ========================================================================
    # Orders (거래 기록) 관련
    # ========================================================================

    def add_order(
        self,
        user_id: int,
        symbol: str,
        order_type: str,
        quantity: float,
        price: float
    ) -> bool:
        """
        거래 기록 추가 (페이퍼 트레이딩).

        Parameters:
            user_id: 사용자 ID
            symbol: 심볼
            order_type: 주문 유형 (BUY, SELL)
            quantity: 수량
            price: 가격

        Returns:
            성공 여부
        """
        try:
            # 심볼 ID 조회
            symbol_result = self.client.table("symbols").select("id").eq(
                "symbol", symbol
            ).execute()
            if not symbol_result.data:
                return False

            symbol_id = symbol_result.data[0]["id"]

            data = {
                "user_id": user_id,
                "symbol_id": symbol_id,
                "order_type": order_type,
                "quantity": quantity,
                "price": price,
                "total_amount": quantity * price,
                "status": "filled",
            }

            self.client.table("orders").insert(data).execute()
            logger.info(f"거래 기록: {symbol} {order_type} {quantity}개 @ {price}")
            return True

        except Exception as e:
            logger.error(f"거래 기록 추가 실패: {e}")
            return False

    def get_orders(
        self, user_id: int = 1, status: Optional[str] = None
    ) -> pd.DataFrame:
        """
        거래 기록 조회.

        Parameters:
            user_id: 사용자 ID
            status: 필터링 상태 (pending, filled, cancelled)

        Returns:
            거래 기록 DataFrame
        """
        try:
            query = self.client.table("orders").select("*").eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            result = query.order("order_date", descending=True).execute()

            if not result.data:
                return pd.DataFrame()

            df = pd.DataFrame(result.data)
            df["order_date"] = pd.to_datetime(df["order_date"])
            return df

        except Exception as e:
            logger.error(f"거래 기록 조회 실패: {e}")
            return pd.DataFrame()

    # ========================================================================
    # Wallets / Holdings / Trades (페이퍼 트레이딩 v2, Phase 5 Part 3)
    # ========================================================================
    # 목적: 자유 검색 심볼(symbols 테이블에 사전 등록되지 않은 종목 포함)을
    #       지원하는 시장별(한국/미국/암호화폐) 가상 현금/보유종목/거래내역을
    #       영구 저장한다. 기존 portfolio/orders 테이블은 symbols FK가
    #       필요해 자유 검색과 맞지 않아 별도 테이블(wallet_*)로 분리했다.
    #       스키마: scripts/init_db.sql 참고.

    def get_wallet(self, user_id: int, category: str) -> Optional[Dict[str, Any]]:
        """
        시장 카테고리별 지갑(현금 잔액) 조회.

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리 (예: "🇰🇷 한국 주식")

        Returns:
            지갑 정보 딕셔너리, 없으면 None
        """
        try:
            result = (
                self.client.table("wallets").select("*")
                .eq("user_id", user_id).eq("category", category)
                .limit(1).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"지갑 조회 실패({category}): {e}")
            return None

    def init_wallet(self, user_id: int, category: str, initial_balance: float) -> bool:
        """
        지갑이 없으면 초기 자금으로 새로 만든다 (이미 있으면 그대로 둔다).

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            initial_balance: 초기 가상자금

        Returns:
            성공 여부 (이미 존재해도 True)
        """
        try:
            if self.get_wallet(user_id, category):
                return True
            self.client.table("wallets").insert({
                "user_id": user_id,
                "category": category,
                "cash": initial_balance,
                "initial_balance": initial_balance,
            }).execute()
            logger.info(f"지갑 초기화: {category} (초기자금 {initial_balance:,.0f})")
            return True
        except Exception as e:
            logger.error(f"지갑 초기화 실패({category}): {e}")
            return False

    def update_wallet_cash(self, user_id: int, category: str, cash: float) -> bool:
        """
        지갑 현금 잔액을 갱신한다 (매수/매도 체결 후 호출).

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            cash: 갱신할 현금 잔액

        Returns:
            성공 여부
        """
        try:
            self.client.table("wallets").update({"cash": cash}).eq(
                "user_id", user_id
            ).eq("category", category).execute()
            return True
        except Exception as e:
            logger.error(f"지갑 현금 갱신 실패({category}): {e}")
            return False

    def get_holdings(self, user_id: int, category: str) -> List[Dict[str, Any]]:
        """
        시장 카테고리별 보유 종목 전체 조회.

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리

        Returns:
            보유 종목 딕셔너리 리스트 (symbol, name, qty, avg_price)
        """
        try:
            result = (
                self.client.table("wallet_holdings").select("*")
                .eq("user_id", user_id).eq("category", category).execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"보유종목 조회 실패({category}): {e}")
            return []

    def upsert_holding(
        self, user_id: int, category: str, symbol: str, name: str,
        qty: float, avg_price: float,
    ) -> bool:
        """
        보유 종목을 추가하거나 갱신한다 (수량/평균단가 upsert).

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            symbol: 종목 심볼
            name: 종목 표시 이름
            qty: 보유 수량
            avg_price: 평균 매수가

        Returns:
            성공 여부
        """
        try:
            self.client.table("wallet_holdings").upsert(
                {
                    "user_id": user_id, "category": category, "symbol": symbol,
                    "name": name, "qty": qty, "avg_price": avg_price,
                },
                on_conflict="user_id,category,symbol",
            ).execute()
            return True
        except Exception as e:
            logger.error(f"보유종목 갱신 실패({symbol}): {e}")
            return False

    def delete_holding(self, user_id: int, category: str, symbol: str) -> bool:
        """
        보유 종목을 삭제한다 (전량 매도 시 호출).

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            symbol: 종목 심볼

        Returns:
            성공 여부
        """
        try:
            self.client.table("wallet_holdings").delete().eq(
                "user_id", user_id
            ).eq("category", category).eq("symbol", symbol).execute()
            return True
        except Exception as e:
            logger.error(f"보유종목 삭제 실패({symbol}): {e}")
            return False

    def add_wallet_trade(
        self,
        user_id: int,
        category: str,
        symbol: str,
        name: str,
        trade_type: str,
        qty: float,
        price: float,
        amount: float,
        source: str = "MANUAL",
        ai_signal: Optional[str] = None,
        ai_confidence: Optional[float] = None,
        ai_reason: Optional[str] = None,
    ) -> bool:
        """
        거래 체결 기록을 추가한다 (수동 거래 + 자동매매 모두 사용).

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            symbol: 종목 심볼
            name: 종목 표시 이름
            trade_type: "BUY" 또는 "SELL"
            qty: 체결 수량
            price: 체결 가격
            amount: 체결 금액
            source: "MANUAL" 또는 "AUTO_AI"
            ai_signal: 자동매매인 경우 AI 신호 (감사 추적용)
            ai_confidence: 자동매매인 경우 AI 신뢰도
            ai_reason: 자동매매인 경우 AI 판단 근거

        Returns:
            성공 여부
        """
        try:
            self.client.table("wallet_trades").insert({
                "user_id": user_id,
                "category": category,
                "symbol": symbol,
                "name": name,
                "trade_type": trade_type,
                "qty": qty,
                "price": price,
                "amount": amount,
                "source": source,
                "ai_signal": ai_signal,
                "ai_confidence": ai_confidence,
                "ai_reason": ai_reason,
            }).execute()
            logger.info(f"거래 기록({source}): {category} {symbol} {trade_type} {qty}개 @ {price}")
            return True
        except Exception as e:
            logger.error(f"거래 기록 실패({symbol}): {e}")
            return False

    def get_wallet_trades(
        self, user_id: int, category: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        시장 카테고리별 최근 거래 내역을 조회한다.

        Parameters:
            user_id: 사용자 ID
            category: 시장 카테고리
            limit: 조회 개수

        Returns:
            거래 내역 딕셔너리 리스트 (최신순)
        """
        try:
            result = (
                self.client.table("wallet_trades").select("*")
                .eq("user_id", user_id).eq("category", category)
                .order("executed_at", desc=True).limit(limit).execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"거래 내역 조회 실패({category}): {e}")
            return []

    # ========================================================================
    # Health Check
    # ========================================================================

    def health_check(self) -> bool:
        """
        Supabase 연결 상태 확인.

        Returns:
            연결 성공 여부
        """
        try:
            result = self.client.table("symbols").select("id").limit(1).execute()
            logger.info("✅ Supabase 연결 성공")
            return True
        except Exception as e:
            logger.error(f"❌ Supabase 연결 실패: {e}")
            return False
