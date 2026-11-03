# -*- coding: utf-8 -*-
"""
Yahoo Finance fetcher for US stocks, Korean stocks, indices, and crypto.

Supported symbols:
  US stocks: AAPL, GOOGL, MSFT, TSLA
  US indices: ^GSPC, ^DJI, ^IXIC
  Korean stocks: 005930.KS (Samsung), 000660.KS (SK Hynix)
  Crypto: BTC-USD, ETH-USD, XRP-USD
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fetcher.base_fetcher import BaseFetcher, FetcherError

logger = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.WARNING)


class YahooFetcher(BaseFetcher):
    """
    Data fetcher using Yahoo Finance API.

    Supported markets:
    - US Stocks: AAPL, GOOGL, MSFT, TSLA
    - US Indices: ^GSPC, ^DJI, ^IXIC
    - Korean Stocks: 005930.KS (Samsung), 000660.KS (SK Hynix), etc.
    - Crypto: BTC-USD, ETH-USD, XRP-USD
    """

    INTERVAL_MAPPING = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "1d": "1d", "1w": "1wk", "1wk": "1wk",
        "1mo": "1mo", "1month": "1mo",
    }

    # Korean stock symbol mapping (name -> code)
    # 주의: 네이버(035420)와 카카오(035720)는 코드가 다르다.
    KOREAN_STOCKS = {
        "Samsung": "005930.KS",
        "SAMSUNG": "005930.KS",
        "SK": "000660.KS",
        "SK_HYNIX": "000660.KS",
        "LG": "066570.KS",
        "HYUNDAI": "005380.KS",
        "KB": "105560.KS",
        "NAVER": "035420.KS",
        "KAKAO": "035720.KS",
        "SAMSUNG_005930": "005930.KS",
    }

    #: yfinance 모듈 (지연 임포트). 클래스 속성으로 두어 테스트에서
    #: @patch("...YahooFetcher.yf")로 목킹할 수 있게 한다.
    yf = None

    def __init__(self) -> None:
        # 이미 로드됐거나 테스트에서 목이 주입된 경우 임포트를 건너뛴다.
        if type(self).yf is None:
            try:
                import yfinance

                type(self).yf = yfinance
            except ImportError as exc:
                raise FetcherError(
                    "yfinance package not installed. Run: pip install yfinance"
                ) from exc

    def _normalize_interval(self, interval: str) -> str:
        return self.INTERVAL_MAPPING.get(interval.lower(), "1d")

    def _normalize_korean_symbol(self, symbol: str) -> str:
        """
        Normalize Korean stock symbol.

        Parameters:
            symbol: Korean stock name or code.

        Returns:
            Yahoo Finance compatible symbol (e.g., "005930.KS").
        """
        symbol_upper = symbol.upper().strip()
        if symbol_upper in self.KOREAN_STOCKS:
            return self.KOREAN_STOCKS[symbol_upper]
        # Assume it's already a code like "005930.KS"
        return symbol

    def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 500,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data from Yahoo Finance.

        Parameters:
            symbol: Stock/crypto symbol (e.g., "AAPL", "005930.KS", "BTC-USD").
            interval: Candle interval ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mo").
            limit: Number of candles to fetch.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns [open_time, open, high, low, close, volume, symbol].

        Raises:
            FetcherError: If symbol is empty or no data found.
        """
        if not symbol:
            raise FetcherError("Symbol cannot be empty.")

        try:
            # Normalize Korean symbol if needed
            normalized_symbol = self._normalize_korean_symbol(symbol)
            normalized_interval = self._normalize_interval(interval)
            logger.info(
                f"Fetching {symbol} ({normalized_interval}) from Yahoo Finance..."
            )

            ticker = self.yf.Ticker(normalized_symbol)

            if start_date and end_date:
                df = ticker.history(start=start_date, end=end_date, interval=normalized_interval)
            else:
                if limit <= 30:
                    period = "1mo"
                elif limit <= 90:
                    period = "3mo"
                elif limit <= 180:
                    period = "6mo"
                else:
                    period = "1y"
                df = ticker.history(period=period, interval=normalized_interval)

            if df.empty:
                raise FetcherError(
                    f"No data found for {symbol} on Yahoo Finance. "
                    "Check the symbol (e.g. AAPL, ^GSPC, 005930.KS)."
                )

            # Reset index: converts DatetimeIndex to column
            df = df.reset_index()

            # Rename 'Date' to 'open_time' (case-sensitive)
            column_mapping = {}
            for col in df.columns:
                if col.lower() == 'date':
                    column_mapping[col] = 'open_time'
            df = df.rename(columns=column_mapping)

            # Convert all remaining column names to lowercase
            df.columns = df.columns.str.lower()

            # Verify required columns
            required_cols = {"open_time", "open", "high", "low", "close", "volume"}
            missing = required_cols - set(df.columns)
            if missing:
                logger.error(f"Available columns: {list(df.columns)}")
                raise FetcherError(f"Missing required columns: {missing}")

            # Convert data types
            numeric_cols = ["open", "high", "low", "close", "volume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Yahoo는 장중/휴장일에 마지막 봉의 종가를 NaN으로 주는 경우가 있다.
            # 종가가 없는 봉은 지표 계산과 체결가 모두를 오염시키므로 버린다.
            # (2026-09-04 SOFI가 NaN 가격으로 매도되어 현금이 유실된 버그의 원인)
            before = len(df)
            df = df.dropna(subset=["close"])
            if len(df) < before:
                logger.warning(f"{symbol}: dropped {before - len(df)} candle(s) with missing close")
            if df.empty:
                raise FetcherError(f"No valid close prices for {symbol} on Yahoo Finance.")

            df["open_time"] = pd.to_datetime(df["open_time"])
            df["symbol"] = symbol.upper()

            # Return only required columns in correct order
            result = df[["open_time", "open", "high", "low", "close", "volume", "symbol"]]
            result = result.tail(limit).reset_index(drop=True)

            logger.info(f"Fetched {len(result)} candles for {symbol} from Yahoo Finance")
            return result

        except FetcherError:
            raise
        except Exception as exc:
            logger.error(f"Yahoo Finance fetch error for {symbol}: {exc}")
            raise FetcherError(f"Failed to fetch {symbol} from Yahoo Finance: {exc}") from exc
