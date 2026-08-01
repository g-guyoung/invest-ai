# -*- coding: utf-8 -*-
"""
Base fetcher interface for all data sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class FetcherError(Exception):
    """Base exception for all data fetching errors."""


class BaseFetcher(ABC):
    """Common interface all data fetchers must implement."""

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 500,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data and return as DataFrame.

        Returns:
            DataFrame with columns=[open_time, open, high, low, close, volume, symbol]
        """
        raise NotImplementedError

    @property
    def source_name(self) -> str:
        return self.__class__.__name__