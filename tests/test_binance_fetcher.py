# -*- coding: utf-8 -*-
"""
src/fetcher/binance_fetcher.py 에 대한 pytest 테스트.

정상 케이스와 실패 케이스(네트워크 오류로 인한 재시도 소진, 잘못된 입력,
빈 DataFrame 저장 시도)를 모두 검증한다. 실제 네트워크 호출은 하지 않고
requests.Session을 mock으로 대체한다.
"""

import pandas as pd
import pytest
import requests

from src.fetcher.binance_fetcher import BinanceFetcher, BinanceFetcherError


# 실제 Binance klines 응답 형식을 그대로 흉내낸 샘플 (2개 캔들)
SAMPLE_KLINES = [
    [
        1700000000000, "36000.0", "36500.0", "35800.0", "36200.0", "123.45",
        1700003599999, "4459050.0", 1000, "60.0", "2172000.0", "0",
    ],
    [
        1700003600000, "36200.0", "36800.0", "36100.0", "36700.0", "150.10",
        1700007199999, "5488660.0", 1100, "70.0", "2569700.0", "0",
    ],
]


class _FakeResponse:
    """requests.Response 를 흉내내는 최소 스텁."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class _FakeSession:
    """호출 시나리오를 스크립트로 지정할 수 있는 가짜 세션."""

    def __init__(self, side_effects):
        # side_effects: 각 호출마다 반환할 값 또는 raise할 예외의 리스트
        self._side_effects = list(side_effects)
        self.call_count = 0

    def get(self, url, params=None, timeout=None):
        self.call_count += 1
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """재시도 테스트가 실제로 대기하지 않도록 time.sleep을 무력화한다."""
    monkeypatch.setattr("src.fetcher.binance_fetcher.time.sleep", lambda _: None)


# ── 정상 케이스 ──────────────────────────────────────────────
def test_get_klines_success_returns_dataframe():
    session = _FakeSession([_FakeResponse(SAMPLE_KLINES)])
    fetcher = BinanceFetcher(session=session, max_retries=3)

    df = fetcher.get_klines(symbol="btcusdt", interval="1h", limit=2)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df["symbol"].unique()) == ["BTCUSDT"]
    assert df["close"].iloc[-1] == 36700.0
    assert session.call_count == 1


def test_get_klines_retries_then_succeeds():
    # 첫 시도는 네트워크 오류, 두 번째 시도는 성공
    session = _FakeSession([
        requests.ConnectionError("일시적 네트워크 오류"),
        _FakeResponse(SAMPLE_KLINES),
    ])
    fetcher = BinanceFetcher(session=session, max_retries=3, backoff_seconds=0)

    df = fetcher.get_klines(symbol="BTCUSDT")

    assert len(df) == 2
    assert session.call_count == 2


def test_get_klines_empty_response_returns_empty_dataframe():
    session = _FakeSession([_FakeResponse([])])
    fetcher = BinanceFetcher(session=session)

    df = fetcher.get_klines(symbol="BTCUSDT")

    assert df.empty


def test_save_to_csv_writes_file(tmp_path, monkeypatch):
    import src.fetcher.binance_fetcher as module
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)

    df = pd.DataFrame({"close": [1.0, 2.0]})
    filepath = module.BinanceFetcher.save_to_csv(df, "test.csv")

    assert (tmp_path / "test.csv").exists()
    assert filepath == str(tmp_path / "test.csv")


# ── 실패 케이스 ──────────────────────────────────────────────
def test_get_klines_empty_symbol_raises_error():
    fetcher = BinanceFetcher(session=_FakeSession([]))

    with pytest.raises(BinanceFetcherError):
        fetcher.get_klines(symbol="")


def test_get_klines_exhausts_retries_raises_error():
    session = _FakeSession([
        requests.ConnectionError("오류1"),
        requests.ConnectionError("오류2"),
        requests.ConnectionError("오류3"),
    ])
    fetcher = BinanceFetcher(session=session, max_retries=3, backoff_seconds=0)

    with pytest.raises(BinanceFetcherError):
        fetcher.get_klines(symbol="BTCUSDT")

    assert session.call_count == 3


def test_get_klines_http_error_raises_after_retries():
    session = _FakeSession([_FakeResponse(None, status_code=500)] * 3)
    fetcher = BinanceFetcher(session=session, max_retries=3, backoff_seconds=0)

    with pytest.raises(BinanceFetcherError):
        fetcher.get_klines(symbol="BTCUSDT")


def test_save_to_csv_empty_dataframe_raises_error():
    with pytest.raises(BinanceFetcherError):
        BinanceFetcher.save_to_csv(pd.DataFrame(), "empty.csv")
