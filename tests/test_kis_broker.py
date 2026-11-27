# -*- coding: utf-8 -*-
"""KisBroker 단위 테스트 (가짜 HTTP 세션 — 네트워크/실돈 없음)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.execution.base_broker import BrokerError, OrderRequest, OrderSide
from src.execution.kis_broker import (
    KisBroker,
    KisCredentials,
    KisEnv,
    normalize_stock_symbol,
    us_limit_price,
)
from src.execution.market_hours import KR_CATEGORY, US_CATEGORY

KR_OPEN = datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc)  # 금 KST 10:00
US_OPEN = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)  # 금 ET 10:00
CLOSED = datetime(2026, 11, 28, 1, 0, tzinfo=timezone.utc)  # 토

TOKEN = {"access_token": "tok-123", "expires_in": 86400}
KR_BALANCE = {
    "rt_cd": "0",
    "output1": [{"pdno": "005930", "hldg_qty": "3", "ord_psbl_qty": "3", "pchs_avg_pric": "70000"}],
    "output2": [{"dnca_tot_amt": "500000", "prvs_rcdl_excc_amt": "450000"}],
}
KR_PRICE = {"rt_cd": "0", "output": {"stck_prpr": "71000"}}
ORDER_OK = {"rt_cd": "0", "msg1": "주문 전송 완료", "output": {"ODNO": "0000123456"}}
KR_CCLD = {"rt_cd": "0", "output1": [{"odno": "0000123456", "tot_ccld_qty": "2", "avg_prvs": "71000"}]}


class FakeResp:
    def __init__(self, body: Any, status: int = 200) -> None:
        self._body, self.status_code = body, status

    def json(self) -> Any:
        return self._body


class FakeSession:
    """(method, path) → 응답 (리스트면 순서대로 소비, 마지막 값 반복). 호출 기록 저장."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes, self.calls = routes, []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResp:
        path = url.split(":29443")[-1].split(":9443")[-1]
        self.calls.append((method, path, kwargs))
        if (method, path) not in self.routes:
            raise AssertionError(f"예상치 못한 호출: {method} {path}")
        resp = self.routes[(method, path)]
        if isinstance(resp, list):
            resp = resp.pop(0) if len(resp) > 1 else resp[0]
        if isinstance(resp, Exception):
            raise resp
        return resp if isinstance(resp, FakeResp) else FakeResp(resp)

    def count(self, method: str, path_part: str) -> int:
        return sum(1 for m, p, _ in self.calls if m == method and path_part in p)


CREDS = KisCredentials.from_values("app-key-xyz", "app-secret-xyz", "12345678-01")


def make_broker(tmp_path: Path, routes: dict, now: datetime = KR_OPEN, **kw: Any) -> tuple[KisBroker, FakeSession]:
    routes = {("POST", "/oauth2/tokenP"): TOKEN, **routes}
    session = FakeSession(routes)
    broker = KisBroker(
        CREDS, session=session, sleep=lambda s: None, now_fn=lambda: now,
        token_cache_path=tmp_path / "token.json", retry_backoff=0.0, fill_poll_attempts=2, **kw,
    )
    return broker, session


def kr_req(side: OrderSide = OrderSide.BUY, amount: float = 150_000, price: float = 71_000, symbol: str = "005930") -> OrderRequest:
    return OrderRequest(category=KR_CATEGORY, symbol=symbol, name="삼성전자", side=side, price=price, amount=amount)


KR_ROUTES = {
    ("GET", "/uapi/domestic-stock/v1/trading/inquire-balance"): KR_BALANCE,
    ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): KR_PRICE,
    ("POST", "/uapi/domestic-stock/v1/trading/order-cash"): ORDER_OK,
    ("GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"): KR_CCLD,
}


# ----------------------------------------------------------------------
# 순수 헬퍼
# ----------------------------------------------------------------------


