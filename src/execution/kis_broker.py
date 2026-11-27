# -*- coding: utf-8 -*-
"""
한국투자증권(KIS) Open API 주식 브로커 — 한국 주식 + 미국 주식.

목적: BaseBroker 인터페이스를 KIS REST API로 구현한다. 업비트 브로커(암호화폐)와
    같은 규약을 따르므로, 봇/AutoTrader는 브로커 종류를 몰라도 된다.
    반드시 broker_factory.get_kis_broker()를 통해서 생성한다.

모드 (KIS_ENV)
--------------
- "vts"  : 모의투자 서버 (openapivts...:29443). 가짜 돈. **기본값.**
- "prod" : 실전 서버 (openapi...:9443). 실제 돈 → LIVE_TRADING 이중 잠금 필수.
- 어떤 모드든 dry_run=True면 주문을 서버로 보내지 않고 검증만 한다.

안전 설계
---------
1. 주문 POST는 자동 재시도하지 않는다 (중복 체결 방지). 유일한 예외는 게이트웨이가
   "토큰 만료"로 거절한 경우 — 이때는 주문이 접수되지 않았음이 확실하므로 토큰 재발급 후 1회.
2. 조회(GET)는 네트워크 오류 / 5xx / 초당 호출 한도(EGW00201)에 대해 지수 백오프 재시도.
3. 1회 주문 금액 상한(max_order_krw / max_order_usd) — 전략·봇 버그가 있어도 한 번에
   큰돈이 나가지 않는다.
4. 장 운영 시간 외 주문 거부 (dry_run이면 경고만).
5. 종목코드 형식 검증 + 선택적 화이트리스트.
6. 앱키/시크릿/토큰/계좌번호는 로그·예외 메시지에 출력하지 않는다.
7. 접근 토큰은 data/kis_token_<env>.json에 캐시한다 (KIS는 토큰 발급을 1분 1회로 제한,
   유효기간 24시간). data/*.json은 .gitignore 대상.

주문 방식
---------
- 한국 주식: 시장가(ORD_DVSN=01), 정수 주 단위.
- 미국 주식: KIS 해외주식은 시장가를 지원하지 않으므로 "시장성 지정가"로 낸다
  (매수 = 기준가 × (1+슬리피지) 올림, 매도 = 기준가 × (1-슬리피지) 내림).

API 근거: apiportal.koreainvestment.com (국내주식 주문/잔고/체결, 해외주식 주문/잔고/체결/시세).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from src.common.retry import retry_with_backoff
from src.execution.base_broker import (
    BaseBroker,
    BrokerError,
    OrderRequest,
    OrderResult,
    OrderSide,
)
from src.execution.market_hours import KR_CATEGORY, KST, NEW_YORK, US_CATEGORY, is_market_open

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOKEN_DIR = _PROJECT_ROOT / "data"


class KisEnv(str, Enum):
    """KIS 서버 종류."""

    PAPER = "vts"  # 모의투자
    REAL = "prod"  # 실전


BASE_URLS: dict[KisEnv, str] = {
    KisEnv.PAPER: "https://openapivts.koreainvestment.com:29443",
    KisEnv.REAL: "https://openapi.koreainvestment.com:9443",
}

#: 서버별 최소 호출 간격(초). 모의투자는 초당 2건, 실전은 초당 20건 제한.
MIN_CALL_INTERVAL: dict[KisEnv, float] = {KisEnv.PAPER: 0.55, KisEnv.REAL: 0.06}

# tr_id: (실전, 모의)
TR_IDS: dict[str, tuple[str, str]] = {
    "kr_buy": ("TTTC0012U", "VTTC0012U"),
    "kr_sell": ("TTTC0011U", "VTTC0011U"),
    "kr_balance": ("TTTC8434R", "VTTC8434R"),
    "kr_ccld": ("TTTC8001R", "VTTC8001R"),
    "kr_price": ("FHKST01010100", "FHKST01010100"),
    "us_buy": ("TTTT1002U", "VTTT1002U"),
    "us_sell": ("TTTT1006U", "VTTT1001U"),
    "us_balance": ("TTTS3012R", "VTTS3012R"),
    "us_psamount": ("TTTS3007R", "VTTS3007R"),
    "us_ccnl": ("TTTS3035R", "VTTS3035R"),
    "us_price": ("HHDFS00000300", "HHDFS00000300"),
}

#: 미국 거래소 코드: 주문/잔고용(4자리) ↔ 시세용(3자리)
US_ORDER_TO_QUOTE_EXCHANGE: dict[str, str] = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}

_KR_CODE_RE = re.compile(r"^\d{6}$")
_US_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
_TOKEN_EXPIRED_CODES = {"EGW00123", "EGW00121"}
_RATE_LIMIT_CODE = "EGW00201"


class _TransientKisError(BrokerError):
    """재시도해도 되는 일시적 오류 (조회 전용)."""


class _TokenExpiredError(BrokerError):
    """게이트웨이가 토큰 만료로 거절 — 요청은 처리되지 않았다."""


@dataclass(frozen=True)
class KisCredentials:
    """KIS 인증 정보.

    Attributes:
        app_key: 앱키 (모의투자와 실전은 앱키가 서로 다르다).
        app_secret: 앱시크릿.
        account_no: 종합계좌번호 앞 8자리 (CANO).
        product_code: 계좌상품코드 뒤 2자리 (주식은 보통 "01").
    """

    app_key: str
    app_secret: str
    account_no: str
    product_code: str = "01"

    def __repr__(self) -> str:  # 비밀 정보가 로그/트레이스백에 찍히지 않도록
        return f"KisCredentials(account=****{self.account_no[-2:]}-{self.product_code})"

    @classmethod
    def from_values(cls, app_key: str, app_secret: str, account: str) -> "KisCredentials":
        """"12345678-01" 또는 "1234567801" 형태의 계좌번호를 파싱해 생성한다.

        Raises:
            BrokerError: 값이 비었거나 계좌번호 형식이 틀린 경우.
        """
        digits = re.sub(r"\D", "", account or "")
        if not app_key or not app_secret:
            raise BrokerError("KIS 앱키/앱시크릿(KIS_APP_KEY / KIS_APP_SECRET)이 비어 있습니다.")
        if len(digits) != 10:
            raise BrokerError("KIS_ACCOUNT_NO 형식 오류: '12345678-01'처럼 8자리-2자리로 입력하세요.")
        return cls(app_key=app_key, app_secret=app_secret, account_no=digits[:8], product_code=digits[8:])


# ----------------------------------------------------------------------
# 순수 헬퍼 (단독 테스트 가능)
# ----------------------------------------------------------------------


def normalize_stock_symbol(category: str, symbol: str) -> str:
    """종목코드를 KIS 형식으로 정규화하고 검증한다.

    Args:
        category: 한국/미국 주식 카테고리.
        symbol: "005930", "005930.KS", "aapl" 등.

    Returns:
        한국: 6자리 숫자 코드 / 미국: 대문자 티커.

    Raises:
        ValueError: 형식이 맞지 않거나 주식 카테고리가 아닌 경우.
    """
    text = (symbol or "").strip().upper()
    if category == KR_CATEGORY:
        code = re.sub(r"\.(KS|KQ)$", "", text)
        if not _KR_CODE_RE.match(code):
            raise ValueError(f"한국 주식 종목코드는 6자리 숫자여야 합니다: {symbol!r}")
        return code
    if category == US_CATEGORY:
        if not _US_TICKER_RE.match(text):
            raise ValueError(f"미국 주식 티커 형식 오류: {symbol!r}")
        return text
    raise ValueError(f"KIS 브로커는 한국/미국 주식만 지원합니다: {category}")


def us_limit_price(side: OrderSide, ref_price: float, slippage_pct: float) -> Decimal:
    """미국 주식 '시장성 지정가'를 계산한다.

    호가 단위: $1 이상 0.01, $1 미만 0.0001. 매수는 올림, 매도는 내림
    (반대로 하면 슬리피지 허용폭이 줄어 미체결 가능성이 커진다).

    Args:
        side: 매수/매도.
        ref_price: 기준가(현재가).
        slippage_pct: 허용 슬리피지 (0.005 = 0.5%).

    Returns:
        호가 단위에 맞춘 지정가 (Decimal).
    """
    raw = Decimal(str(ref_price)) * (
        Decimal(1) + Decimal(str(slippage_pct)) if side == OrderSide.BUY
        else Decimal(1) - Decimal(str(slippage_pct))
    )
    tick = Decimal("0.01") if raw >= 1 else Decimal("0.0001")
    rounding = ROUND_CEILING if side == OrderSide.BUY else ROUND_FLOOR
    return (raw / tick).to_integral_value(rounding=rounding) * tick


def _f(value: Any) -> float:
    """KIS 응답의 문자열 숫자를 float로 (빈 값/오류는 0)."""
    try:
        result = float(str(value).replace(",", "")) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


# ----------------------------------------------------------------------
# 브로커
# ----------------------------------------------------------------------


class KisBroker(BaseBroker):
    """한국투자증권 한국/미국 주식 브로커.

    Args:
        credentials: KIS 인증 정보.
        env: KisEnv.PAPER(모의투자, 기본) 또는 KisEnv.REAL(실전).
        dry_run: True면 주문을 서버로 보내지 않고 검증만 한다 (조회는 실제 API).
        max_order_krw: 한국 주식 1회 주문 금액 상한(원).
        max_order_usd: 미국 주식 1회 주문 금액 상한(달러).
        us_slippage_pct: 미국 주식 시장성 지정가 슬리피지 허용폭.
        allowed_symbols: 주문 허용 종목 집합 (None이면 형식 검증만).
        us_exchanges: 미국 티커 → 주문 거래소 코드(NASD/NYSE/AMEX) 고정 매핑.
            없는 티커는 시세 API로 자동 탐색 후 캐시한다.
        enforce_market_hours: 장외 주문 거부 여부 (dry_run이면 경고만).
        us_cash_probe_symbol: get_cash(미국)에서 주문가능금액 조회에 쓸 기준 종목.
        session: requests.Session 호환 객체 (테스트 주입용).
        timeout: HTTP 타임아웃(초).
        sleep: 대기 함수 (테스트 주입용).
        clock: 단조 시계 함수 (호출 간격 제어용, 테스트 주입용).
        now_fn: 현재 UTC 시각 함수 (장 시간/조회일자 계산용).
        token_cache_path: 토큰 캐시 파일 경로 (None이면 data/kis_token_<env>.json).
        retry_backoff: 조회 재시도 초기 대기(초).
        fill_poll_attempts: 체결 확인 최대 횟수.

    Raises:
        BrokerError: 인증 정보가 비었거나 상한값이 잘못된 경우.
    """

    def __init__(
        self,
        credentials: KisCredentials,
        env: KisEnv = KisEnv.PAPER,
        dry_run: bool = False,
        max_order_krw: float = 500_000.0,
        max_order_usd: float = 500.0,
        us_slippage_pct: float = 0.005,
        allowed_symbols: Optional[Iterable[str]] = None,
        us_exchanges: Optional[dict[str, str]] = None,
        enforce_market_hours: bool = True,
        us_cash_probe_symbol: str = "AAPL",
        session: Any = None,
        timeout: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now_fn: Optional[Callable[[], datetime]] = None,
        token_cache_path: Optional[Path] = None,
        retry_backoff: float = 0.5,
        fill_poll_attempts: int = 5,
    ) -> None:
        if not isinstance(credentials, KisCredentials):
            raise BrokerError("KisCredentials가 필요합니다.")
        if max_order_krw <= 0 or max_order_usd <= 0:
            raise BrokerError("1회 주문 상한(max_order_krw/max_order_usd)은 0보다 커야 합니다.")
        if not 0 <= us_slippage_pct < 0.05:
            raise BrokerError("us_slippage_pct는 0~5% 범위여야 합니다.")
        self._creds = credentials
        self.env = KisEnv(env)
        self.dry_run = dry_run
        # 실제 돈이 오가는 경우에만 IS_LIVE=True (모의투자는 가짜 돈).
        self.IS_LIVE = self.env == KisEnv.REAL
        self.max_order_krw = float(max_order_krw)
        self.max_order_usd = float(max_order_usd)
        self.us_slippage_pct = float(us_slippage_pct)
        self.allowed_symbols = (
            frozenset(s.strip().upper() for s in allowed_symbols) if allowed_symbols else None
        )
        self._us_exchange_cache: dict[str, str] = {
            k.upper(): v.upper() for k, v in (us_exchanges or {}).items()
        }
        for code in self._us_exchange_cache.values():
            if code not in US_ORDER_TO_QUOTE_EXCHANGE:
                raise BrokerError(f"미국 거래소 코드는 NASD/NYSE/AMEX 중 하나여야 합니다: {code}")
        self.enforce_market_hours = enforce_market_hours
        self.us_cash_probe_symbol = us_cash_probe_symbol
        self._timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._token_path = token_cache_path or (DEFAULT_TOKEN_DIR / f"kis_token_{self.env.value}.json")
        self._retry_backoff = retry_backoff
        self._fill_poll_attempts = fill_poll_attempts
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._last_call: float = -1e9
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    # ------------------------------------------------------------------
    # 표시용
    # ------------------------------------------------------------------

    @property
    def mode_label(self) -> str:
        """사람이 읽는 실행 모드 (로그/CLI 출력용)."""
        server = "🔴 실전" if self.env == KisEnv.REAL else "모의투자"
        return f"KIS {server}" + (" / DRY-RUN" if self.dry_run else "")

    # ------------------------------------------------------------------
    # 인증 (토큰)
    # ------------------------------------------------------------------

    def _key_fingerprint(self) -> str:
        """캐시 파일이 다른 앱키의 토큰을 재사용하지 않도록 하는 지문 (키 원문은 저장 안 함)."""
        return hashlib.sha256(self._creds.app_key.encode("utf-8")).hexdigest()[:16]

    def _load_cached_token(self) -> bool:
        try:
            data = json.loads(self._token_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return False
        if data.get("fingerprint") != self._key_fingerprint():
            return False
        expires_at = float(data.get("expires_at", 0))
        if expires_at - time.time() < 600:  # 만료 10분 전부터는 새로 발급
            return False
        self._token, self._token_expires_at = str(data["access_token"]), expires_at
        return True

    def _issue_token(self) -> None:
        """접근 토큰을 발급받아 메모리/파일에 캐시한다."""
        body = {
            "grant_type": "client_credentials",
            "appkey": self._creds.app_key,
            "appsecret": self._creds.app_secret,
        }
        self._throttle()
        try:
            resp = self._session.request(
                "POST", BASE_URLS[self.env] + "/oauth2/tokenP",
                json=body, headers={"content-type": "application/json"}, timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"KIS 토큰 발급 통신 실패: {type(exc).__name__}") from exc
        data = self._json(resp)
        token = data.get("access_token") if isinstance(data, dict) else None
        if getattr(resp, "status_code", 0) != 200 or not token:
            detail = ""
            if isinstance(data, dict):
                detail = str(data.get("error_description") or data.get("msg1") or "")
            raise BrokerError(
                f"KIS 토큰 발급 실패 HTTP {getattr(resp, 'status_code', '?')}: {detail or '알 수 없음'} "
                "(앱키/시크릿이 KIS_ENV 서버와 맞는지 확인 — 모의투자와 실전 앱키는 다릅니다)"
            )
        expires_in = _f(data.get("expires_in")) or 86_400
        self._token = str(token)
        self._token_expires_at = time.time() + expires_in
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(
                json.dumps({
                    "fingerprint": self._key_fingerprint(),
                    "access_token": self._token,
                    "expires_at": self._token_expires_at,
                }),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("KIS 토큰 캐시 파일 저장 실패 — 메모리 토큰만 사용합니다.")

    def _ensure_token(self, force: bool = False) -> str:
        if force:
            self._token = None
        if self._token and self._token_expires_at - time.time() > 600:
            return self._token
        if force or not self._load_cached_token():
            self._issue_token()
        assert self._token is not None
        return self._token

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        wait = MIN_CALL_INTERVAL[self.env] - (self._clock() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = self._clock()

    @staticmethod
    def _json(resp: Any) -> Any:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return None

    def _tr(self, key: str) -> str:
        real, paper = TR_IDS[key]
        return real if self.env == KisEnv.REAL else paper

    def _call_once(self, method: str, path: str, tr_key: str, params: dict[str, str]) -> dict[str, Any]:
        """KIS REST 1회 호출. 오류 종류별로 다른 예외를 던진다 (메시지에 비밀 정보 없음)."""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self._creds.app_key,
            "appsecret": self._creds.app_secret,
            "tr_id": self._tr(tr_key),
            "custtype": "P",
        }
        kwargs: dict[str, Any] = {"headers": headers, "timeout": self._timeout}
        kwargs["params" if method == "GET" else "json"] = params
        self._throttle()
        try:
            resp = self._session.request(method, BASE_URLS[self.env] + path, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise _TransientKisError(f"KIS 통신 실패({path}): {type(exc).__name__}") from exc

        status = getattr(resp, "status_code", 0)
        body = self._json(resp)
        msg_cd = str(body.get("msg_cd", "")) if isinstance(body, dict) else ""
        msg = str(body.get("msg1", "")).strip() if isinstance(body, dict) else ""
        if msg_cd in _TOKEN_EXPIRED_CODES:
            raise _TokenExpiredError(f"KIS 토큰 만료({path})")
        if msg_cd == _RATE_LIMIT_CODE or status >= 500:
            raise _TransientKisError(f"KIS 일시 오류({path}) HTTP {status} {msg_cd} {msg}".strip())
        if not 200 <= status < 300 or not isinstance(body, dict):
            raise BrokerError(f"KIS API 오류({path}) HTTP {status}: {msg_cd} {msg}".strip())
        return body

    def _get(self, path: str, tr_key: str, params: dict[str, str]) -> dict[str, Any]:
        """조회 API — 토큰 만료 시 1회 재발급, 일시 오류는 지수 백오프 재시도.

        Raises:
            BrokerError: 재시도 후에도 실패하거나 rt_cd != "0" 인 경우.
        """

        def attempt() -> dict[str, Any]:
            try:
                return self._call_once("GET", path, tr_key, params)
            except _TokenExpiredError:
                self._ensure_token(force=True)
                return self._call_once("GET", path, tr_key, params)

        body = retry_with_backoff(
            attempt, max_retries=3, backoff_seconds=self._retry_backoff,
            retry_exceptions=(_TransientKisError,), logger=logger, action_name=f"KIS 조회 {path}",
        )
        if str(body.get("rt_cd")) != "0":
            raise BrokerError(f"KIS 조회 실패({path}): {body.get('msg_cd', '')} {body.get('msg1', '')}".strip())
        return body

    def _post_order(self, path: str, tr_key: str, body: dict[str, str]) -> dict[str, Any]:
        """주문 API — 자동 재시도 금지 (토큰 만료로 게이트웨이가 거절한 경우만 1회 재전송).

        Raises:
            BrokerError: 통신 오류 등으로 접수 여부가 불명확한 경우 (호출 측이 잔고/체결 재확인).
        """
        try:
            return self._call_once("POST", path, tr_key, body)
        except _TokenExpiredError:
            self._ensure_token(force=True)
            return self._call_once("POST", path, tr_key, body)
        except _TransientKisError as exc:
            raise BrokerError(
                f"{exc} — 주문 접수 여부가 불명확합니다. 자동 재시도하지 않으니 KIS 앱에서 체결 내역을 확인하세요."
            ) from exc

    # ------------------------------------------------------------------
    # 시세
    # ------------------------------------------------------------------

    def _us_quote(self, symbol: str, quote_exchange: str) -> float:
        body = self._get(
            "/uapi/overseas-price/v1/quotations/price", "us_price",
            {"AUTH": "", "EXCD": quote_exchange, "SYMB": symbol},
        )
        return _f((body.get("output") or {}).get("last"))

    def resolve_us_exchange(self, symbol: str) -> str:
        """미국 티커의 주문 거래소 코드(NASD/NYSE/AMEX)를 찾는다 (캐시).

        Raises:
            BrokerError: 어느 거래소에서도 시세가 없는 경우.
        """
        symbol = symbol.upper()
        if symbol in self._us_exchange_cache:
            return self._us_exchange_cache[symbol]
        for order_code, quote_code in US_ORDER_TO_QUOTE_EXCHANGE.items():
            try:
                if self._us_quote(symbol, quote_code) > 0:
                    self._us_exchange_cache[symbol] = order_code
                    return order_code
            except BrokerError:
                continue
        raise BrokerError(
            f"{symbol}: NASD/NYSE/AMEX 어디에서도 시세를 찾지 못했습니다 — "
            "KIS_US_EXCHANGES에 'TICKER:NYSE' 형태로 지정하세요."
        )

    def get_price(self, category: str, symbol: str) -> float:
        """현재가 (한국: 원, 미국: 달러).

        Raises:
            BrokerError: 조회 실패 또는 비정상 가격(0/NaN).
        """
        code = normalize_stock_symbol(category, symbol)
        if category == KR_CATEGORY:
            body = self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-price", "kr_price",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            )
            price = _f((body.get("output") or {}).get("stck_prpr"))
        else:
            exch = self.resolve_us_exchange(code)
            price = self._us_quote(code, US_ORDER_TO_QUOTE_EXCHANGE[exch])
        if price <= 0:
            raise BrokerError(f"{code}: 비정상 현재가({price}) — 매매하지 않습니다.")
        return price

    # ------------------------------------------------------------------
    # 잔고
    # ------------------------------------------------------------------

    def _account(self) -> dict[str, str]:
        return {"CANO": self._creds.account_no, "ACNT_PRDT_CD": self._creds.product_code}

    def _kr_balance(self) -> dict[str, Any]:
        return self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance", "kr_balance",
            {
                **self._account(), "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )

    def _us_balance(self, order_exchange: str) -> dict[str, Any]:
        return self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance", "us_balance",
            {
                **self._account(), "OVRS_EXCG_CD": order_exchange, "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
            },
        )

    def _us_buying_power(self, symbol: str, order_exchange: str, price: float) -> float:
        body = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-psamount", "us_psamount",
            {
                **self._account(), "OVRS_EXCG_CD": order_exchange,
                "OVRS_ORD_UNPR": f"{price:.2f}", "ITEM_CD": symbol,
            },
        )
        return _f((body.get("output") or {}).get("ovrs_ord_psbl_amt"))

    def get_cash(self, category: str) -> float:
        """주문 가능 현금 (한국: 원, 미국: 달러).

        한국은 예수금과 D+2 예수금 중 작은 값(보수적), 미국은 해외 주문가능금액(외화).
        """
        if category == KR_CATEGORY:
            out2 = self._kr_balance().get("output2") or [{}]
            row = out2[0] if isinstance(out2, list) and out2 else {}
            return max(0.0, min(_f(row.get("dnca_tot_amt")), _f(row.get("prvs_rcdl_excc_amt"))))
        if category == US_CATEGORY:
            probe = self.us_cash_probe_symbol
            exch = self.resolve_us_exchange(probe)
            return self._us_buying_power(probe, exch, self.get_price(US_CATEGORY, probe))
        raise BrokerError(f"KIS 브로커는 한국/미국 주식만 지원합니다: {category}")

    def get_position(self, category: str, symbol: str) -> tuple[float, float]:
        """(주문 가능 보유 수량, 평균 매입가). 미보유면 (0.0, 0.0)."""
        code = normalize_stock_symbol(category, symbol)
        if category == KR_CATEGORY:
            rows = self._kr_balance().get("output1") or []
            key, qty_key = "pdno", "ord_psbl_qty"
        else:
            rows = self._us_balance(self.resolve_us_exchange(code)).get("output1") or []
            key, qty_key = "ovrs_pdno", "ord_psbl_qty"
        for row in rows:
            if str(row.get(key, "")).upper() == code:
                return _f(row.get(qty_key)), _f(row.get("pchs_avg_pric"))
        return 0.0, 0.0

    def get_holding_qty(self, category: str, symbol: str) -> float:
        """주문 가능 보유 수량."""
        return self.get_position(category, symbol)[0]

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    def _fail(self, request: OrderRequest, message: str, order_id: Optional[str] = None) -> OrderResult:
        logger.warning(f"[KisBroker] 주문 거부/미체결: {message}")
        return OrderResult(
            success=False, message=message, request=request,
            is_live=self.IS_LIVE and not self.dry_run, order_id=order_id,
        )

    def _validate(self, request: OrderRequest) -> tuple[Optional[str], str]:
        """공통 사전 검증. (정규화된 종목코드, 실패 사유) — 코드가 None이면 거부."""
        try:
            code = normalize_stock_symbol(request.category, request.symbol)
        except ValueError as exc:
            return None, str(exc)
        if self.allowed_symbols is not None and code not in self.allowed_symbols:
            return None, f"허용 목록에 없는 종목: {code} (허용: {sorted(self.allowed_symbols)})"
        if not math.isfinite(request.price) or request.price <= 0:
            return None, f"비정상 기준가({request.price}) — 주문하지 않습니다."
        if not math.isfinite(request.amount) or request.amount < 0:
            return None, f"비정상 주문 금액({request.amount})"
        return code, ""

    def _market_hours_note(self, category: str) -> Optional[str]:
        """장외면 사유 문자열, 장중이면 None."""
        if not self.enforce_market_hours or is_market_open(category, self._now_fn()):
            return None
        return "장 운영 시간(정규장)이 아닙니다"

    def place_order(self, request: OrderRequest) -> OrderResult:
        """주문을 실행한다 (dry_run이면 검증만).

        Args:
            request: 주문 요청. BUY는 amount(현지 통화)로 살 수 있는 최대 정수 주,
                SELL은 amount=0이면 전량, 아니면 amount/price 만큼(정수 주).

        Returns:
            OrderResult. success=True는 "체결 확인됨"(dry_run이면 "검증 통과").
            접수됐지만 체결이 확인되지 않으면 success=False + order_id.

        Raises:
            BrokerError: 통신/인증 오류. 주문 전송 중이었다면 접수 여부가 불명확하므로
                자동 재시도하지 말고 잔고·체결을 재확인해야 한다.
        """
        code, reason = self._validate(request)
        if code is None:
            return self._fail(request, reason)

        hours_note = self._market_hours_note(request.category)
        if hours_note and not self.dry_run:
            return self._fail(request, hours_note)

        is_kr = request.category == KR_CATEGORY
        exch = None if is_kr else self.resolve_us_exchange(code)
        price = (
            float(request.price) if is_kr
            else float(us_limit_price(request.side, request.price, self.us_slippage_pct))
        )

        # ── 수량 결정 + 잔고/상한 검증 ──
        if request.side == OrderSide.BUY:
            cap = self.max_order_krw if is_kr else self.max_order_usd
            unit = "원" if is_kr else "달러"
            if request.amount > cap:
                return self._fail(request, f"1회 주문 상한 초과: {request.amount:,.2f} > {cap:,.2f}{unit}")
            qty = int(request.amount // price)
            if qty < 1:
                return self._fail(request, f"주문 금액 {request.amount:,.2f}{unit}로는 1주({price:,.2f})도 살 수 없습니다.")
            cash = self.get_cash(request.category) if is_kr else self._us_buying_power(code, exch, price)
            if qty * price > cash:
                return self._fail(request, f"주문 가능 현금 부족: 필요 {qty * price:,.2f} > 가능 {cash:,.2f}{unit}")
        else:
            held, _ = self.get_position(request.category, code)
            qty = int(held)
            if request.amount > 0:
                qty = min(qty, int(request.amount // request.price))
            if qty < 1:
                return self._fail(request, f"매도 가능 수량이 없습니다: {code} (보유 {held:g}주)")

        path, tr_key, body = self._build_order(request.side, code, qty, price, exch)

        if self.dry_run:
            warn = f" ⚠️ {hours_note} — 실주문이면 거부됩니다." if hours_note else ""
            msg = f"[DRY-RUN {self.mode_label}] 전송 생략 — {code} {request.side.value} {qty}주 검증 통과: {body}{warn}"
            logger.info(f"[KisBroker] {msg}")
            return OrderResult(success=True, message=msg, request=request, is_live=False)

        logger.info(f"[KisBroker] {self.mode_label} 주문 전송: {code} {request.side.value} {qty}주 @ {body}")
        created = self._post_order(path, tr_key, body)
        if str(created.get("rt_cd")) != "0":
            return self._fail(request, f"KIS 주문 거절: {created.get('msg_cd', '')} {created.get('msg1', '')}".strip())
        order_id = str((created.get("output") or {}).get("ODNO") or "")
        if not order_id:
            raise BrokerError("KIS 주문 응답에 주문번호(ODNO)가 없습니다 — 접수 여부 불명, KIS 앱에서 확인하세요.")
        return self._confirm_fill(request, code, order_id, qty, exch)

    def _build_order(
        self, side: OrderSide, code: str, qty: int, price: float, exch: Optional[str]
    ) -> tuple[str, str, dict[str, str]]:
        """주문 API 경로/tr_id 키/본문을 만든다."""
        if exch is None:  # 한국 주식 — 시장가
            return (
                "/uapi/domestic-stock/v1/trading/order-cash",
                "kr_buy" if side == OrderSide.BUY else "kr_sell",
                {**self._account(), "PDNO": code, "ORD_DVSN": "01", "ORD_QTY": str(qty), "ORD_UNPR": "0"},
            )
        return (  # 미국 주식 — 시장성 지정가
            "/uapi/overseas-stock/v1/trading/order",
            "us_buy" if side == OrderSide.BUY else "us_sell",
            {
                **self._account(), "OVRS_EXCG_CD": exch, "PDNO": code, "ORD_QTY": str(qty),
                "OVRS_ORD_UNPR": format(Decimal(str(price)).normalize(), "f"),
                "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00",
            },
        )

    def _find_fill(self, code: str, order_id: str, exch: Optional[str]) -> tuple[float, float]:
        """주문번호의 (체결 수량, 평균 체결가)를 조회한다."""
        now = self._now_fn()
        if exch is None:
            today = now.astimezone(KST).strftime("%Y%m%d")
            body = self._get(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", "kr_ccld",
                {
                    **self._account(), "INQR_STRT_DT": today, "INQR_END_DT": today,
                    "SLL_BUY_DVSN_CD": "00", "INQR_DVSN": "00", "PDNO": code, "CCLD_DVSN": "00",
                    "ORD_GNO_BRNO": "", "ODNO": order_id, "INQR_DVSN_3": "00", "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                },
            )
            qty_key, price_key = "tot_ccld_qty", "avg_prvs"
        else:
            start = (now.astimezone(NEW_YORK) - timedelta(days=1)).strftime("%Y%m%d")
            end = now.astimezone(KST).strftime("%Y%m%d")
            body = self._get(
                "/uapi/overseas-stock/v1/trading/inquire-ccnl", "us_ccnl",
                {
                    **self._account(), "PDNO": code, "ORD_STRT_DT": start, "ORD_END_DT": end,
                    "SLL_BUY_DVSN": "00", "CCLD_NCCS_DVSN": "00", "OVRS_EXCG_CD": exch,
                    "SORT_SQN": "DS", "ORD_DT": "", "ORD_GNO_BRNO": "", "ODNO": "",
                    "CTX_AREA_NK200": "", "CTX_AREA_FK200": "",
                },
            )
            qty_key, price_key = "ft_ccld_qty", "ft_ccld_unpr3"
        rows = body.get("output1", body.get("output")) or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            if str(row.get("odno", "")).lstrip("0") == order_id.lstrip("0"):
                return _f(row.get(qty_key)), _f(row.get(price_key))
        return 0.0, 0.0

    def _confirm_fill(
        self, request: OrderRequest, code: str, order_id: str, qty: int, exch: Optional[str]
    ) -> OrderResult:
        """체결을 폴링해 OrderResult로 만든다 (조회 실패는 '접수됨, 미확인'으로 처리)."""
        filled, avg = 0.0, 0.0
        for attempt in range(self._fill_poll_attempts):
            try:
                filled, avg = self._find_fill(code, order_id, exch)
            except BrokerError as exc:
                logger.warning(f"[KisBroker] 체결 조회 실패(주문번호 {order_id}): {exc}")
            if filled >= qty:
                break
            if attempt < self._fill_poll_attempts - 1:
                self._sleep(1.0)

        is_live = self.IS_LIVE
        if filled > 0:
            partial = "" if filled >= qty else f" (부분 체결 {filled:g}/{qty}주 — 잔량은 미체결 상태)"
            msg = f"[{self.mode_label}] 체결 완료(주문번호 {order_id}): {code} {filled:g}주 @ {avg:,.4g}{partial}"
            logger.info(f"[KisBroker] {msg}")
            return OrderResult(
                success=True, message=msg, request=request, is_live=is_live,
                order_id=order_id, filled_qty=filled, avg_fill_price=avg,
            )
        return self._fail(
            request,
            f"[{self.mode_label}] 접수됨(주문번호 {order_id}) 그러나 체결 미확인 — KIS 앱에서 확인/취소하세요.",
            order_id=order_id,
        )
