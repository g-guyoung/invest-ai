# -*- coding: utf-8 -*-
"""
Tests for improved YahooFetcher with Korean stock support.
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from src.fetcher.yahoo_fetcher import YahooFetcher
from src.fetcher.base_fetcher import FetcherError


class TestYahooFetcherKoreanSymbols:
    """Test Korean stock symbol normalization."""

    def test_normalize_korean_samsung(self):
        """Should normalize Samsung symbol."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_korean_symbol("Samsung") == "005930.KS"
        assert fetcher._normalize_korean_symbol("SAMSUNG") == "005930.KS"
        assert fetcher._normalize_korean_symbol("samsung") == "005930.KS"

    def test_normalize_korean_sk_hynix(self):
        """Should normalize SK Hynix symbol."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_korean_symbol("SK") == "000660.KS"
        assert fetcher._normalize_korean_symbol("SK_HYNIX") == "000660.KS"

    def test_normalize_korean_full_code(self):
        """Should accept full Korean codes."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_korean_symbol("005930.KS") == "005930.KS"
        assert fetcher._normalize_korean_symbol("000660.KS") == "000660.KS"

    def test_normalize_korean_unknown_symbol(self):
        """Unknown Korean symbols should remain unchanged."""
        fetcher = YahooFetcher()
        result = fetcher._normalize_korean_symbol("UNKNOWN_SYMBOL")
        assert result == "UNKNOWN_SYMBOL"

    def test_normalize_korean_case_insensitive(self):
        """Korean symbol normalization should be case-insensitive."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_korean_symbol("samsung") == "005930.KS"
        assert fetcher._normalize_korean_symbol("SAMSUNG") == "005930.KS"
        assert fetcher._normalize_korean_symbol("SaMsUnG") == "005930.KS"


class TestYahooFetcherOHLCV:
    """Test OHLCV data fetching."""

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_get_ohlcv_us_stock(self, mock_yf):
        """Should fetch US stock OHLCV data."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker

        # Mock historical data
        mock_history = pd.DataFrame({
            "Open": [150.0, 151.0],
            "High": [152.0, 153.0],
            "Low": [149.0, 150.0],
            "Close": [151.5, 152.5],
            "Volume": [1000000.0, 1100000.0],
        })
        mock_history.index = pd.date_range("2021-01-01", periods=2)
        mock_history.index.name = "Date"

        mock_ticker.history.return_value = mock_history

        fetcher = YahooFetcher()
        df = fetcher.get_ohlcv(symbol="AAPL", limit=100)

        assert not df.empty
        assert "open_time" in df.columns
        assert "close" in df.columns
        assert "symbol" in df.columns
        assert df["symbol"].iloc[0] == "AAPL"

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_get_ohlcv_korean_stock(self, mock_yf):
        """Should fetch Korean stock OHLCV data."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker

        # Mock historical data
        mock_history = pd.DataFrame({
            "Open": [70000.0, 71000.0],
            "High": [72000.0, 73000.0],
            "Low": [69000.0, 70000.0],
            "Close": [71500.0, 72500.0],
            "Volume": [1000000.0, 1100000.0],
        })
        mock_history.index = pd.date_range("2021-01-01", periods=2)
        mock_history.index.name = "Date"

        mock_ticker.history.return_value = mock_history

        fetcher = YahooFetcher()
        # Test with normalized symbol
        df = fetcher.get_ohlcv(symbol="Samsung", limit=100)

        assert not df.empty
        # Should have called Ticker with normalized symbol
        mock_yf.Ticker.assert_called()

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_get_ohlcv_with_date_range(self, mock_yf):
        """Should fetch data with date range."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker

        mock_history = pd.DataFrame({
            "Open": [150.0],
            "High": [152.0],
            "Low": [149.0],
            "Close": [151.5],
            "Volume": [1000000.0],
        })
        mock_history.index = pd.date_range("2021-01-01", periods=1)
        mock_history.index.name = "Date"

        mock_ticker.history.return_value = mock_history

        fetcher = YahooFetcher()
        df = fetcher.get_ohlcv(
            symbol="AAPL",
            start_date="2021-01-01",
            end_date="2021-01-31",
        )

        assert not df.empty
        mock_ticker.history.assert_called_with(
            start="2021-01-01", end="2021-01-31", interval="1d"
        )

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_get_ohlcv_limit_truncation(self, mock_yf):
        """Should return only up to limit records."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker

        # Create more data than limit
        mock_history = pd.DataFrame({
            "Open": list(range(100, 110)),
            "High": list(range(110, 120)),
            "Low": list(range(90, 100)),
            "Close": list(range(105, 115)),
            "Volume": [1000000.0] * 10,
        })
        mock_history.index = pd.date_range("2021-01-01", periods=10)
        mock_history.index.name = "Date"

        mock_ticker.history.return_value = mock_history

        fetcher = YahooFetcher()
        df = fetcher.get_ohlcv(symbol="AAPL", limit=5)

        assert len(df) == 5


class TestYahooFetcherIntervalMapping:
    """Test interval normalization."""

    def test_normalize_interval_1d(self):
        """1d should map to 1d."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_interval("1d") == "1d"

    def test_normalize_interval_1h(self):
        """1h should map to 1h."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_interval("1h") == "1h"

    def test_normalize_interval_1w(self):
        """1w should map to 1wk."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_interval("1w") == "1wk"

    def test_normalize_interval_1mo(self):
        """1mo should map to 1mo."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_interval("1mo") == "1mo"

    def test_normalize_interval_case_insensitive(self):
        """Interval normalization should be case-insensitive."""
        fetcher = YahooFetcher()
        assert fetcher._normalize_interval("1D") == "1d"
        assert fetcher._normalize_interval("1H") == "1h"


class TestYahooFetcherErrors:
    """Test error handling."""

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_empty_symbol_raises(self, mock_yf):
        """Empty symbol should raise FetcherError."""
        fetcher = YahooFetcher()
        with pytest.raises(FetcherError):
            fetcher.get_ohlcv(symbol="")

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_no_data_raises(self, mock_yf):
        """No data found should raise FetcherError."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()  # Empty

        fetcher = YahooFetcher()
        with pytest.raises(FetcherError):
            fetcher.get_ohlcv(symbol="INVALID_SYMBOL")

    @patch("src.fetcher.yahoo_fetcher.YahooFetcher.yf")
    def test_missing_required_columns_raises(self, mock_yf):
        """Missing required columns should raise FetcherError."""
        mock_ticker = Mock()
        mock_yf.Ticker.return_value = mock_ticker

        # Missing 'Close' column
        mock_history = pd.DataFrame({
            "Open": [150.0],
            "High": [152.0],
            "Low": [149.0],
            "Volume": [1000000.0],
        })
        mock_history.index = pd.date_range("2021-01-01", periods=1)
        mock_history.index.name = "Date"

        mock_ticker.history.return_value = mock_history

        fetcher = YahooFetcher()
        with pytest.raises(FetcherError):
            fetcher.get_ohlcv(symbol="AAPL")


class TestYahooFetcherIntegration:
    """Integration tests."""

    def test_fetcher_has_correct_source_name(self):
        """Source name should be correct."""
        fetcher = YahooFetcher()
        assert fetcher.source_name == "YahooFetcher"

    def test_korean_stock_workflow(self):
        """Full workflow for Korean stock."""
        fetcher = YahooFetcher()

        # Test symbol normalization in workflow
        normalized = fetcher._normalize_korean_symbol("Samsung")
        assert normalized == "005930.KS"

        # Symbol should be uppercase in result
        # (This would require mocking to fully test)