class TestHelpers:
    def test_normalize_kr(self) -> None:
        assert normalize_stock_symbol(KR_CATEGORY, "005930.KS") == "005930"
        assert normalize_stock_symbol(KR_CATEGORY, " 035720.kq ") == "035720"

    def test_normalize_kr_invalid(self) -> None:
        with pytest.raises(ValueError):
            normalize_stock_symbol(KR_CATEGORY, "삼성전자")

    def test_normalize_us(self) -> None:
        assert normalize_stock_symbol(US_CATEGORY, "aapl") == "AAPL"

    def test_normalize_crypto_rejected(self) -> None:
        with pytest.raises(ValueError):
            normalize_stock_symbol("₿ 암호화폐", "BTC")

    def test_us_limit_price_rounding(self) -> None:
        assert us_limit_price(OrderSide.BUY, 100.0, 0.005) == Decimal("100.50")
        assert us_limit_price(OrderSide.BUY, 100.001, 0.005) == Decimal("100.51")  # 올림
        assert us_limit_price(OrderSide.SELL, 100.009, 0.005) == Decimal("99.50")  # 내림
        assert us_limit_price(OrderSide.BUY, 0.5, 0.0) == Decimal("0.5000")  # $1 미만 0.0001 단위

    def test_credentials_parsing_and_masking(self) -> None:
        assert (CREDS.account_no, CREDS.product_code) == ("12345678", "01")
        assert "app-key" not in repr(CREDS) and "12345678" not in repr(CREDS)

    @pytest.mark.parametrize("account", ["1234", "", "12345678-0"])
    def test_credentials_bad_account(self, account: str) -> None:
        with pytest.raises(BrokerError):
            KisCredentials.from_values("k", "s", account)

    def test_credentials_missing_key(self) -> None:
        with pytest.raises(BrokerError):
            KisCredentials.from_values("", "s", "12345678-01")


# ----------------------------------------------------------------------
# 인증 / HTTP
# ----------------------------------------------------------------------


class TestAuth:
    def test_token_cached_across_instances(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES)
        broker.get_price(KR_CATEGORY, "005930")
        broker2, session2 = make_broker(tmp_path, KR_ROUTES)
        broker2.get_price(KR_CATEGORY, "005930")
        assert session.count("POST", "tokenP") == 1
        assert session2.count("POST", "tokenP") == 0  # 파일 캐시 재사용

    def test_token_file_has_no_app_secret(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES)
        broker.get_price(KR_CATEGORY, "005930")
        text = (tmp_path / "token.json").read_text(encoding="utf-8")
        assert "app-secret" not in text and "app-key" not in text

    def test_headers_use_paper_tr_id(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES)
        broker.get_cash(KR_CATEGORY)
        headers = session.calls[-1][2]["headers"]
        assert headers["tr_id"] == "VTTC8434R"
        assert headers["authorization"] == "Bearer tok-123"

    def test_real_env_uses_real_tr_id_and_is_live(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES, env=KisEnv.REAL)
        broker.get_cash(KR_CATEGORY)
        assert session.calls[-1][2]["headers"]["tr_id"] == "TTTC8434R"
        assert broker.IS_LIVE is True

    def test_token_failure_raises(self, tmp_path: Path) -> None:
        session = FakeSession({("POST", "/oauth2/tokenP"): FakeResp({"error_description": "invalid"}, 403)})
        broker = KisBroker(CREDS, session=session, sleep=lambda s: None, token_cache_path=tmp_path / "t.json")
        with pytest.raises(BrokerError, match="토큰 발급 실패"):
            broker.get_cash(KR_CATEGORY)

    def test_expired_token_reissued_once(self, tmp_path: Path) -> None:
        expired = FakeResp({"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token"}, 500)
        broker, session = make_broker(tmp_path, {
            ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): [expired, KR_PRICE],
        })
        assert broker.get_price(KR_CATEGORY, "005930") == 71_000
        assert session.count("POST", "tokenP") == 2

    def test_rate_limit_retried(self, tmp_path: Path) -> None:
        limited = FakeResp({"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수 초과"}, 500)
        broker, session = make_broker(tmp_path, {
            ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): [limited, KR_PRICE],
        })
        assert broker.get_price(KR_CATEGORY, "005930") == 71_000
        assert session.count("GET", "inquire-price") == 2

    def test_business_error_not_retried(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, {
            ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): {"rt_cd": "1", "msg_cd": "X", "msg1": "없는 종목"},
        })
        with pytest.raises(BrokerError, match="없는 종목"):
            broker.get_price(KR_CATEGORY, "005930")
        assert session.count("GET", "inquire-price") == 1

    def test_error_message_has_no_secrets(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, {
            ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): ConnectionError("boom app-secret-xyz"),
        })
        with pytest.raises(BrokerError) as exc_info:
            broker.get_price(KR_CATEGORY, "005930")
        assert "app-secret" not in str(exc_info.value)

    def test_zero_price_rejected(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, {
            ("GET", "/uapi/domestic-stock/v1/quotations/inquire-price"): {"rt_cd": "0", "output": {"stck_prpr": "0"}},
        })
        with pytest.raises(BrokerError, match="비정상 현재가"):
            broker.get_price(KR_CATEGORY, "005930")


