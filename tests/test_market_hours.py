# -*- coding: utf-8 -*-
"""market_hours 단위 테스트 (KST/뉴욕 시간대, 서머타임, 주말, 미완성 봉 제거)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.execution.market_hours import (
    KR_CATEGORY,
    US_CATEGORY,
    drop_incomplete_stock_candle,
    is_market_open,
    last_completed_session_date,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestIsMarketOpen:
    def test_kr_open_during_session(self) -> None:
        assert is_market_open(KR_CATEGORY, utc(2026, 11, 27, 1, 0))  # 금 KST 10:00

    def test_kr_closed_at_1530(self) -> None:
        assert not is_market_open(KR_CATEGORY, utc(2026, 11, 27, 6, 30))  # KST 15:30

    def test_kr_closed_before_open(self) -> None:
        assert not is_market_open(KR_CATEGORY, utc(2026, 11, 26, 23, 59))  # KST 08:59

    def test_weekend_closed(self) -> None:
        assert not is_market_open(KR_CATEGORY, utc(2026, 11, 28, 1, 0))  # 토

    def test_holiday_closed(self) -> None:
        assert not is_market_open(KR_CATEGORY, utc(2026, 11, 27, 1, 0), extra_holidays=[date(2026, 11, 27)])

    def test_us_winter_time(self) -> None:
        # 11/27(EST, UTC-5): 09:30 ET = 14:30 UTC
        assert not is_market_open(US_CATEGORY, utc(2026, 11, 27, 14, 29))
        assert is_market_open(US_CATEGORY, utc(2026, 11, 27, 14, 30))

    def test_us_summer_time(self) -> None:
        # 7/1(EDT, UTC-4): 09:30 ET = 13:30 UTC
        assert is_market_open(US_CATEGORY, utc(2026, 7, 1, 13, 30))
        assert not is_market_open(US_CATEGORY, utc(2026, 7, 1, 20, 0))  # 16:00 ET

    def test_naive_datetime_treated_as_utc(self) -> None:
        assert is_market_open(KR_CATEGORY, datetime(2026, 11, 27, 1, 0))

    def test_crypto_category_rejected(self) -> None:
        with pytest.raises(ValueError):
            is_market_open("₿ 암호화폐", utc(2026, 11, 27, 1, 0))


class TestLastCompletedSession:
    def test_during_session_returns_previous_day(self) -> None:
        assert last_completed_session_date(KR_CATEGORY, utc(2026, 11, 27, 1, 0)) == date(2026, 11, 26)

    def test_after_close_returns_today(self) -> None:
        assert last_completed_session_date(KR_CATEGORY, utc(2026, 11, 27, 7, 0)) == date(2026, 11, 27)

    def test_monday_morning_returns_friday(self) -> None:
        assert last_completed_session_date(KR_CATEGORY, utc(2026, 11, 30, 0, 30)) == date(2026, 11, 27)

    def test_us_uses_new_york_date(self) -> None:
        # KST 11/27 23:40 = ET 11/27 09:40 → 완성 봉은 11/26
        assert last_completed_session_date(US_CATEGORY, utc(2026, 11, 27, 14, 40)) == date(2026, 11, 26)


def test_drop_incomplete_candle_removes_today_during_session() -> None:
    df = pd.DataFrame({
        "open_time": pd.to_datetime(["2026-11-25", "2026-11-26", "2026-11-27"]),
        "close": [1.0, 2.0, 3.0],
    })
    out = drop_incomplete_stock_candle(df, KR_CATEGORY, utc(2026, 11, 27, 1, 0))
    assert list(out["close"]) == [1.0, 2.0]
    after_close = drop_incomplete_stock_candle(df, KR_CATEGORY, utc(2026, 11, 27, 7, 0))
    assert len(after_close) == 3
