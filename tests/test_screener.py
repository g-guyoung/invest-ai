# -*- coding: utf-8 -*-
"""StockScreener 테스트 (합성 일봉 — 네트워크 없음)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.execution.market_hours import KR_CATEGORY
from src.fetcher.kis_master import UniverseItem
from src.strategy.rule_strategies import DonchianBreakout
from src.strategy.screener import ScreenerConfig, StockScreener

AFTER_CLOSE = datetime(2026, 11, 27, 7, 0, tzinfo=timezone.utc)  # KST 16:00 금


def bars(last_close: float, volume: float = 1_000_000, breakout: bool = True, n: int = 40) -> pd.DataFrame:
    closes = [100.0] * (n - 1) + [last_close if breakout else 100.0]
    return pd.DataFrame({
        "open_time": pd.date_range(end="2026-11-27", periods=n, freq="B"),
        "open": closes, "high": [101.0] * (n - 1) + [max(last_close, 101.0)],
        "low": [99.0] * n, "close": closes, "volume": [volume] * n,
    })


def item(sym: str) -> UniverseItem:
    return UniverseItem(KR_CATEGORY, sym, f"{sym}.KS", sym, "KOSPI")


CFG = ScreenerConfig(min_price=50, min_avg_traded_value=50_000_000, max_price=1_000, max_candidates=2)


def screener(data: dict, tmp_path: Path | None = None, cfg: ScreenerConfig = CFG) -> StockScreener:
    return StockScreener(KR_CATEGORY, DonchianBreakout(entry=20, exit=10), cfg,
                         download_fn=lambda syms: {s: data[s] for s in syms if s in data},
                         now_fn=lambda: AFTER_CLOSE, today_fn=lambda: date(2026, 11, 27), cache_dir=tmp_path)


def test_fresh_breakout_passes() -> None:
    assert screener({}).evaluate(item("000001"), bars(110)) is not None


def test_no_breakout_rejected() -> None:
    assert screener({}).evaluate(item("000001"), bars(110, breakout=False)) is None


def test_illiquid_rejected() -> None:
    assert screener({}).evaluate(item("000001"), bars(110, volume=10)) is None


def test_price_filters() -> None:
    cheap = ScreenerConfig(min_price=500, min_avg_traded_value=0, max_price=10_000)
    assert screener({}, cfg=cheap).evaluate(item("1"), bars(110)) is None  # 최소 주가 미달
    tight = ScreenerConfig(min_price=0, min_avg_traded_value=0, max_price=105)
    assert screener({}, cfg=tight).evaluate(item("1"), bars(110)) is None  # 1주 예산 초과


def test_too_short_history_rejected() -> None:
    assert screener({}).evaluate(item("1"), bars(110, n=10)) is None


def test_screen_ranks_by_traded_value_and_caps() -> None:
    data = {"A.KS": bars(110, 1_000_000), "B.KS": bars(110, 3_000_000), "C.KS": bars(110, 2_000_000),
            "D.KS": bars(110, breakout=False)}
    items = [UniverseItem(KR_CATEGORY, s, f"{s}.KS", s, "KOSPI") for s in "ABCD"]
    result = screener(data).screen(items)
    assert [c.symbol for c in result] == ["B", "C"]


def test_screen_cache_reused(tmp_path: Path) -> None:
    data = {"A.KS": bars(110)}
    items = [UniverseItem(KR_CATEGORY, "A", "A.KS", "A", "KOSPI")]
    assert [c.symbol for c in screener(data, tmp_path).screen(items, cache_key="kr")] == ["A"]
    # 데이터가 없어도 같은 날 캐시를 쓴다
    assert [c.symbol for c in screener({}, tmp_path).screen(items, cache_key="kr")] == ["A"]


def test_bad_data_does_not_break_screen() -> None:
    data = {"A.KS": pd.DataFrame({"x": [1]}), "B.KS": bars(110)}
    items = [UniverseItem(KR_CATEGORY, s, f"{s}.KS", s, "KOSPI") for s in "AB"]
    assert [c.symbol for c in screener(data).screen(items)] == ["B"]