# ----------------------------------------------------------------------
# 잔고
# ----------------------------------------------------------------------


class TestBalances:
    def test_kr_cash_is_conservative_min(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES)
        assert broker.get_cash(KR_CATEGORY) == 450_000

    def test_kr_position(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES)
        assert broker.get_position(KR_CATEGORY, "005930.KS") == (3.0, 70_000.0)
        assert broker.get_position(KR_CATEGORY, "000660") == (0.0, 0.0)


# ----------------------------------------------------------------------
# 한국 주식 주문
# ----------------------------------------------------------------------


class TestKrOrders:
    def test_buy_market_order_and_fill(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES)
        result = broker.place_order(kr_req(amount=150_000))
        post = [c for c in session.calls if c[0] == "POST" and "order-cash" in c[1]][0]
        body = post[2]["json"]
        assert body["ORD_QTY"] == "2" and body["ORD_DVSN"] == "01" and body["ORD_UNPR"] == "0"
        assert body["CANO"] == "12345678" and body["PDNO"] == "005930"
        assert post[2]["headers"]["tr_id"] == "VTTC0012U"
        assert result.success and result.order_id == "0000123456" and result.filled_qty == 2
        assert result.is_live is False  # 모의투자는 실제 돈이 아님

    def test_sell_all(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES)
        broker.place_order(kr_req(side=OrderSide.SELL, amount=0))
        post = [c for c in session.calls if c[0] == "POST" and "order-cash" in c[1]][0]
        assert post[2]["json"]["ORD_QTY"] == "3"
        assert post[2]["headers"]["tr_id"] == "VTTC0011U"

    def test_dry_run_never_posts(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES, dry_run=True)
        result = broker.place_order(kr_req())
        assert result.success and "DRY-RUN" in result.message
        assert session.count("POST", "order") == 0

    def test_dry_run_outside_hours_warns(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES, now=CLOSED, dry_run=True)
        result = broker.place_order(kr_req())
        assert result.success and "실주문이면 거부" in result.message

    def test_outside_hours_rejected(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES, now=CLOSED)
        result = broker.place_order(kr_req())
        assert not result.success and "장 운영 시간" in result.message
        assert session.count("POST", "order") == 0

    def test_max_order_cap(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES, max_order_krw=100_000)
        result = broker.place_order(kr_req(amount=150_000))
        assert not result.success and "상한" in result.message
        assert session.count("POST", "order") == 0

    def test_amount_below_one_share(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES)
        result = broker.place_order(kr_req(amount=50_000))
        assert not result.success and "1주" in result.message

    def test_insufficient_cash(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES, max_order_krw=10_000_000)
        result = broker.place_order(kr_req(amount=1_000_000))
        assert not result.success and "현금 부족" in result.message

    def test_whitelist(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES, allowed_symbols=["000660"])
        result = broker.place_order(kr_req())
        assert not result.success and "허용 목록" in result.message

    @pytest.mark.parametrize("price", [0.0, float("nan"), -1.0])
    def test_bad_price_rejected(self, tmp_path: Path, price: float) -> None:
        broker, session = make_broker(tmp_path, KR_ROUTES)
        assert not broker.place_order(kr_req(price=price)).success
        assert session.count("POST", "order") == 0

    def test_sell_without_holding(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, KR_ROUTES)
        result = broker.place_order(kr_req(side=OrderSide.SELL, symbol="000660"))
        assert not result.success and "매도 가능 수량" in result.message

    def test_broker_rejection_is_not_exception(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, {
            **KR_ROUTES,
            ("POST", "/uapi/domestic-stock/v1/trading/order-cash"): {"rt_cd": "1", "msg_cd": "APBK0013", "msg1": "주문가능금액 초과"},
        })
        result = broker.place_order(kr_req())
        assert not result.success and "주문가능금액 초과" in result.message

    def test_network_error_on_order_not_retried(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, {
            **KR_ROUTES,
            ("POST", "/uapi/domestic-stock/v1/trading/order-cash"): TimeoutError("timeout"),
        })
        with pytest.raises(BrokerError, match="자동 재시도하지 않"):
            broker.place_order(kr_req())
        assert session.count("POST", "order-cash") == 1

    def test_accepted_but_unfilled(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, {
            **KR_ROUTES,
            ("GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"): {"rt_cd": "0", "output1": []},
        })
        result = broker.place_order(kr_req())
        assert not result.success and result.order_id == "0000123456" and "체결 미확인" in result.message

    def test_missing_order_number_raises(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, {
            **KR_ROUTES,
            ("POST", "/uapi/domestic-stock/v1/trading/order-cash"): {"rt_cd": "0", "output": {}},
        })
        with pytest.raises(BrokerError, match="주문번호"):
            broker.place_order(kr_req())


