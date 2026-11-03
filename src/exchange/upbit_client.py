# -*- coding: utf-8 -*-
"""
업비트 시세(Quotation) 클라이언트 — 공개 API, 인증 불필요.

목적:
    비트코인 실전 봇(5만원)과 백테스트가 **실제로 체결될 거래소의 원화(KRW) 시세**를
    그대로 쓰도록 한다. 기존 Yahoo(BTC-USD)는 달러 시세이고, 2026-09-04 SOFI 사고처럼
    마지막 봉 종가가 NaN으로 오는 경우가 있어 실전 데이터원으로 부적합하다.

설계:
    - requests.Session 주입(DI) → 테스트에서 네트워크 없이 mock 가능
    - 업비트 캔들 API는 1회 최대 200개 → `to` 파라미터로 과거 방향 페이지네이션
    - 모든 호출은 common.retry의 지수 백오프 재시도 사용 (DRY)
    - 반환 DataFrame 스키마는 기존 fetcher와 동일: open_time(UTC), open, high, low, close, volume

주문(인증) API는 Part 2(실전 봇)에서 별도 클래스로 추가한다 — 시세와 주문의 책임 분리(SRP).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd
import requests

from src.common.retry import retry_with_backoff
from src.fetcher.base_fetcher import FetcherError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upbit.com/v1"
MAX_PER_REQUEST = 200

#: 지원 인터벌 → 업비트 엔드포인트 경로
INTERVAL_PATHS: dict[str, str] = {
    "1d": "candles/days",
    "4h": "candles/minutes/240",
    "1h": "candles/minutes/60",
    "15m": "candles/minutes/15",
}


class UpbitQuotationClient:
    """업비트 원화마켓 OHLCV 수집기.

    Examples:
        >>> client = UpbitQuotationClient()                      # doctest: +SKIP
        >>> df = client.get_ohlcv("KRW-BTC", "1d", count=1000)   # doctest: +SKIP
        >>> df.columns.tolist()                                    # doctest: +SKIP
        ['open_time', 'open', 'high', 'low', 'close', 'volume']
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        request_interval: float = 0.15,
    ) -> None:
        """
        Args:
            session: HTTP 세션 (테스트 시 mock 주입). None이면 새로 생성.
            timeout: 요청 타임아웃(초).
            max_retries: 요청당 최대 재시도 횟수.
            backoff_seconds: 재시도 초기 대기(초).
            request_interval: 페이지 요청 사이 대기(초) — 업비트 요청 제한 준수용.
        """
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.request_interval = request_interval

    def get_ohlcv(self, market: str = "KRW-BTC", interval: str = "1d", count: int = 200) -> pd.DataFrame:
        """최근 `count`개의 캔들을 과거→현재 순으로 반환한다.

        Args:
            market: 업비트 마켓 코드 (예: "KRW-BTC").
            interval: "1d" | "4h" | "1h" | "15m".
            count: 가져올 캔들 수 (200 초과 시 자동 페이지네이션).

        Returns:
            open_time(UTC, tz-naive) 오름차순 DataFrame. 종가가 비정상인 봉은 제거된다.

        Raises:
            ValueError: 지원하지 않는 interval 또는 count <= 0.
            FetcherError: 네트워크/응답 오류가 재시도 후에도 지속될 때.
        """
        if interval not in INTERVAL_PATHS:
            raise ValueError(f"지원하지 않는 interval: {interval} (지원: {list(INTERVAL_PATHS)})")
        if count <= 0:
            raise ValueError("count는 1 이상이어야 합니다.")

        rows: list[dict] = []
        to: Optional[str] = None
        while len(rows) < count:
            batch = self._fetch_page(market, interval, min(MAX_PER_REQUEST, count - len(rows)), to)
            if not batch:
                break  # 상장 이전까지 도달
            rows.extend(batch)
            # 업비트는 최신→과거 순으로 준다. 가장 오래된 봉 시각을 다음 페이지의 `to`로 사용(배타적).
            to = batch[-1]["candle_date_time_utc"]
            if len(batch) < MAX_PER_REQUEST and len(rows) < count:
                break
            if len(rows) < count:
                time.sleep(self.request_interval)

        if not rows:
            raise FetcherError(f"{market} {interval} 캔들을 받지 못했습니다.")
        return self._to_frame(rows)

    # ── 내부 구현 ────────────────────────────────────────────
    def _fetch_page(self, market: str, interval: str, count: int, to: Optional[str]) -> list[dict]:
        """캔들 1페이지(최대 200개)를 받아온다."""
        params: dict[str, str | int] = {"market": market, "count": count}
        if to:
            params["to"] = to

        def _call() -> list[dict]:
            resp = self.session.get(f"{BASE_URL}/{INTERVAL_PATHS[interval]}", params=params, timeout=self.timeout)
            if resp.status_code == 429:
                raise ConnectionError("업비트 요청 제한(429)")
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError(f"예상하지 못한 응답 형식: {str(data)[:200]}")
            return data

        try:
            return retry_with_backoff(
                _call,
                max_retries=self.max_retries,
                backoff_seconds=self.backoff_seconds,
                retry_exceptions=(requests.RequestException, ConnectionError, ValueError),
                logger=logger,
                action_name=f"업비트 {market} {interval} 캔들 조회",
            )
        except Exception as exc:  # 도메인 예외로 감싸서 상위에 전달
            raise FetcherError(f"업비트 캔들 조회 실패: {exc}") from exc

    @staticmethod
    def _to_frame(rows: list[dict]) -> pd.DataFrame:
        """업비트 응답을 표준 OHLCV 스키마로 변환하고 검증한다."""
        df = pd.DataFrame(rows)
        out = pd.DataFrame(
            {
                "open_time": pd.to_datetime(df["candle_date_time_utc"]),
                "open": pd.to_numeric(df["opening_price"], errors="coerce"),
                "high": pd.to_numeric(df["high_price"], errors="coerce"),
                "low": pd.to_numeric(df["low_price"], errors="coerce"),
                "close": pd.to_numeric(df["trade_price"], errors="coerce"),
                "volume": pd.to_numeric(df["candle_acc_trade_volume"], errors="coerce"),
            }
        )
        # Validation: 중복 제거 → 시간 오름차순 → 비정상 종가 제거 (NaN 체결 사고 재발 방지)
        out = out.drop_duplicates("open_time").sort_values("open_time")
        out = out[out["close"].notna() & (out["close"] > 0)]
        return out.reset_index(drop=True)
