# -*- coding: utf-8 -*-
"""
업비트(Upbit) 현물 실전 브로커.

목적: BaseBroker 인터페이스를 업비트 REST API로 구현한다. AutoTrader/실전 봇은
    "지금이 페이퍼인지 실전인지" 몰라도 되며, 이 클래스는 broker_factory.get_broker()
    를 통해서만 생성한다 (LIVE_TRADING 이중 잠금 통과 필요).

안전 설계
---------
1. 허용 마켓 화이트리스트 (기본 KRW-BTC 하나). 그 외 심볼 주문은 거부.
2. 주문 POST는 절대 자동 재시도하지 않는다 (중복 체결 방지). 실패는 BrokerError로 올린다.
3. dry_run=True면 주문 본문만 검증하고 서버로 보내지 않는다 (가상 검증용).
4. API 키/시크릿은 로그·예외 메시지에 절대 출력하지 않는다.
5. 외부 의존성 없이 표준 라이브러리로 JWT(HS256)를 만든다.

업비트 인증 (docs.upbit.com/kr/reference/auth)
-------------------------------------------
- payload: access_key, nonce(uuid4), (파라미터/본문이 있으면) query_hash(SHA512) + query_hash_alg
- 시장가 매수: side=bid, ord_type=price, price=투입 KRW (volume 제외)
- 시장가 매도: side=ask, ord_type=market, volume=수량 (price 제외)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from src.execution.base_broker import (
    BaseBroker,
    BrokerError,
    OrderRequest,
    OrderResult,
    OrderSide,
)

logger = logging.getLogger(__name__)

CRYPTO_CATEGORY = "₿ 암호화폐"
BASE_URL = "https://api.upbit.com"
MIN_ORDER_KRW = 5_000.0  # 업비트 KRW 마켓 최소 주문 금액
DEFAULT_ALLOWED_MARKETS = frozenset({"KRW-BTC"})
_FINAL_STATES = {"done", "cancel"}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_jwt(access_key: str, secret_key: str, query_string: Optional[str] = None) -> str:
    """업비트 인증용 JWT(HS256)를 생성한다.

    Args:
        access_key: 업비트 Access Key.
        secret_key: 업비트 Secret Key (Base64 디코딩 불필요 — 문자열 그대로 서명 키).
        query_string: 요청 파라미터/본문을 urlencode한 문자열 (없으면 None).

    Returns:
        "header.payload.signature" 형식의 JWT 문자열.
    """
    payload: dict[str, str] = {"access_key": access_key, "nonce": str(uuid.uuid4())}
    if query_string:
        payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
        payload["query_hash_alg"] = "SHA512"
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


def _format_volume(qty: float) -> str:
    """수량을 업비트 허용 소수 8자리로 내림 변환한다 (올림하면 잔고 초과 주문이 됨)."""
    return format(Decimal(str(qty)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN), "f")


def _format_krw(amount: float) -> str:
    """KRW 금액을 정수 문자열로 내림 변환한다."""
    return str(int(Decimal(str(amount)).to_integral_value(rounding=ROUND_DOWN)))


class UpbitBroker(BaseBroker):
    """업비트 KRW 현물 브로커.

    Args:
        access_key: 업비트 Access Key.
        secret_key: 업비트 Secret Key.
        allowed_markets: 주문 허용 마켓 집합 (기본 {"KRW-BTC"}).
        dry_run: True면 주문을 서버로 전송하지 않고 검증만 한다.
        session: requests.Session 호환 객체 (테스트 주입용). 생략 시 requests.Session().
        timeout: HTTP 타임아웃(초).
        sleep: 체결 확인 대기 함수 (테스트 주입용).
        fill_poll_attempts: 체결 확인 최대 횟수.

    Raises:
        BrokerError: 키가 비어 있는 경우.
    """

    IS_LIVE = True

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        allowed_markets: frozenset[str] | set[str] = DEFAULT_ALLOWED_MARKETS,
        dry_run: bool = False,
        session: Any = None,
        timeout: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        fill_poll_attempts: int = 6,
    ) -> None:
        if not access_key or not secret_key:
            raise BrokerError("업비트 API 키(UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY)가 비어 있습니다.")
        self._access_key = access_key
        self._secret_key = secret_key
        self.allowed_markets = frozenset(allowed_markets)
        self.dry_run = dry_run
        self._timeout = timeout
        self._sleep = sleep
        self._fill_poll_attempts = fill_poll_attempts
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, str]] = None,
        auth: bool = True,
    ) -> Any:
        """업비트 REST 호출. 실패 시 BrokerError (키/서명은 메시지에 포함하지 않는다)."""
        headers: dict[str, str] = {"Accept": "application/json"}
        query_string = urlencode(params) if params else None
        if auth:
            headers["Authorization"] = "Bearer " + build_jwt(
                self._access_key, self._secret_key, query_string
            )
        kwargs: dict[str, Any] = {"headers": headers, "timeout": self._timeout}
        if method == "GET":
            kwargs["params"] = params
        else:
            kwargs["json"] = params
        try:
            resp = self._session.request(method, BASE_URL + path, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 네트워크 계층 오류를 BrokerError로 통일
            raise BrokerError(f"업비트 통신 실패({path}): {type(exc).__name__}") from exc

        status = getattr(resp, "status_code", 0)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = None
        if not 200 <= status < 300:
            detail = ""
            if isinstance(body, dict):
                err = body.get("error") or {}
                detail = f"{err.get('name', '')} {err.get('message', '')}".strip()
            raise BrokerError(f"업비트 API 오류({path}) HTTP {status}: {detail or '알 수 없음'}")
        return body

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[dict[str, Any]]:
        """전체 계좌 잔고를 조회한다 (자산조회 권한 필요)."""
        data = self._request("GET", "/v1/accounts")
        if not isinstance(data, list):
            raise BrokerError("업비트 계좌 응답 형식이 올바르지 않습니다.")
        return data

    def _balance_of(self, currency: str) -> dict[str, Any]:
        for acc in self.get_accounts():
            if acc.get("currency") == currency:
                return acc
        return {}

    def get_cash(self, category: str = CRYPTO_CATEGORY) -> float:
        """주문 가능 KRW 잔고(balance, 미체결 묶인 금액 제외)."""
        return float(self._balance_of("KRW").get("balance", 0) or 0)

    def get_holding_qty(self, category: str, symbol: str) -> float:
        """보유 수량 (주문 가능 balance 기준)."""
        return float(self._balance_of(symbol.upper()).get("balance", 0) or 0)

    def get_position(self, symbol: str) -> tuple[float, float]:
        """(보유 수량, 평균 매수가 KRW). 미보유면 (0.0, 0.0)."""
        acc = self._balance_of(symbol.upper())
        return (
            float(acc.get("balance", 0) or 0),
            float(acc.get("avg_buy_price", 0) or 0),
        )

    def get_price(self, market: str = "KRW-BTC") -> float:
        """현재가(KRW). 공개 API라 인증 불필요."""
        data = self._request("GET", "/v1/ticker", {"markets": market}, auth=False)
        try:
            return float(data[0]["trade_price"])
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise BrokerError(f"업비트 시세 응답 파싱 실패: {market}") from exc

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    def _fail(self, request: OrderRequest, message: str) -> OrderResult:
        logger.warning(f"[UpbitBroker] 주문 거부: {message}")
        return OrderResult(success=False, message=message, request=request, is_live=True)

    def _build_body(self, request: OrderRequest, market: str) -> tuple[Optional[dict[str, str]], str]:
        """주문 본문을 만든다. (본문, 실패사유) — 본문이 None이면 거부."""
        if request.side == OrderSide.BUY:
            if request.amount < MIN_ORDER_KRW:
                return None, f"최소 주문 금액 미달: {request.amount:,.0f} < {MIN_ORDER_KRW:,.0f}"
            cash = self.get_cash(request.category)
            if request.amount > cash:
                return None, f"KRW 잔고 부족: 주문 {request.amount:,.0f} > 보유 {cash:,.0f}"
            return {
                "market": market,
                "side": "bid",
                "ord_type": "price",
                "price": _format_krw(request.amount),
            }, ""

        qty = self.get_holding_qty(request.category, request.symbol)
        if request.amount > 0 and request.price > 0:
            qty = min(qty, request.amount / request.price)
        if qty <= 0:
            return None, "보유 수량이 없어 매도할 수 없습니다."
        if qty * request.price < MIN_ORDER_KRW:
            return None, f"최소 주문 금액 미달: 매도 평가액 {qty * request.price:,.0f}원 < {MIN_ORDER_KRW:,.0f}원"
        return {
            "market": market,
            "side": "ask",
            "ord_type": "market",
            "volume": _format_volume(qty),
        }, ""

    def place_order(self, request: OrderRequest) -> OrderResult:
        """시장가 주문을 실행한다 (dry_run이면 검증만).

        Args:
            request: 주문 요청 (category는 암호화폐, symbol은 허용 마켓의 코인).

        Returns:
            OrderResult. 업비트가 주문을 거절하거나 사전 검증에 실패하면 success=False.

        Raises:
            BrokerError: 통신/인증 오류 (주문이 접수됐는지 불명확할 수 있으므로 호출 측에서
                반드시 잔고를 재확인해야 한다 — 자동 재시도 금지).
        """
        if request.category != CRYPTO_CATEGORY:
            return self._fail(request, f"업비트 브로커는 암호화폐만 지원합니다: {request.category}")
        market = f"KRW-{request.symbol.upper()}"
        if market not in self.allowed_markets:
            return self._fail(request, f"허용되지 않은 마켓: {market} (허용: {sorted(self.allowed_markets)})")

        body, reason = self._build_body(request, market)
        if body is None:
            return self._fail(request, reason)

        if self.dry_run:
            msg = f"[DRY-RUN] 전송 생략 — 주문 본문 검증 통과: {body}"
            logger.info(f"[UpbitBroker] {msg}")
            return OrderResult(success=True, message=msg, request=request, is_live=False)

        logger.info(f"[UpbitBroker] 실전 주문 전송: {body}")
        created = self._request("POST", "/v1/orders", body)
        order_uuid = created.get("uuid") if isinstance(created, dict) else None
        if not order_uuid:
            raise BrokerError("업비트 주문 응답에 uuid가 없습니다 — 접수 여부 불명, 잔고를 직접 확인하세요.")
        return self._confirm_fill(request, str(order_uuid))

    def _confirm_fill(self, request: OrderRequest, order_uuid: str) -> OrderResult:
        """주문 uuid의 체결 결과를 폴링해 OrderResult로 만든다."""
        info: dict[str, Any] = {}
        for _ in range(self._fill_poll_attempts):
            info = self._request("GET", "/v1/order", {"uuid": order_uuid}) or {}
            if info.get("state") in _FINAL_STATES:
                break
            self._sleep(0.5)

        executed = float(info.get("executed_volume", 0) or 0)
        fee = float(info.get("paid_fee", 0) or 0)
        state = info.get("state", "unknown")
        if executed > 0:
            msg = f"체결 완료(uuid={order_uuid}, state={state}): 수량 {executed:.8f}, 수수료 {fee:,.2f}원"
            logger.info(f"[UpbitBroker] {msg}")
            return OrderResult(success=True, message=msg, request=request, is_live=True)
        return self._fail(request, f"체결 확인 실패(uuid={order_uuid}, state={state}) — 업비트 앱에서 확인하세요.")