# ----------------------------------------------------------------------
# 미국 주식
# ----------------------------------------------------------------------

US_PRICE_NAS = {"rt_cd": "0", "output": {"last": "200.00"}}
US_ROUTES = {
    ("GET", "/uapi/overseas-price/v1/quotations/price"): US_PRICE_NAS,
    ("GET", "/uapi/overseas-stock/v1/trading/inquire-psamount"): {"rt_cd": "0", "output": {"ovrs_ord_psbl_amt": "1000.00"}},
    ("GET", "/uapi/overseas-stock/v1/trading/inquire-balance"): {
        "rt_cd": "0", "output1": [{"ovrs_pdno": "AAPL", "ovrs_cblc_qty": "4", "ord_psbl_qty": "4", "pchs_avg_pric": "190.5"}],
    },
    ("POST", "/uapi/overseas-stock/v1/trading/order"): {"rt_cd": "0", "output": {"ODNO": "0030000001"}},
    ("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl"): {
        "rt_cd": "0", "output": [{"odno": "0030000001", "ft_ccld_qty": "2", "ft_ccld_unpr3": "200.10"}],
    },
}


def us_req(side: OrderSide = OrderSide.BUY, amount: float = 450.0) -> OrderRequest:
    return OrderRequest(category=US_CATEGORY, symbol="AAPL", name="Apple", side=side, price=200.0, amount=amount)


