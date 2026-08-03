# -*- coding: utf-8 -*-
"""
세션 기반 가상 포트폴리오 (페이퍼 트레이딩 MVP).

목적: Streamlit session_state에 저장되는 간단한 가상 매수/매도 기능을 제공한다.
      시장(한국/미국/암호화폐)별로 초기 가상자금을 배정하고, 사용자가 직접
      매수/매도 버튼을 눌러 즉시 체험할 수 있도록 한다.

설계 노트
---------
- 이 모듈은 "1-2개월 AI 자동매매 엔진"(Phase 5-2-3, 예정)의 전 단계로,
  포트폴리오 구조/계산 로직을 먼저 검증하기 위한 MVP다.
- 자동매매 엔진 단계에서는 이 로직을 Supabase 영구 저장 + 스케줄러 기반
  자동 실행으로 확장한다 (세션이 아니라 DB에 상태를 둔다).
- 통화 단위: 한국 주식은 원(KRW), 미국 주식/암호화폐는 달러(USD)로 각각
  독립적인 가상자금 100만을 배정한다 (실제 환율 변환은 하지 않는 단순화된 모델).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

INITIAL_BALANCE = 1_000_000.0

CURRENCY_SYMBOL = {
    "🇰🇷 한국 주식": "₩",
    "🇺🇸 미국 주식": "$",
    "₿ 암호화폐": "$",
}

CATEGORIES = list(CURRENCY_SYMBOL.keys())


def init_portfolio(session_state: dict) -> None:
    """
    session_state에 포트폴리오 구조가 없으면 초기화한다.

    Args:
        session_state: st.session_state (dict-like 객체).

    Returns:
        None (session_state를 직접 수정).
    """
    if "portfolio" not in session_state:
        session_state["portfolio"] = {
            category: {
                "cash": INITIAL_BALANCE,
                "holdings": {},  # symbol -> {"name":.., "qty":.., "avg_price":..}
                "history": [],   # 거래 기록 리스트
            }
            for category in CATEGORIES
        }


def buy(
    session_state: dict,
    category: str,
    symbol: str,
    name: str,
    price: float,
    amount: float,
) -> tuple[bool, str]:
    """
    가상 매수를 실행한다.

    Args:
        session_state: st.session_state.
        category: 시장 카테고리.
        symbol: 종목 심볼.
        name: 종목 표시 이름.
        price: 현재가.
        amount: 매수할 금액(현금 기준).

    Returns:
        (성공 여부, 결과 메시지) 튜플.
    """
    init_portfolio(session_state)
    book = session_state["portfolio"][category]

    if price <= 0:
        return False, "가격 정보가 올바르지 않습니다."
    if amount <= 0:
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

    return True, f"✅ {name} {qty:.4f}주 매수 완료 ({amount:,.0f} 사용)"


def sell(
    session_state: dict,
    category: str,
    symbol: str,
    price: float,
    qty: Optional[float] = None,
) -> tuple[bool, str]:
    """
    가상 매도를 실행한다.

    Args:
        session_state: st.session_state.
        category: 시장 카테고리.
        symbol: 종목 심볼.
        price: 현재가.
        qty: 매도할 수량. None이면 전량 매도.

    Returns:
        (성공 여부, 결과 메시지) 튜플.
    """
    init_portfolio(session_state)
    book = session_state["portfolio"][category]
    holding = book["holdings"].get(symbol)

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
