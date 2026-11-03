# -*- coding: utf-8 -*-
"""UpbitBroker 단위 테스트 (가짜 HTTP 세션 — 네트워크/실돈 없음)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import pytest

from src.execution.base_broker import BrokerError, OrderRequest, OrderSide
from src.execution.upbit_broker import (
    CRYPTO_CATEGORY,
    UpbitBroker,
    _format_krw,
    _format_volume,
    build_jwt,
)


class FakeResp:
    def __init__(self, body: Any, status: int = 200) -> None:
        self._body, self.status_code = body, status

    def json(self) -> Any:
        return self._body


class Seq:
    """호출마다 순서대로 소비되는 응답 시퀀스 (마지막 값은 반복)."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)


class FakeSession:
    """경로별 응답을 돌려주고 호출 기록을 남긴다."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes, self.calls = routes, []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResp:
        path = url.replace("https://api.upbit.com", "")
        self.calls.append((method, path, kwargs))
        resp = self.routes[(method, path)]
        if isinstance(resp, Seq):
            resp = resp.items.pop(0) if len(resp.items) > 1 else resp.items[0]
        return resp if isinstance(resp, FakeResp) else FakeResp(resp)

    def posts(self) -> list:
        return [c for c in self.calls if c[0] == "POST"]


ACCOUNTS = [
    {"currency": "KRW", "balance": "50000", "avg_buy_price": "0"},
    {"currency": "BTC", "balance": "0.00010000", "avg_buy_price": "100000000"},
]


def make(routes: dict, **kw: Any) -> tuple[UpbitBroker, FakeSession]:
    routes.setdefault(("GET", "/v1/accounts"), ACCOUNTS)
    s = FakeSession(routes)
    return UpbitBroker("AK", "SK", session=s, sleep=lambda _: None, **kw), s


def buy(amount: float, symbol: str = "BTC", category: str = CRYPTO_CATEGORY) -> OrderRequest:
    return OrderRequest(category, symbol, "x", OrderSide.BUY, price=100_000_000, amount=amount)


def sell(amount: float = 0.0, price: float = 100_000_000) -> OrderRequest:
    return OrderRequest(CRYPTO_CATEGORY, "BTC", "x", OrderSide.SELL, price=price, amount=amount)


# ---------- JWT ----------

def test_jwt_signature_and_query_hash():
    token = build_jwt("AK", "SK", "market=KRW-BTC&side=bid")
    h, p, sig = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    payload = json.loads(base64.urlsafe_b64decode(pad(p)))
    assert payload["access_key"] == "AK"
    assert payload["query_hash"] == hashlib.sha512(b"market=KRW-BTC&side=bid").hexdigest()
    assert payload["query_hash_alg"] == "SHA512"
    expected = hmac.new(b"SK", f"{h}.{p}".encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(pad(sig)) == expected


def test_jwt_matches_pyjwt_if_available():
    jwt = pytest.importorskip("jwt")
    token = build_jwt("AK", "SK")
    decoded = jwt.decode(token, "SK", algorithms=["HS256"])
    assert decoded["access_key"] == "AK" and "query_hash" not in decoded


def test_empty_keys_rejected():
    with pytest.raises(BrokerError):
        UpbitBroker("", "")


# ---------- 포맷 ----------

def test_format_helpers_round_down():
    assert _format_volume(0.123456789) == "0.12345678"
    assert _format_krw(12345.99) == "12345"


# ---------- 조회 ----------

def test_balances_and_position():
    b, _ = make({})
    assert b.get_cash(CRYPTO_CATEGORY) == 50000
    assert b.get_holding_qty(CRYPTO_CATEGORY, "btc") == pytest.approx(0.0001)
    assert b.get_position("BTC") == (pytest.approx(0.0001), 100_000_000)
    assert b.get_position("ETH") == (0.0, 0.0)


def test_get_price_is_public_no_auth_header():
    b, s = make({("GET", "/v1/ticker"): [{"trade_price": 123456789.0}]})
    assert b.get_price("KRW-BTC") == 123456789.0
    assert "Authorization" not in s.calls[-1][2]["headers"]


def test_http_error_becomes_broker_error_without_secrets():
    err = FakeResp({"error": {"name": "invalid_access_key", "message": "bad"}}, 401)
    b, _ = make({("GET", "/v1/accounts"): err})
    with pytest.raises(BrokerError) as ei:
        b.get_cash(CRYPTO_CATEGORY)
    assert "401" in str(ei.value) and "SK" not in str(ei.value) and "AK" not in str(ei.value)


# ---------- 매수 ----------

def test_market_buy_body_and_fill():
    routes = {
        ("POST", "/v1/orders"): {"uuid": "u1"},
        ("GET", "/v1/order"): Seq({"state": "wait"}, {"state": "cancel", "executed_volume": "0.0000999", "paid_fee": "2.5"}),
    }
    b, s = make(routes)
    r = b.place_order(buy(20000))
    assert r.success and r.is_live
    body = s.posts()[0][2]["json"]
    assert body == {"market": "KRW-BTC", "side": "bid", "ord_type": "price", "price": "20000"}
    assert "volume" not in body


def test_buy_below_minimum_rejected_no_post():
    b, s = make({})
    r = b.place_order(buy(4999))
    assert not r.success and "최소" in r.message and not s.posts()


def test_buy_over_cash_rejected():
    b, s = make({})
    r = b.place_order(buy(60000))
    assert not r.success and "부족" in r.message and not s.posts()


def test_disallowed_market_and_category_rejected():
    b, s = make({})
    assert not b.place_order(buy(10000, symbol="DOGE")).success
    assert not b.place_order(buy(10000, category="🇰🇷 한국 주식")).success
    assert not s.posts()


def test_unfilled_order_reports_failure():
    routes = {("POST", "/v1/orders"): {"uuid": "u1"}, ("GET", "/v1/order"): {"state": "wait", "executed_volume": "0"}}
    b, _ = make(routes, fill_poll_attempts=2)
    r = b.place_order(buy(10000))
    assert not r.success and "u1" in r.message


def test_post_failure_is_not_retried():
    b, s = make({("POST", "/v1/orders"): FakeResp({"error": {"name": "x", "message": "y"}}, 500)})
    with pytest.raises(BrokerError):
        b.place_order(buy(10000))
    assert len(s.posts()) == 1  # 중복 주문 방지


# ---------- 매도 ----------

def test_market_sell_all_body():
    routes = {("POST", "/v1/orders"): {"uuid": "u2"}, ("GET", "/v1/order"): {"state": "done", "executed_volume": "0.0001", "paid_fee": "5"}}
    b, s = make(routes)
    r = b.place_order(sell())
    assert r.success
    assert s.posts()[0][2]["json"] == {"market": "KRW-BTC", "side": "ask", "ord_type": "market", "volume": "0.00010000"}


def test_sell_without_holding_rejected():
    b, s = make({("GET", "/v1/accounts"): [{"currency": "KRW", "balance": "1000"}]})
    r = b.place_order(sell())
    assert not r.success and not s.posts()


def test_sell_dust_below_minimum_rejected():
    b, s = make({}, )
    r = b.place_order(sell(price=1_000_000))  # 0.0001 BTC * 100만 = 100원
    assert not r.success and "최소" in r.message and not s.posts()


# ---------- dry-run ----------

def test_dry_run_never_posts():
    b, s = make({}, dry_run=True)
    r = b.place_order(buy(20000))
    assert r.success and not r.is_live and "DRY-RUN" in r.message
    assert not s.posts()