class TestUsOrders:
    def test_buy_marketable_limit(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, US_ROUTES, now=US_OPEN)
        result = broker.place_order(us_req(amount=450.0))
        post = [c for c in session.calls if c[0] == "POST" and "trading/order" in c[1]][0]
        body = post[2]["json"]
        assert body["OVRS_ORD_UNPR"] == "201" and body["ORD_QTY"] == "2"  # 450 // 201 = 2
        assert body["OVRS_EXCG_CD"] == "NASD" and body["ORD_DVSN"] == "00"
        assert post[2]["headers"]["tr_id"] == "VTTT1002U"
        assert result.success and result.filled_qty == 2 and result.avg_fill_price == pytest.approx(200.10)

    def test_sell_uses_paper_sell_tr_id(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, US_ROUTES, now=US_OPEN)
        broker.place_order(us_req(side=OrderSide.SELL, amount=0))
        post = [c for c in session.calls if c[0] == "POST" and "trading/order" in c[1]][0]
        assert post[2]["headers"]["tr_id"] == "VTTT1001U"
        assert post[2]["json"]["ORD_QTY"] == "4" and post[2]["json"]["OVRS_ORD_UNPR"] == "199"

    def test_exchange_autodetect_falls_through(self, tmp_path: Path) -> None:
        empty = {"rt_cd": "0", "output": {"last": ""}}
        broker, session = make_broker(tmp_path, {
            **US_ROUTES, ("GET", "/uapi/overseas-price/v1/quotations/price"): [empty, US_PRICE_NAS],
        }, now=US_OPEN)
        assert broker.resolve_us_exchange("KO") == "NYSE"
        assert broker.resolve_us_exchange("KO") == "NYSE"  # 캐시
        assert session.count("GET", "quotations/price") == 2

    def test_exchange_override(self, tmp_path: Path) -> None:
        broker, session = make_broker(tmp_path, US_ROUTES, now=US_OPEN, us_exchanges={"aapl": "nyse"})
        assert broker.resolve_us_exchange("AAPL") == "NYSE"
        assert session.count("GET", "quotations/price") == 0

    def test_bad_exchange_override(self, tmp_path: Path) -> None:
        with pytest.raises(BrokerError):
            make_broker(tmp_path, US_ROUTES, us_exchanges={"AAPL": "NAS"})

    def test_us_cap(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, US_ROUTES, now=US_OPEN, max_order_usd=300)
        assert "상한" in broker.place_order(us_req(amount=450)).message

    def test_us_position(self, tmp_path: Path) -> None:
        broker, _ = make_broker(tmp_path, US_ROUTES, now=US_OPEN)
        assert broker.get_position(US_CATEGORY, "AAPL") == (4.0, 190.5)


def test_crypto_order_rejected(tmp_path: Path) -> None:
    broker, _ = make_broker(tmp_path, KR_ROUTES)
    req = OrderRequest(category="₿ 암호화폐", symbol="BTC", name="BTC", side=OrderSide.BUY, price=1.0, amount=10.0)
    assert not broker.place_order(req).success


def test_invalid_constructor_values(tmp_path: Path) -> None:
    with pytest.raises(BrokerError):
        make_broker(tmp_path, KR_ROUTES, max_order_krw=0)
    with pytest.raises(BrokerError):
        make_broker(tmp_path, KR_ROUTES, us_slippage_pct=0.2)


def test_list_positions_kr(tmp_path: Path) -> None:
    broker, _ = make_broker(tmp_path, KR_ROUTES)
    assert broker.list_positions(KR_CATEGORY) == {"005930": (3.0, 70_000.0)}


def test_list_positions_us_merges_exchanges_and_caches(tmp_path: Path) -> None:
    broker, session = make_broker(tmp_path, US_ROUTES, now=US_OPEN)
    assert broker.list_positions(US_CATEGORY) == {"AAPL": (4.0, 190.5)}
    assert session.count("GET", "inquire-balance") == 3  # NASD/NYSE/AMEX
    assert broker.resolve_us_exchange("AAPL") == "NASD"  # 잔고에서 거래소 캐시


def test_slash_ticker_allowed() -> None:
    assert normalize_stock_symbol(US_CATEGORY, "brk/b") == "BRK/B"
