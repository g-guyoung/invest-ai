# -*- coding: utf-8 -*-
"""
Fetcher registry for multi-market auto-detection and routing.
Supports: Crypto (Binance), US Stocks (Yahoo), Korean Stocks (Yahoo).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.fetcher.base_fetcher import BaseFetcher, FetcherError

logger = logging.getLogger(__name__)


class FetcherRegistry:
    """
    Multi-market fetcher registry with auto-detection and routing.

    Supported markets:
    - Crypto: BTC, ETH, XRP, SOL, ADA, DOGE, BNB, LINK, MATIC, AVAX (Binance USDT)
    - US Stocks: AAPL, TSLA, MSFT, etc. (Yahoo)
    - Korean Stocks: Samsung (005930.KS), LG (066570.KS), etc. (Yahoo)
    """

    # Crypto symbols (Binance USDT pairs)
    CRYPTO_SYMBOLS = {
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

    # Pattern matching for market detection
    MARKET_PATTERNS = {
        # Binance crypto pairs (e.g., BTCUSDT, ETHUSDT)
        r"^[A-Z0-9]{2,}USDT$": "binance",
        # Korean stocks with .KS suffix (e.g., 005930.KS)
        r"^[0-9]{6}\.KS$": "yahoo",
        r"^[A-Z0-9]+\.KS$": "yahoo",
        # Yahoo US stocks
        r"^[A-Z0-9]+-USD$": "yahoo",
        r"^\^[A-Z0-9]+$": "yahoo",  # Indices
        r"^[A-Z0-9]{6}\.[A-Z]{2}$": "yahoo",  # TSE, HKG, etc.
        r"^[A-Z]{1,5}$": "yahoo",  # US ticker (1-5 chars)
    }

    @staticmethod
    def detect_market(symbol: str) -> str:
        """
        Auto-detect market from symbol.

        Parameters:
            symbol: Stock/crypto symbol (e.g., "BTC", "AAPL", "005930.KS")

        Returns:
            Market name ("binance" or "yahoo")

        Raises:
            FetcherError: If symbol is empty or invalid.
        """
        if not symbol:
            raise FetcherError("Symbol cannot be empty.")

        symbol_upper = symbol.upper()

        # Check crypto symbol map
        if symbol_upper in FetcherRegistry.CRYPTO_SYMBOLS:
            return "binance"

        # Pattern matching
        for pattern, market in FetcherRegistry.MARKET_PATTERNS.items():
            if re.match(pattern, symbol_upper):
                return market

        # Default to Yahoo Finance
        logger.warning(
            f"Could not auto-detect market for '{symbol}'. "
            f"Defaulting to Yahoo Finance."
        )
        return "yahoo"

    @staticmethod
    def normalize_symbol(symbol: str, market: str) -> str:
        """
        Normalize symbol for the target market.

        Parameters:
            symbol: Original symbol
            market: Target market ("binance" or "yahoo")

        Returns:
            Normalized symbol for the market.
        """
        if not symbol:
            return symbol

        symbol_upper = symbol.upper()

        # Crypto: map short names to full USDT pairs
        if market == "binance":
            if symbol_upper in FetcherRegistry.CRYPTO_SYMBOLS:
                return FetcherRegistry.CRYPTO_SYMBOLS[symbol_upper]
            # Assume it's already a full pair like BTCUSDT
            return symbol_upper

        # Yahoo: keep as-is or uppercase
        return symbol_upper

    @staticmethod
    def get_fetcher(
        market: Optional[str] = None, symbol: Optional[str] = None
    ) -> BaseFetcher:
        """
        Get fetcher instance for the specified market.

        Parameters:
            market: Market name ("binance", "yahoo"). If None, auto-detect from symbol.
            symbol: Symbol for auto-detection.

        Returns:
            BaseFetcher instance.

        Raises:
            FetcherError: If market is unknown or neither market nor symbol provided.
        """
        if market is None:
            if symbol is None:
                raise FetcherError("Either market or symbol is required.")
            market = FetcherRegistry.detect_market(symbol)

        market_lower = market.lower().strip()

        if market_lower == "binance":
            from src.fetcher.binance_fetcher import BinanceFetcher

            return BinanceFetcher()
        elif market_lower == "yahoo":
            from src.fetcher.yahoo_fetcher import YahooFetcher

            return YahooFetcher()
        else:
            raise FetcherError(f"Unknown market: {market_lower}")

    @staticmethod
    def get_ohlcv(
        symbol: str,
        interval: str = "1d",
        limit: int = 500,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        market: Optional[str] = None,
    ) -> "pd.DataFrame":
        """
        Fetch OHLCV data for any market.

        Parameters:
            symbol: Stock/crypto symbol.
            interval: Candle interval ("1d", "1h", "15m", etc.).
            limit: Number of candles to fetch.
            start_date: Start date (YYYY-MM-DD). For Binance only.
            end_date: End date (YYYY-MM-DD). For Binance only.
            market: Market name. If None, auto-detect from symbol.

        Returns:
            DataFrame with columns [open_time, open, high, low, close, volume, symbol].
        """
        if market is None:
            market = FetcherRegistry.detect_market(symbol)

        normalized_symbol = FetcherRegistry.normalize_symbol(symbol, market)
        fetcher = FetcherRegistry.get_fetcher(market=market, symbol=normalized_symbol)

        return fetcher.get_ohlcv(
            symbol=normalized_symbol,
            interval=interval,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def list_supported_symbols() -> dict:
        """
        List all supported symbols by market.

        Returns:
            Dictionary with market names as keys and symbol lists as values.
        """
        return {
            "binance": list(FetcherRegistry.CRYPTO_SYMBOLS.keys()),
            "yahoo": [
                "AAPL",
                "TSLA",
                "MSFT",
                "GOOGL",
                "AMZN",  # US Stocks
                "005930.KS",
                "066570.KS",
                "035720.KS",  # Korean Stocks
            ],
        }
