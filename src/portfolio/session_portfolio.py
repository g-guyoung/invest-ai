# -*- coding: utf-8 -*-
"""
가상 포트폴리오 (페이퍼 트레이딩).

목적: 시장(한국/미국/암호화폐)별로 초기 가상자금을 배정하고, 수동 매수/매도
      버튼(Streamlit) 또는 자동매매 엔진(src.trading.auto_trader) 양쪽에서
      동일한 로직으로 가상 매매를 체결할 수 있도록 한다.

설계 노트
---------
- 이 모듈의 계산 로직(buy/sell/get_summary)은 상태 저장 방식(세션 전용인지
  Supabase 영구 저장인지)을 전혀 몰라도 되도록 설계했다 (Repository Pattern,
  src.portfolio.repository_factory.get_repository()가 실제 저장소를 결정한다).
  - Supabase가 설정 안 돼 있으면: 기존과 동일하게 세션에서만 동작 (새로고침 시 초기화).
  - Supabase가 설정돼 있으면: 매수/매도할 때마다 자동으로 영구 저장된다.
- session_state 파라미터는 "dict-like"이기만 하면 되므로, Streamlit 없이도
  plain dict를 넘겨 자동매매 엔진에서 그대로 재사용할 수 있다.
- 통화 단위: 한국 주식은 원(KRW), 미국 주식/암호화폐는 달러(USD)로 각각
  독립적인 가상자금 100만을 배정한다 (실제 환율 변환은 하지 않는 단순화된 모델).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from src.portfolio.constants import CATEGORIES, CURRENCY_SYMBOL, INITIAL_BALANCE
from src.portfolio.repository_factory import get_repository

# 하위 호환을 위해 기존 이름으로도 그대로 노출한다 (streamlit_app.py가
# sp.CATEGORIES / sp.CURRENCY_SYMBOL / sp.INITIAL_BALANCE로 참조 중).
__all__ = [
    "INITIAL_BALANCE", "CURRENCY_SYMBOL", "CATEGORIES",
    "init_portfolio", "buy", "sell", "get_summary",
]


def init_portfolio(session_state: dict) -> None:
    """
    session_state에 포트폴리오 구조가 없으면 초기화(또는 저장소에서 복원)한다.

    Args:
        session_state: st.session_state (dict-like 객체) 또는 plain dict.

    Returns:
        None (session_state를 직접 수정).
    """
    if "portfolio" not in session_state:
        get_repository().load_into(session_state)



def _is_valid_price(price: float) -> bool:
    """체결 가격이 유한한 양수인지 검사한다.

    `price <= 0` 만으로는 NaN을 걸러내지 못한다(NaN과의 비교는 항상 False).

    Args:
        price: 검사할 가격.

    Returns:
        유한한 양수면 True.

    Examples:
        >>> _is_valid_price(10.0), _is_valid_price(float("nan")), _is_valid_price(0)
        (True, False, False)
    """
    try:
        return math.isfinite(price) and price > 0
    except TypeError:
        return False

def buy(
    session_state: dict,
    category: str,
    symbol: str,
    name: str,
    price: float,
    amount: float,
    source: str = "MANUAL",
    ai_signal: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    ai_reason: Optional[str] = None,
) -> tuple[bool, str]:
    """
    가상 매수를 실행한다.

    Args:
        session_state: st.session_state 또는 plain dict.
        category: 시장 카테고리.
        symbol: 종목 심볼.
        name: 종목 표시 이름.
        price: 현재가.
        amount: 매수할 금액(현금 기준).
        source: "MANUAL"(사용자 수동 거래) 또는 "AUTO_AI"(자동매매 엔진).
        ai_signal: 자동매매인 경우 AI 신호 문자열, 감사 추적용.
        ai_confidence: 자동매매인 경우 AI 신뢰도(0.0~1.0).
        ai_reason: 자동매매인 경우 AI 판단 근거.

    Returns:
        (성공 여부, 결과 메시지) 튜플.
    """
    init_portfolio(session_state)
    book = session_state["portfolio"][category]

    if not _is_valid_price(price):
        return False, "가격 정보가 올바르지 않습니다."
    if not math.isfinite(amount) or amount <= 0:
        return False, "매수 금액은 0보다 커야 합니다."
    if amount > book["cash"]:
        return False, f"현금이 부족합니다. (보유 현금: {book['cash']:,.0f})"

    qty = amount / price
    existing = book["holdings"].get(symbol)

    if existing:
        total_qty = existing["qty"] + qty
        total_cost = existing["qty"] * existing["avg_price"] + amount
        existing["qty"] = total_qty
        existing["avg_price"] = total_cost / total_qty
    else:
        book["holdings"][symbol] = {"name": name, "qty": qty, "avg_price": price}

    book["cash"] -= amount
    book["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol, "type": "BUY", "qty": qty, "price": price, "amount": amount,
    })

    get_repository().record_trade(
        category, symbol, name, "BUY", qty, price, amount, book,
        source=source, ai_signal=ai_signal, ai_confidence=ai_confidence, ai_reason=ai_reason,
    )

    return True, f"✅ {name} {qty:.4f}주 매수 완료 ({amount:,.0f} 사용)"


def sell(
    session_state: dict,
    category: str,
    symbol: str,
    price: float,
    qty: Optional[float] = None,
    source: str = "MANUAL",
    ai_signal: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    ai_reason: Optional[str] = None,
) -> tuple[bool, str]:
    """
    가상 매도를 실행한다.

    Args:
        session_state: st.session_state 또는 plain dict.
        category: 시장 카테고리.
        symbol: 종목 심볼.
        price: 현재가.
        qty: 매도할 수량. None이면 전량 매도.
        source: "MANUAL"(사용자 수동 거래) 또는 "AUTO_AI"(자동매매 엔진).
        ai_signal: 자동매매인 경우 AI 신호 문자열, 감사 추적용.
        ai_confidence: 자동매매인 경우 AI 신뢰도(0.0~1.0).
        ai_reason: 자동매매인 경우 AI 판단 근거.

    Returns:
        (성공 여부, 결과 메시지) 튜플.
    """
    init_portfolio(session_state)
    book = session_state["portfolio"][category]
    holding = book["holdings"].get(symbol)

    # NaN/0 가격으로 매도하면 보유분만 사라지고 현금이 들어오지 않는다 (2026-09-04 SOFI 사고).
    if not _is_valid_price(price):
        return False, "가격 정보가 올바르지 않습니다."

    if not holding or holding["qty"] <= 0:
        return False, "보유하고 있지 않은 종목입니다."

    sell_qty = qty if qty is not None else holding["qty"]
    if sell_qty > holding["qty"]:
        return False, "보유 수량보다 많이 매도할 수 없습니다."

    proceeds = sell_qty * price
    holding["qty"] -= sell_qty
    book["cash"] += proceeds

    name = holding["name"]
    if holding["qty"] <= 1e-9:
        del book["holdings"][symbol]

    book["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol, "type": "SELL", "qty": sell_qty, "price": price, "amount": proceeds,
    })

    get_repository().record_trade(
        category, symbol, name, "SELL", sell_qty, price, proceeds, book,
        source=source, ai_signal=ai_signal, ai_confidence=ai_confidence, ai_reason=ai_reason,
    )

    return True, f"✅ {name} {sell_qty:.4f}주 매도 완료 ({proceeds:,.0f} 회수)"


def get_summary(session_state: dict, category: str, current_prices: dict) -> dict:
    """
    포트폴리오 요약 정보를 계산한다.

    Args:
        session_state: st.session_state.
        category: 시장 카테고리.
        current_prices: {symbol: 현재가} 딕셔너리.

    Returns:
        {"cash":.., "holdings_value":.., "total":.., "pnl":.., "pnl_pct":.., "holdings":[...]}
    """
    init_portfolio(session_state)
    book = session_state["portfolio"][category]

    holdings_rows = []
    holdings_value = 0.0
    for symbol, h in book["holdings"].items():
        current_price = current_prices.get(symbol, h["avg_price"])
        value = h["qty"] * current_price
        pnl = value - (h["qty"] * h["avg_price"])
        pnl_pct = (pnl / (h["qty"] * h["avg_price"]) * 100) if h["avg_price"] > 0 else 0
        holdings_value += value
        holdings_rows.append({
            "종목": f"{symbol} ({h['name']})",
            "수량": h["qty"],
            "평균단가": h["avg_price"],
            "현재가": current_price,
            "평가금액": value,
            "손익": pnl,
            "손익률": pnl_pct,
        })

    total = book["cash"] + holdings_value
    pnl = total - INITIAL_BALANCE
    pnl_pct = (pnl / INITIAL_BALANCE * 100) if INITIAL_BALANCE > 0 else 0

    return {
        "cash": book["cash"],
        "holdings_value": holdings_value,
        "total": total,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "holdings": holdings_rows,
        "history": list(reversed(book["history"][-20:])),
    }
