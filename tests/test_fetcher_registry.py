# -*- coding: utf-8 -*-
"""
Tests for FetcherRegistry (multi-market routing).
"""

import pytest
from src.fetcher.fetcher_registry import FetcherRegistry
from src.fetcher.base_fetcher import FetcherError, BaseFetcher


class TestFetcherRegistryDetection:
    """Test market auto-detection."""

    def test_detect_binance_from_short_symbol(self):
        """Short crypto symbols should detect Binance."""
        assert FetcherRegistry.detect_market("BTC") == "binance"
        assert FetcherRegistry.detect_market("ETH") == "binance"
        assert FetcherRegistry.detect_market("XRP") == "binance"

    def test_detect_binance_from_full_pair(self):
        """Full USDT pairs should detect Binance."""
        assert FetcherRegistry.detect_market("BTCUSDT") == "binance"
        assert FetcherRegistry.detect_market("ETHUSDT") == "binance"

    def test_detect_yahoo_from_us_ticker(self):
        """US tickers should detect Yahoo."""
        assert FetcherRegistry.detect_market("AAPL") == "yahoo"
        assert FetcherRegistry.detect_market("TSLA") == "yahoo"
        assert FetcherRegistry.detect_market("GOOGL") == "yahoo"

    def test_detect_yahoo_from_korean_stock(self):
        """Korean stocks (.KS) should detect Yahoo."""
        assert FetcherRegistry.detect_market("005930.KS") == "yahoo"
        assert FetcherRegistry.detect_market("000660.KS") == "yahoo"

    def test_detect_yahoo_from_index(self):
        """Indices should detect Yahoo."""
        assert FetcherRegistry.detect_market("^GSPC") == "yahoo"
        assert FetcherRegistry.detect_market("^DJI") == "yahoo"

    def test_detect_market_empty_symbol_raises(self):
        """Empty symbol should raise FetcherError."""
        with pytest.raises(FetcherError):
            FetcherRegistry.detect_market("")

    def test_detect_market_unknown_defaults_to_yahoo(self):
        """Unknown symbols should default to Yahoo."""
        market = FetcherRegistry.detect_market("UNKNOWN_SYMBOL")
        assert market == "yahoo"


class TestFetcherRegistryNormalization:
    """Test symbol normalization."""

    def test_normalize_crypto_short_to_full(self):
        """Short crypto symbols should normalize to full USDT pairs."""
        assert FetcherRegistry.normalize_symbol("BTC", "binance") == "BTCUSDT"
        assert FetcherRegistry.normalize_symbol("ETH", "binance") == "ETHUSDT"
        assert FetcherRegistry.normalize_symbol("XRP", "binance") == "XRPUSDT"

    def test_normalize_crypto_uppercase(self):
        """Crypto symbols should be uppercase."""
        assert FetcherRegistry.normalize_symbol("btc", "binance") == "BTCUSDT"
        assert FetcherRegistry.normalize_symbol("eth", "binance") == "ETHUSDT"

    def test_normalize_full_pair_unchanged(self):
        """Full pairs should remain unchanged."""
        assert FetcherRegistry.normalize_symbol("BTCUSDT", "binance") == "BTCUSDT"

    def test_normalize_yahoo_stock_uppercase(self):
        """Yahoo stocks should be uppercase."""
        assert FetcherRegistry.normalize_symbol("aapl", "yahoo") == "AAPL"
        assert FetcherRegistry.normalize_symbol("tsla", "yahoo") == "TSLA"

    def test_normalize_korean_stock_unchanged(self):
        """Korean stocks should remain unchanged."""
        assert FetcherRegistry.normalize_symbol("005930.KS", "yahoo") == "005930.KS"

    def test_normalize_empty_symbol(self):
        """Empty symbol should return empty."""
        assert FetcherRegistry.normalize_symbol("", "binance") == ""


class TestFetcherRegistryGetFetcher:
    """Test fetcher instance creation."""

    def test_get_binance_fetcher(self):
        """Should return BinanceFetcher for Binance market."""
        fetcher = FetcherRegistry.get_fetcher(market="binance")
        assert fetcher is not None
        assert fetcher.source_name == "BinanceFetcher"

    def test_get_yahoo_fetcher(self):
        """Should return YahooFetcher for Yahoo market."""
        fetcher = FetcherRegistry.get_fetcher(market="yahoo")
        assert fetcher is not None
        assert fetcher.source_name == "YahooFetcher"

    def test_get_fetcher_auto_detect(self):
        """Should auto-detect market from symbol."""
        fetcher_btc = FetcherRegistry.get_fetcher(symbol="BTC")
        assert fetcher_btc.source_name == "BinanceFetcher"

        fetcher_aapl = FetcherRegistry.get_fetcher(symbol="AAPL")
        assert fetcher_aapl.source_name == "YahooFetcher"

    def test_get_fetcher_no_market_no_symbol_raises(self):
        """Should raise if neither market nor symbol provided."""
        with pytest.raises(FetcherError):
            FetcherRegistry.get_fetcher()

    def test_get_fetcher_unknown_market_raises(self):
        """Should raise for unknown market."""
        with pytest.raises(FetcherError):
            FetcherRegistry.get_fetcher(market="unknown")

    def test_get_fetcher_case_insensitive(self):
        """Market names should be case-insensitive."""
        fetcher1 = FetcherRegistry.get_fetcher(market="BINANCE")
        fetcher2 = FetcherRegistry.get_fetcher(market="binance")
        assert fetcher1.source_name == fetcher2.source_name


class TestFetcherRegistryOHLCV:
    """Test OHLCV data fetching."""

    def test_ohlcv_auto_detect_market(self):
        """Should auto-detect market and fetch data."""
        # This test would require mocking Binance/Yahoo APIs
        # Placeholder for integration test
        pass

    def test_list_supported_symbols(self):
        """Should return dict of supported symbols by market."""
        symbols = FetcherRegistry.list_supported_symbols()
        assert "binance" in symbols
        assert "yahoo" in symbols
        assert "BTC" in symbols["binance"]
        assert "AAPL" in symbols["yahoo"]


class TestFetcherRegistryIntegration:
    """Integration tests."""

    def test_workflow_crypto_to_binance(self):
        """Full workflow: BTC symbol -> Binance -> BTCUSDT."""
        market = FetcherRegistry.detect_market("BTC")
        assert market == "binance"

        normalized = FetcherRegistry.normalize_symbol("BTC", market)
        assert normalized == "BTCUSDT"

        fetcher = FetcherRegistry.get_fetcher(market=market)
        assert fetcher.source_name == "BinanceFetcher"

    def test_workflow_stock_to_yahoo(self):
        """Full workflow: AAPL symbol -> Yahoo -> AAPL."""
        market = FetcherRegistry.detect_market("AAPL")
        assert market == "yahoo"

        normalized = FetcherRegistry.normalize_symbol("AAPL", market)
        assert normalized == "AAPL"

        fetcher = FetcherRegistry.get_fetcher(market=market)
        assert fetcher.source_name == "YahooFetcher"

    def test_workflow_korean_stock_to_yahoo(self):
        """Full workflow: Korean stock -> Yahoo."""
        market = FetcherRegistry.detect_market("005930.KS")
        assert market == "yahoo"

        normalized = FetcherRegistry.normalize_symbol("005930.KS", market)
        assert normalized == "005930.KS"

        fetcher = FetcherRegistry.get_fetcher(market=market)
        assert fetcher.source_name == "YahooFetcher"
