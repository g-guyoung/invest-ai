# -*- coding: utf-8 -*-
"""
Data source auto-detection registry.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fetcher.base_fetcher import BaseFetcher, FetcherError

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """Auto-detect and manage data sources."""

    _BINANCE_SYMBOL_MAP = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "XRP": "XRPUSDT",
        "SOL": "SOLUSDT",
        "ADA": "ADAUSDT",
        "DOGE": "DOGEUSDT",
        "BNB": "BNBUSDT",
        "LINK": "LINKUSDT",
        "MATIC": "MATICUSDT",
        "AVAX": "AVAXUSDT",
    }

    _PATTERNS = {
        r"^[A-Z0-9]{2,}USDT$": "binance",
        r"^[A-Z0-9]+-USD$": "yahoo",
        r"^\^[A-Z0-9]+$": "yahoo",
        r"^[A-Z0-9]{6}\.[A-Z]{2}$": "yahoo",
        r"^[A-Z]{1,5}$": "yahoo",
    }

    @staticmethod
    def detect_source(symbol: str) -> str:
        if not symbol:
            raise FetcherError("Symbol cannot be empty.")

        symbol_upper = symbol.upper()

        if symbol_upper in DataSourceRegistry._BINANCE_SYMBOL_MAP:
            return "binance"

        for pattern, source in DataSourceRegistry._PATTERNS.items():
            if re.match(pattern, symbol_upper):
                return source

        logger.warning(f"Could not auto-detect source for {symbol}. Trying Yahoo Finance.")
        return "yahoo"

    @staticmethod
    def normalize_symbol(symbol: str, source: str) -> str:
        if not symbol:
            return symbol
        symbol_upper = symbol.upper()
        if source == "binance" and symbol_upper in DataSourceRegistry._BINANCE_SYMBOL_MAP:
            return DataSourceRegistry._BINANCE_SYMBOL_MAP[symbol_upper]
        return symbol_upper

    @staticmethod
    def get_fetcher(source: Optional[str] = None, symbol: Optional[str] = None) -> BaseFetcher:
        if source is None:
            if symbol is None:
                raise FetcherError("Either source or symbol is required.")
            source = DataSourceRegistry.detect_source(symbol)

        source_lower = source.lower().strip()

        if source_lower == "binance":
            from src.fetcher.binance_fetcher import BinanceFetcher
            return BinanceFetcher()
        elif source_lower == "yahoo":
            from src.fetcher.yahoo_fetcher import YahooFetcher
            return YahooFetcher()
        else:
            raise FetcherError(f"Unknown data source: {source}")

    @staticmethod
    def get_ohlcv(
        symbol: str,
        interval: str = "1d",
        limit: int = 500,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source: Optional[str] = None,
    ):
        if source is None:
            source = DataSourceRegistry.detect_source(symbol)

        normalized_symbol = DataSourceRegistry.normalize_symbol(symbol, source)
        fetcher = DataSourceRegistry.get_fetcher(source=source, symbol=normalized_symbol)

        return fetcher.get_ohlcv(
            symbol=normalized_symbol,
            interval=interval,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )