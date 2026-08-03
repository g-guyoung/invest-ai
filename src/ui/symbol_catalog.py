# -*- coding: utf-8 -*-
"""
심볼 정규화 유틸리티.

목적: 사용자가 자유롭게 입력한 종목 코드/티커를 각 시장에 맞는
      Yahoo Finance 심볼로 정규화한다 (고정 목록 없이 검색 지원).

설계 노트
---------
- 사용자가 "005930", "005930.KS", "삼성전자" 등 다양한 형태로 입력해도
  Yahoo Finance가 이해하는 표준 심볼로 변환한다.
- 회사명은 알려진 경우에만 참고용으로 표시하고, 모르는 종목도 코드만으로
  자유롭게 조회 가능하도록 한다 (검색을 막지 않는다).
"""

from __future__ import annotations

import re
from typing import Optional

# 참고용 회사명 매핑 (알려진 경우 표시용, 모르면 코드 그대로 표시)
_KNOWN_KR_NAMES = {
    "005930": "삼성전자", "000660": "SK하이닉스", "066570": "LG전자",
    "035420": "네이버", "035720": "카카오", "005380": "현대차",
    "051910": "LG화학", "207940": "삼성바이오로직스", "005490": "POSCO홀딩스",
    "105560": "KB금융", "033780": "KT&G", "096770": "SK이노베이션",
    "003670": "포스코퓨처엠", "068270": "셀트리온", "323410": "카카오뱅크",
}

_KNOWN_US_NAMES = {
    "AAPL": "Apple", "TSLA": "Tesla", "MSFT": "Microsoft",
    "GOOGL": "Alphabet", "AMZN": "Amazon", "NVDA": "NVIDIA",
    "META": "Meta", "NFLX": "Netflix",
}

_KNOWN_CRYPTO_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "XRP": "Ripple", "SOL": "Solana",
    "ADA": "Cardano", "DOGE": "Dogecoin", "BNB": "BNB", "LINK": "Chainlink",
    "MATIC": "Polygon", "AVAX": "Avalanche",
}

CATEGORIES = ["🇰🇷 한국 주식", "🇺🇸 미국 주식", "₿ 암호화폐"]

CATEGORY_PLACEHOLDER = {
    "🇰🇷 한국 주식": "예: 005930, 000660, 033780",
    "🇺🇸 미국 주식": "예: AAPL, TSLA, NVDA",
    "₿ 암호화폐": "예: BTC, ETH, SOL",
}


def normalize_symbol(raw_input: str, category: str) -> Optional[dict]:
    """
    사용자 입력을 시장별 표준 심볼로 정규화한다.

    Args:
        raw_input: 사용자가 입력한 원본 문자열 (예: "005930", "AAPL", "btc").
        category: 시장 카테고리 ("🇰🇷 한국 주식", "🇺🇸 미국 주식", "₿ 암호화폐").

    Returns:
        {"symbol": 표시용 심볼, "yahoo_symbol": Yahoo 조회용 심볼, "name": 표시 이름}
        입력이 비어있으면 None.
    """
    text = raw_input.strip().upper()
    if not text:
        return None

    if category == "🇰🇷 한국 주식":
        # 순수 숫자(6자리) -> .KS 접미사 추가
        code = re.sub(r"\.KS$", "", text)
        if not re.match(r"^\d{6}$", code):
            # 6자리 숫자가 아니면 그대로 시도 (사용자가 다른 형식을 입력했을 수 있음)
            yahoo_symbol = text if text.endswith(".KS") else f"{text}.KS"
            code = re.sub(r"\.KS$", "", yahoo_symbol)
        else:
            yahoo_symbol = f"{code}.KS"
        name = _KNOWN_KR_NAMES.get(code, code)
        return {"symbol": yahoo_symbol, "yahoo_symbol": yahoo_symbol, "name": name}

    elif category == "🇺🇸 미국 주식":
        name = _KNOWN_US_NAMES.get(text, text)
        return {"symbol": text, "yahoo_symbol": text, "name": name}

    elif category == "₿ 암호화폐":
        # "BTC", "BTC-USD", "BTCUSDT" 등 다양한 입력을 base 심볼로 정리
        base = re.sub(r"(-USD|USDT|USD)$", "", text)
        yahoo_symbol = f"{base}-USD"
        name = _KNOWN_CRYPTO_NAMES.get(base, base)
        return {"symbol": base, "yahoo_symbol": yahoo_symbol, "name": name}

    return None


def parse_symbol_list(raw_text: str, category: str) -> list[dict]:
    """
    쉼표로 구분된 여러 심볼 입력을 파싱하여 정규화한다.

    Args:
        raw_text: "AAPL, TSLA, 005930" 형태의 쉼표 구분 문자열.
        category: 시장 카테고리.

    Returns:
        정규화된 심볼 정보 딕셔너리 리스트 (중복 제거).
    """
    if not raw_text:
        return []

    seen = set()
    results = []
    for part in raw_text.split(","):
        info = normalize_symbol(part, category)
        if info and info["yahoo_symbol"] not in seen:
            seen.add(info["yahoo_symbol"])
            results.append(info)
    return results
