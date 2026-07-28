# -*- coding: utf-8 -*-
"""
Binance 공개 REST API를 이용한 OHLCV 데이터 수집기.

설계 노트
---------
- Binance klines(/api/v3/klines) 엔드포인트는 시세 조회에 API 키가
  필요 없으므로, 현재 단계(데이터 수집)에서는 인증 없이 동작한다.
  추후 계좌 조회/주문 등 인증이 필요한 엔드포인트를 추가할 때
  BINANCE_API_KEY / BINANCE_API_SECRET(.env)을 사용하도록 확장한다.
- 네트워크 요청은 일시적으로 실패할 수 있으므로 지수 백오프 기반
  재시도 로직을 공통으로 적용한다.
- 반환 타입은 프로젝트 전역 규칙에 따라 pandas DataFrame으로 통일한다.
"""

from __future__ import annotations

import sys
import time
import logging
from pathlib import Path
from typing import Optional

# 이 파일을 `python src/fetcher/binance_fetcher.py`처럼 직접 실행하면
# 파이썬이 프로젝트 루트를 sys.path에 넣어주지 않아 `config` 모듈을
# 찾지 못해 ModuleNotFoundError가 발생한다. 프로젝트 루트를 명시적으로
# 추가하여 직접 실행/모듈 임포트 양쪽 모두에서 동작하도록 한다.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import requests

from config.settings import (
    BINANCE_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BACKOFF_SECONDS,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

# Binance klines 응답 컬럼 정의 (공식 API 문서 기준 12개 필드)
_KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "num_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]

_NUMERIC_COLUMNS = [
    "open", "high", "low", "close", "volume",
    "quote_asset_volume", "taker_buy_base_volume", "taker_buy_quote_volume",
]


class BinanceFetcherError(Exception):
    """Binance 데이터 수집 과정에서 발생하는 모든 오류의 기반 클래스."""


class BinanceFetcher:
    """Binance 공개 API로부터 OHLCV(캔들) 데이터를 수집하는 클래스.

    Attributes:
        base_url: Binance REST API 기본 URL.
        max_retries: 요청 실패 시 최대 재시도 횟수.
        backoff_seconds: 재시도 간 대기 시간(초). 시도마다 2배씩 증가한다.
        session: 재사용할 requests.Session 인스턴스.
    """

    def __init__(
        self,
        base_url: str = BINANCE_BASE_URL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        session: Optional[requests.Session] = None,
    ) -> None:
        """BinanceFetcher를 초기화한다.

        Args:
            base_url: Binance REST API 기본 URL.
            max_retries: 요청 실패 시 최대 재시도 횟수.
            backoff_seconds: 재시도 간 초기 대기 시간(초).
            session: 외부에서 주입할 requests.Session (테스트 시 mock 주입용).
        """
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.session = session or requests.Session()

    def _request_with_retry(self, endpoint: str, params: dict) -> list:
        """재시도 로직이 적용된 GET 요청.

        Args:
            endpoint: base_url 뒤에 붙는 API 경로 (예: "/api/v3/klines").
            params: 쿼리 파라미터.

        Returns:
            API 응답 JSON을 파싱한 리스트.

        Raises:
            BinanceFetcherError: max_retries 회 모두 실패했을 때.
        """
        url = f"{self.base_url}{endpoint}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Binance 요청 실패 (시도 %d/%d): %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        raise BinanceFetcherError(
            f"Binance API 요청이 {self.max_retries}회 모두 실패했습니다: {last_error}"
        ) from last_error

    def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> pd.DataFrame:
        """Binance klines(OHLCV) 데이터를 수집하여 DataFrame으로 반환한다.

        Args:
            symbol: 거래 심볼 (예: "BTCUSDT").
            interval: 캔들 간격 (예: "1m", "1h", "1d").
            limit: 최대 수집 캔들 개수 (1~1000, Binance 제한).
            start_time: 조회 시작 시각(ms epoch). 생략 가능.
            end_time: 조회 종료 시각(ms epoch). 생략 가능.

        Returns:
            columns=[open_time, open, high, low, close, volume, close_time, ...]
            를 가진 pandas DataFrame. open_time/close_time은 datetime으로 변환된다.

        Raises:
            BinanceFetcherError: symbol이 비어있거나 API 요청이 모두 실패한 경우.
        """
        if not symbol:
            raise BinanceFetcherError("symbol은 비어 있을 수 없습니다.")

        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        raw = self._request_with_retry("/api/v3/klines", params)

        if not raw:
            logger.info("Binance에서 %s(%s) 데이터가 반환되지 않았습니다.", symbol, interval)
            return pd.DataFrame(columns=_KLINE_COLUMNS)

        df = pd.DataFrame(raw, columns=_KLINE_COLUMNS)
        df[_NUMERIC_COLUMNS] = df[_NUMERIC_COLUMNS].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        df["num_trades"] = df["num_trades"].astype(int)
        df["symbol"] = symbol.upper()

        return df.drop(columns=["ignore"])

    @staticmethod
    def save_to_csv(df: pd.DataFrame, filename: str) -> str:
        """DataFrame을 data/ 디렉토리에 CSV로 저장한다.

        Args:
            df: 저장할 DataFrame.
            filename: 저장할 파일명 (예: "BTCUSDT_1d.csv").

        Returns:
            저장된 파일의 전체 경로(str).

        Raises:
            BinanceFetcherError: df가 비어 있는 경우.
        """
        if df.empty:
            raise BinanceFetcherError("빈 DataFrame은 저장할 수 없습니다.")

        filepath = DATA_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info("CSV 저장 완료: %s", filepath)
        return str(filepath)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetcher = BinanceFetcher()
    ohlcv = fetcher.get_klines(symbol="BTCUSDT", interval="1d", limit=30)
    print(ohlcv.tail())
    fetcher.save_to_csv(ohlcv, "BTCUSDT_1d.csv")
