# -*- coding: utf-8 -*-
"""
주식 시장 운영 시간 (한국 KRX / 미국 NYSE·NASDAQ 정규장).

목적: 장이 닫혀 있을 때 주문을 보내 거부/예약주문 사고가 나는 것을 막고,
    일봉 전략이 "아직 끝나지 않은 오늘 봉"을 쓰지 않도록(look-ahead 방지)
    마지막 완성 봉 날짜를 계산한다.

설계 메모
---------
- 시간대는 zoneinfo(IANA)로 처리한다 → 미국 서머타임(DST)이 자동 반영된다.
  Windows에는 IANA DB가 없으므로 requirements.txt의 `tzdata` 패키지가 필요하다.
- 공휴일은 내장하지 않는다(매년 바뀌고, 틀린 달력은 없는 것보다 위험).
  대신 `extra_holidays`로 주입할 수 있고, 공휴일에 주문이 나가도 브로커가 거부하므로
  돈이 걸리는 사고로 이어지지는 않는다.
- 순수 함수 — 현재 시각을 인자로 받으므로 테스트가 결정적이다.

입력: 카테고리(🇰🇷 한국 주식 / 🇺🇸 미국 주식), 현재 시각(tz-aware 권장, naive면 UTC로 간주)
출력: 장 운영 여부(bool), 마지막 완성 세션 날짜(date)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

KR_CATEGORY = "🇰🇷 한국 주식"
US_CATEGORY = "🇺🇸 미국 주식"

KST = ZoneInfo("Asia/Seoul")
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketSession:
    """한 시장의 정규장 정의.

    Attributes:
        tz: 시장 현지 시간대.
        open: 정규장 시작 시각 (현지).
        close: 정규장 종료 시각 (현지, 이 시각부터는 장 마감).
    """

    tz: ZoneInfo
    open: time
    close: time


SESSIONS: dict[str, MarketSession] = {
    KR_CATEGORY: MarketSession(KST, time(9, 0), time(15, 30)),
    US_CATEGORY: MarketSession(NEW_YORK, time(9, 30), time(16, 0)),
}


def get_session(category: str) -> MarketSession:
    """카테고리의 정규장 정의를 반환한다.

    Raises:
        ValueError: 주식 카테고리가 아닌 경우.
    """
    try:
        return SESSIONS[category]
    except KeyError as exc:
        raise ValueError(f"주식 시장 카테고리가 아닙니다: {category}") from exc


def _to_local(category: str, now: Optional[datetime]) -> datetime:
    session = get_session(category)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(session.tz)


def _is_trading_day(day: date, holidays: frozenset[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def is_market_open(
    category: str,
    now: Optional[datetime] = None,
    extra_holidays: Iterable[date] = (),
) -> bool:
    """지금이 정규장 시간인지 확인한다.

    Args:
        category: 시장 카테고리.
        now: 기준 시각 (생략 시 현재). naive datetime은 UTC로 간주한다.
        extra_holidays: 휴장일(현지 날짜) 목록.

    Returns:
        평일·비휴장일이고 open <= 현지시각 < close 이면 True.

    Examples:
        >>> from datetime import datetime, timezone
        >>> is_market_open(KR_CATEGORY, datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc))  # KST 10:00 금
        True
    """
    session = get_session(category)
    local = _to_local(category, now)
    if not _is_trading_day(local.date(), frozenset(extra_holidays)):
        return False
    return session.open <= local.time() < session.close


def last_completed_session_date(
    category: str,
    now: Optional[datetime] = None,
    extra_holidays: Iterable[date] = (),
) -> date:
    """종가가 확정된 가장 최근 거래일(현지 날짜)을 반환한다.

    오늘이 거래일이고 이미 장 마감 시각을 지났으면 오늘, 아니면 그 이전 거래일.

    Args:
        category: 시장 카테고리.
        now: 기준 시각.
        extra_holidays: 휴장일 목록.

    Returns:
        마지막 완성 세션의 현지 날짜.
    """
    session = get_session(category)
    holidays = frozenset(extra_holidays)
    local = _to_local(category, now)
    day = local.date()
    if _is_trading_day(day, holidays) and local.time() >= session.close:
        return day
    day -= timedelta(days=1)
    while not _is_trading_day(day, holidays):
        day -= timedelta(days=1)
    return day


def drop_incomplete_stock_candle(df, category: str, now: Optional[datetime] = None):
    """아직 종가가 확정되지 않은 일봉(오늘 진행 중인 봉)을 제거한다.

    Yahoo 일봉의 open_time은 현지 거래일 자정(tz-naive)이다.

    Args:
        df: open_time 컬럼이 있는 OHLCV DataFrame.
        category: 시장 카테고리.
        now: 기준 시각 (테스트 주입용).

    Returns:
        마지막 완성 세션 날짜 이하의 봉만 남긴 DataFrame (인덱스 재설정).
    """
    import pandas as pd

    cutoff = pd.Timestamp(last_completed_session_date(category, now))
    times = pd.to_datetime(df["open_time"])
    if getattr(times.dt, "tz", None) is not None:
        times = times.dt.tz_localize(None)
    return df[times.dt.normalize() <= cutoff].reset_index(drop=True)
