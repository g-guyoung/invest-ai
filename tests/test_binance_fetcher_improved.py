# -*- coding: utf-8 -*-
"""
Tests for improved BinanceFetcher with BaseFetcher interface.
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from src.fetcher.binance_fetcher import BinanceFetcher, BinanceFetcherError
from src.fetcher.base_fetcher import FetcherError


class TestBinanceFetcherInterface:
    """Test BaseFetcher interface implementation."""

    def test_binance_fetcher_inherits_base_fetcher(self):
        """BinanceFetcher should inherit from BaseFetcher."""
        fetcher = BinanceFetcher()
        assert hasattr(fetcher, "get_ohlcv")
        assert hasattr(fetcher, "source_name")

    def test_source_name_property(self):
        """Should return correct source name."""
        fetcher = BinanceFetcher()
        assert fetcher.source_name == "BinanceFetcher"


class TestBinanceFetcherOHLCV:
    """Test get_ohlcv method (BaseFetcher interface)."""

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_ohlcv_with_date_range(self, mock_session):
        """Should fetch OHLCV data with date-based parameters."""
        # Mock response
        mock_data = [
            [1609459200000, "29000.00", "30000.00", "28000.00", "29500.00", "100.0",
             1609545599999, "2950000.00", 50, "50.0", "1475000.00", "0"],
        ]
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        fetcher = BinanceFetcher(session=mock_session_instance)
        df = fetcher.get_ohlcv(
            symbol="BTCUSDT",
            interval="1d",
            limit=100,
            start_date="2021-01-01",
            end_date="2021-01-31",
        )

        assert not df.empty
        assert "open_time" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns
        assert "symbol" in df.columns
        assert df["symbol"].iloc[0] == "BTCUSDT"

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_ohlcv_result_format(self, mock_session):
        """Result should have standard columns."""
        mock_data = [
            [1609459200000, "29000.00", "30000.00", "28000.00", "29500.00", "100.0",
             1609545599999, "2950000.00", 50, "50.0", "1475000.00", "0"],
        ]
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        fetcher = BinanceFetcher(session=mock_session_instance)
        df = fetcher.get_ohlcv(symbol="ETHUSDT")

        # Check standard format
        expected_cols = {"open_time", "open", "high", "low", "close", "volume", "symbol"}
        assert expected_cols.issubset(set(df.columns))


class TestBinanceFetcherKlines:
    """Test get_klines method (existing)."""

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_klines_basic(self, mock_session):
        """Should fetch klines data."""
        mock_data = [
            [1609459200000, "29000.00", "30000.00", "28000.00", "29500.00", "100.0",
             1609545599999, "2950000.00", 50, "50.0", "1475000.00", "0"],
        ]
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        fetcher = BinanceFetcher(session=mock_session_instance)
        df = fetcher.get_klines(symbol="BTCUSDT", interval="1d", limit=100)

        assert not df.empty
        assert len(df) == 1
        assert "open_time" in df.columns
        assert "close_time" in df.columns

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_klines_multiple_symbols(self, mock_session):
        """Should support multiple symbols sequentially."""
        mock_data = [
            [1609459200000, "29000.00", "30000.00", "28000.00", "29500.00", "100.0",
             1609545599999, "2950000.00", 50, "50.0", "1475000.00", "0"],
        ]
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response

        fetcher = BinanceFetcher(session=mock_session_instance)

        # Fetch multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
        results = {}

        for symbol in symbols:
            df = fetcher.get_klines(symbol=symbol, limit=100)
            results[symbol] = df
            assert not df.empty
            assert df["symbol"].iloc[0] == symbol

        assert len(results) == 3

    def test_get_klines_empty_symbol_raises(self):
        """Empty symbol should raise BinanceFetcherError."""
        fetcher = BinanceFetcher()
        with pytest.raises(BinanceFetcherError):
            fetcher.get_klines(symbol="", limit=100)

    def test_get_klines_invalid_limit_raises(self):
        """Invalid limit should raise BinanceFetcherError."""
        fetcher = BinanceFetcher()
        with pytest.raises(BinanceFetcherError):
            fetcher.get_klines(symbol="BTCUSDT", limit=2000)  # > 1000

        with pytest.raises(BinanceFetcherError):
            fetcher.get_klines(symbol="BTCUSDT", limit=0)  # < 1

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_klines_empty_response(self, mock_session):
        """Empty API response should return empty DataFrame."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response

        fetcher = BinanceFetcher(session=mock_session_instance)
        df = fetcher.get_klines(symbol="BTCUSDT", limit=100)

        assert df.empty

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_get_klines_numeric_conversion(self, mock_session):
        """Numeric columns should be converted to float."""
        mock_data = [
            [1609459200000, "29000.00", "30000.00", "28000.00", "29500.00", "100.5",
             1609545599999, "2950000.00", 50, "50.0", "1475000.00", "0"],
        ]
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response

        fetcher = BinanceFetcher(session=mock_session_instance)
        df = fetcher.get_klines(symbol="BTCUSDT")

        # numpy 스칼라(np.float64/np.int64)는 파이썬 int의 서브클래스가 아니므로
        # isinstance 대신 dtype으로 검사한다 (np.float64는 float 서브클래스라 통과했었음).
        import pandas.api.types as ptypes

        assert ptypes.is_float_dtype(df["close"])
        assert ptypes.is_float_dtype(df["volume"])
        assert ptypes.is_integer_dtype(df["num_trades"])


class TestBinanceFetcherErrors:
    """Test error handling."""

    @patch("src.fetcher.binance_fetcher.requests.Session")
    def test_request_failure_raises(self, mock_session):
        """Request failure should raise BinanceFetcherError."""
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = Exception("Network error")

        fetcher = BinanceFetcher(session=mock_session_instance, max_retries=1)

        with pytest.raises(BinanceFetcherError):
            fetcher.get_klines(symbol="BTCUSDT", limit=100)

    def test_fetcher_error_inheritance(self):
        """BinanceFetcherError should inherit from FetcherError."""
        assert issubclass(BinanceFetcherError, FetcherError)
