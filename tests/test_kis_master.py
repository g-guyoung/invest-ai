# -*- coding: utf-8 -*-
"""종목 마스터 파서/로더 테스트 (합성 파일 — 네트워크 없음)."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from src.execution.market_hours import KR_CATEGORY, US_CATEGORY
from src.fetcher.kis_master import (
    KisMasterError,
    KisMasterUniverse,
    items_from_symbols,
    parse_kr_master,
    parse_us_master,
)


def kr_line(code: str, name: str, group: str, tail_len: int = 227) -> str:
    tail = (group + "X" * tail_len)[:tail_len]
    return f"{code:<9}KR7{code}003{name}{tail}"


def us_line(symbol: str, sec_type: str, exch: str = "NAS") -> str:
    return "\t".join(["US", "512", exch, "나스닥", symbol, "D" + symbol, "한글명", f"{symbol} Inc", sec_type, "USD"])


class TestKrParser:
    def test_stock_only_by_default(self) -> None:
        text = "\n".join([kr_line("005930", "삼성전자", "ST"), kr_line("069500", "KODEX 200", "EF"),
                          kr_line("590001", "어떤ETN", "EN")])
        items = parse_kr_master(text, "KOSPI", 227)
        assert [(i.symbol, i.yahoo_symbol, i.name) for i in items] == [("005930", "005930.KS", "삼성전자")]

    def test_include_etf(self) -> None:
        text = "\n".join([kr_line("005930", "삼성전자", "ST"), kr_line("069500", "KODEX 200", "EF")])
        items = parse_kr_master(text, "KOSPI", 227, include_etf=True)
        assert [i.is_etf for i in items] == [False, True]

    def test_kosdaq_suffix_and_tail(self) -> None:
        items = parse_kr_master(kr_line("035720", "카카오", "ST", 221), "KOSDAQ", 221)
        assert items[0].yahoo_symbol == "035720.KQ"

    def test_garbage_lines_skipped(self) -> None:
        assert parse_kr_master("short\n\nQ50000ABC" + "X" * 300, "KOSPI", 227) == []


class TestUsParser:
    def test_stock_only_and_symbol_mapping(self) -> None:
        text = "\n".join([us_line("AAPL", "2"), us_line("QQQ", "3"), us_line("BRK/B", "2", "NYS"), us_line("SPX", "1")])
        items = parse_us_master(text, "NASD")
        assert [(i.symbol, i.yahoo_symbol) for i in items] == [("AAPL", "AAPL"), ("BRK/B", "BRK-B")]

    def test_include_etf(self) -> None:
        assert len(parse_us_master(us_line("QQQ", "3"), "NASD", include_etf=True)) == 1


def make_zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.mst", text.encode("cp949"))
    return buf.getvalue()


class TestUniverseLoader:
    def test_loads_and_caches(self, tmp_path: Path) -> None:
        calls: list[str] = []
        kospi = "\n".join(kr_line(f"{i:06d}", f"종목{i}", "ST") for i in range(60))
        kosdaq = "\n".join(kr_line(f"{900000 + i:06d}", f"코닥{i}", "ST", 221) for i in range(10))

        def fetch(name: str) -> bytes:
            calls.append(name)
            return make_zip(kospi if "kospi" in name else kosdaq)

        uni = KisMasterUniverse(cache_dir=tmp_path, fetch=fetch, today_fn=lambda: date(2026, 11, 27))
        assert len(uni.load(KR_CATEGORY)) == 70
        uni.load(KR_CATEGORY)
        assert calls == ["kospi_code.mst", "kosdaq_code.mst"]  # 두 번째는 캐시

    def test_too_few_items_raises(self, tmp_path: Path) -> None:
        uni = KisMasterUniverse(cache_dir=tmp_path, fetch=lambda n: make_zip(us_line("AAPL", "2")))
        with pytest.raises(KisMasterError, match="형식"):
            uni.load(US_CATEGORY)

    def test_bad_zip_raises(self, tmp_path: Path) -> None:
        uni = KisMasterUniverse(cache_dir=tmp_path, fetch=lambda n: b"not a zip")
        with pytest.raises(KisMasterError, match="압축"):
            uni.load(US_CATEGORY)

    def test_non_stock_category(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            KisMasterUniverse(cache_dir=tmp_path, fetch=lambda n: b"").load("₿ 암호화폐")


def test_items_from_symbols() -> None:
    assert items_from_symbols(KR_CATEGORY, ["005930"])[0].yahoo_symbol == "005930.KS"
    assert items_from_symbols(US_CATEGORY, ["brk.b"])[0].yahoo_symbol == "BRK-B"
