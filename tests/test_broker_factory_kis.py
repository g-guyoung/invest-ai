# -*- coding: utf-8 -*-
"""get_kis_broker 잠금 규칙 테스트 (모의투자 기본 / 실전은 이중 잠금)."""

from __future__ import annotations

import pytest

from src.execution.base_broker import BrokerError
from src.execution.broker_factory import _parse_us_exchanges, get_broker, get_kis_broker
from src.execution.kis_broker import KisBroker, KisEnv
from src.execution.paper_broker import PaperBroker

KEYS = {"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s", "KIS_ACCOUNT_NO": "12345678-01"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["KIS_ENV", "LIVE_TRADING", "LIVE_TRADING_CONFIRM", "KIS_MAX_ORDER_KRW",
                 "KIS_MAX_ORDER_USD", "KIS_US_EXCHANGES", "KIS_US_SLIPPAGE_PCT", *KEYS]:
        monkeypatch.delenv(name, raising=False)


def set_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in KEYS.items():
        monkeypatch.setenv(k, v)


def test_default_is_paper_and_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    broker = get_kis_broker()
    assert isinstance(broker, KisBroker)
    assert broker.env == KisEnv.PAPER and broker.dry_run and not broker.IS_LIVE


def test_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(BrokerError, match="KIS_APP_KEY"):
        get_kis_broker()


def test_prod_without_live_lock_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    monkeypatch.setenv("KIS_ENV", "prod")
    monkeypatch.setenv("LIVE_TRADING", "true")  # 확인 문구 없음
    with pytest.raises(BrokerError, match="실전 잠금"):
        get_kis_broker(dry_run=False)


def test_prod_with_live_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    monkeypatch.setenv("KIS_ENV", "prod")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRM", "I_UNDERSTAND_THE_RISKS")
    broker = get_kis_broker(dry_run=False)
    assert broker.env == KisEnv.REAL and broker.IS_LIVE and not broker.dry_run


def test_invalid_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    monkeypatch.setenv("KIS_ENV", "real")
    with pytest.raises(BrokerError, match="KIS_ENV"):
        get_kis_broker()


def test_caps_and_exchanges_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    monkeypatch.setenv("KIS_MAX_ORDER_KRW", "200,000")
    monkeypatch.setenv("KIS_US_EXCHANGES", "KO:NYSE")
    broker = get_kis_broker()
    assert broker.max_order_krw == 200_000
    assert broker.resolve_us_exchange("KO") == "NYSE"


def test_bad_number_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    set_keys(monkeypatch)
    monkeypatch.setenv("KIS_MAX_ORDER_USD", "lots")
    with pytest.raises(BrokerError, match="KIS_MAX_ORDER_USD"):
        get_kis_broker()


def test_parse_us_exchanges() -> None:
    assert _parse_us_exchanges("aapl:nasd, bad ,KO:NYSE,:X") == {"AAPL": "NASD", "KO": "NYSE"}


def test_crypto_factory_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(get_broker({}), PaperBroker)
