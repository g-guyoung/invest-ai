# -*- coding: utf-8 -*-
"""
심볼 카탈로그.

목적: 대시보드에서 사용하는 종목 목록을 한 곳에서 관리.
      각 종목에 대해 표시 이름, TradingView 심볼(차트용), Yahoo 심볼(데이터 수집용)을 매핑한다.

설계 노트
---------
- TradingView 위젯은 브라우저에서 직접 TradingView 서버와 통신하므로
  Streamlit Cloud 서버의 아웃바운드 API 제한(Binance 451 에러 등)과 무관하게 동작한다.
- 데이터 수집(AI 분석용)은 Yahoo Finance로 통일한다. 암호화폐도 Binance 대신
  Yahoo의 "-USD" 심볼(BTC-USD 등)을 사용해 클라우드 환경에서의 API 차단 문제를 회피한다.
"""

from __future__ import annotations

from typing import Dict, TypedDict


class SymbolInfo(TypedDict):
    name: str
    tv_symbol: str      # TradingView 차트 심볼 (예: "NASDAQ:AAPL")
    yahoo_symbol: str   # Yahoo Finance 데이터 수집 심볼 (예: "AAPL")


# ============================================================================
# 한국 주식 (KRX)
# ============================================================================

KOREAN_STOCKS: Dict[str, SymbolInfo] = {
    "005930.KS": {"name": "삼성전자", "tv_symbol": "KRX:005930", "yahoo_symbol": "005930.KS"},
    "000660.KS": {"name": "SK하이닉스", "tv_symbol": "KRX:000660", "yahoo_symbol": "000660.KS"},
    "066570.KS": {"name": "LG전자", "tv_symbol": "KRX:066570", "yahoo_symbol": "066570.KS"},
    "035420.KS": {"name": "네이버", "tv_symbol": "KRX:035420", "yahoo_symbol": "035420.KS"},
    "035720.KS": {"name": "카카오", "tv_symbol": "KRX:035720", "yahoo_symbol": "035720.KS"},
    "005380.KS": {"name": "현대차", "tv_symbol": "KRX:005380", "yahoo_symbol": "005380.KS"},
    "051910.KS": {"name": "LG화학", "tv_symbol": "KRX:051910", "yahoo_symbol": "051910.KS"},
    "207940.KS": {"name": "삼성바이오로직스", "tv_symbol": "KRX:207940", "yahoo_symbol": "207940.KS"},
    "005490.KS": {"name": "POSCO홀딩스", "tv_symbol": "KRX:005490", "yahoo_symbol": "005490.KS"},
    "105560.KS": {"name": "KB금융", "tv_symbol": "KRX:105560", "yahoo_symbol": "105560.KS"},
}

# ============================================================================
# 미국 주식 (NASDAQ / NYSE)
# ============================================================================

US_STOCKS: Dict[str, SymbolInfo] = {
    "AAPL": {"name": "Apple", "tv_symbol": "NASDAQ:AAPL", "yahoo_symbol": "AAPL"},
    "TSLA": {"name": "Tesla", "tv_symbol": "NASDAQ:TSLA", "yahoo_symbol": "TSLA"},
    "MSFT": {"name": "Microsoft", "tv_symbol": "NASDAQ:MSFT", "yahoo_symbol": "MSFT"},
    "GOOGL": {"name": "Alphabet", "tv_symbol": "NASDAQ:GOOGL", "yahoo_symbol": "GOOGL"},
    "AMZN": {"name": "Amazon", "tv_symbol": "NASDAQ:AMZN", "yahoo_symbol": "AMZN"},
    "NVDA": {"name": "NVIDIA", "tv_symbol": "NASDAQ:NVDA", "yahoo_symbol": "NVDA"},
    "META": {"name": "Meta", "tv_symbol": "NASDAQ:META", "yahoo_symbol": "META"},
    "NFLX": {"name": "Netflix", "tv_symbol": "NASDAQ:NFLX", "yahoo_symbol": "NFLX"},
}

# ============================================================================
# 암호화폐 (데이터는 Yahoo "-USD", 차트는 Binance 피드)
# ============================================================================

CRYPTO: Dict[str, SymbolInfo] = {
    "BTC": {"name": "Bitcoin", "tv_symbol": "BINANCE:BTCUSDT", "yahoo_symbol": "BTC-USD"},
    "ETH": {"name": "Ethereum", "tv_symbol": "BINANCE:ETHUSDT", "yahoo_symbol": "ETH-USD"},
    "XRP": {"name": "Ripple", "tv_symbol": "BINANCE:XRPUSDT", "yahoo_symbol": "XRP-USD"},
    "SOL": {"name": "Solana", "tv_symbol": "BINANCE:SOLUSDT", "yahoo_symbol": "SOL-USD"},
    "ADA": {"name": "Cardano", "tv_symbol": "BINANCE:ADAUSDT", "yahoo_symbol": "ADA-USD"},
    "DOGE": {"name": "Dogecoin", "tv_symbol": "BINANCE:DOGEUSDT", "yahoo_symbol": "DOGE-USD"},
    "BNB": {"name": "BNB", "tv_symbol": "BINANCE:BNBUSDT", "yahoo_symbol": "BNB-USD"},
    "LINK": {"name": "Chainlink", "tv_symbol": "BINANCE:LINKUSDT", "yahoo_symbol": "LINK-USD"},
    "MATIC": {"name": "Polygon", "tv_symbol": "BINANCE:MATICUSDT", "yahoo_symbol": "MATIC-USD"},
    "AVAX": {"name": "Avalanche", "tv_symbol": "BINANCE:AVAXUSDT", "yahoo_symbol": "AVAX-USD"},
}

# ============================================================================
# 시장 카테고리 통합 카탈로그
# ============================================================================

MARKET_CATALOG: Dict[str, Dict[str, SymbolInfo]] = {
    "🇰🇷 한국 주식": KOREAN_STOCKS,
    "🇺🇸 미국 주식": US_STOCKS,
    "₿ 암호화폐": CRYPTO,
}

DEFAULT_SYMBOLS: Dict[str, list] = {
    "🇰🇷 한국 주식": ["005930.KS"],
    "🇺🇸 미국 주식": ["AAPL"],
    "₿ 암호화폐": ["BTC"],
}


def get_symbol_info(category: str, symbol: str) -> SymbolInfo:
    """
    특정 카테고리의 심볼 정보를 조회한다.

    Args:
        category: 시장 카테고리 (MARKET_CATALOG의 키)
        symbol: 종목 심볼

    Returns:
        SymbolInfo 딕셔너리 (name, tv_symbol, yahoo_symbol)

    Raises:
        KeyError: 카테고리 또는 심볼을 찾을 수 없는 경우
    """
    return MARKET_CATALOG[category][symbol]


def format_symbol_label(category: str, symbol: str) -> str:
    """
    멀티셀렉트 등에서 사용할 사람이 읽기 좋은 라벨을 생성한다.

    Args:
        category: 시장 카테고리
        symbol: 종목 심볼

    Returns:
        "005930.KS - 삼성전자" 형식의 문자열
    """
    info = get_symbol_info(category, symbol)
    return f"{symbol} ({info['name']})"
