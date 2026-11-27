# -*- coding: utf-8 -*-
"""
브로커 팩토리 — 가상/실전 모드 전환의 유일한 관문.

안전 설계 (실수로 실돈이 나가는 것을 막는 3중 잠금):
1. 기본값은 무조건 PaperBroker (아무 설정 없으면 절대 실전 안 됨).
2. 실전 전환은 .env에 두 값이 "모두" 정확히 있어야 한다:
       LIVE_TRADING=true
       LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS
   (오타/부분 설정이면 경고 로그 후 PaperBroker로 폴백)
3. 두 값이 모두 있어도 UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY가 없으면
   BrokerError로 명시적으로 멈춘다 (조용히 가상으로 폴백하지 않는다).
   키가 있으면 UpbitBroker(업비트 KRW 현물)를 반환한다.

주식(한국투자증권 KIS)은 get_kis_broker()가 담당한다 — 기본은 모의투자 서버,
실전 서버(KIS_ENV=prod)는 위 이중 잠금이 있어야만 열린다.

→ 즉, 이 파일이 있는 한 "설정 실수로 실돈 매매가 시작되는" 사고는 불가능하다.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from src.execution.base_broker import BaseBroker, BrokerError
from src.execution.paper_broker import PaperBroker

if TYPE_CHECKING:
    from src.execution.kis_broker import KisBroker

logger = logging.getLogger(__name__)

_LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THE_RISKS"


def is_live_mode_requested() -> bool:
    """환경변수가 실전 모드를 정확히 요청했는지 확인한다."""
    return (
        os.getenv("LIVE_TRADING", "").strip().lower() == "true"
        and os.getenv("LIVE_TRADING_CONFIRM", "").strip() == _LIVE_CONFIRM_PHRASE
    )


def get_broker(session_state: dict, dry_run: bool = False) -> BaseBroker:
    """설정에 따라 브로커를 반환한다 (기본: PaperBroker).

    Args:
        session_state: 가상 매매용 상태 dict (실전 모드에서는 무시됨).
        dry_run: 실전 모드에서만 의미 있음. True면 UpbitBroker가 주문을 서버로
            전송하지 않고 검증만 한다 (조회는 실제 API 사용).

    Returns:
        BaseBroker 구현체.

    Raises:
        BrokerError: 실전 모드가 요청됐지만 업비트 API 키가 없는 경우.
            (조용히 가상으로 폴백하지 않고 명시적으로 실패 — 사용자가 실전이라고
            믿고 있는데 가상으로 돌아가는 것도 사고이기 때문)
    """
    if not is_live_mode_requested():
        if os.getenv("LIVE_TRADING", "").strip():
            # LIVE_TRADING은 있는데 확인 문구가 틀린 경우 — 명확히 알려준다.
            logger.warning(
                "LIVE_TRADING이 설정됐지만 LIVE_TRADING_CONFIRM="
                f"{_LIVE_CONFIRM_PHRASE} 가 없어 가상 매매(PaperBroker)로 실행합니다."
            )
        return PaperBroker(session_state)

    access_key = os.getenv("UPBIT_ACCESS_KEY", "").strip()
    secret_key = os.getenv("UPBIT_SECRET_KEY", "").strip()
    missing = [
        name
        for name, value in (("UPBIT_ACCESS_KEY", access_key), ("UPBIT_SECRET_KEY", secret_key))
        if not value
    ]
    if missing:
        raise BrokerError(
            "실전 모드(LIVE_TRADING=true)가 요청됐지만 .env에 "
            + ", ".join(missing)
            + " 가 없습니다. 업비트에서 API 키(자산조회+주문하기 권한, 허용 IP 등록)를 "
            "발급받아 .env에 넣거나, LIVE_TRADING을 제거하고 가상 매매로 운영하세요."
        )

    from src.execution.upbit_broker import UpbitBroker  # 지연 import: 가상 모드에서는 불필요

    logger.warning("🔴 실전 모드: UpbitBroker 사용 (dry_run=%s)", dry_run)
    return UpbitBroker(access_key=access_key, secret_key=secret_key, dry_run=dry_run)


# ----------------------------------------------------------------------
# 주식 (한국투자증권 KIS)
# ----------------------------------------------------------------------


def _parse_us_exchanges(raw: str) -> dict[str, str]:
    """"AAPL:NASD,KO:NYSE" → {"AAPL": "NASD", "KO": "NYSE"} (형식이 틀린 항목은 무시)."""
    result: dict[str, str] = {}
    for item in (raw or "").split(","):
        if ":" in item:
            sym, exch = item.split(":", 1)
            if sym.strip() and exch.strip():
                result[sym.strip().upper()] = exch.strip().upper()
    return result


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "").replace("_", ""))
    except ValueError as exc:
        raise BrokerError(f".env의 {name} 값이 숫자가 아닙니다: {raw!r}") from exc


def get_kis_broker(dry_run: bool = True, allowed_symbols: "list[str] | None" = None) -> "KisBroker":
    """한국투자증권(KIS) 주식 브로커를 만든다 (한국/미국 주식 공용).

    잠금 규칙:
        - KIS_ENV 기본값은 "vts"(모의투자, 가짜 돈). KIS 앱키만 있으면 사용 가능.
        - KIS_ENV=prod(실전, 실제 돈)는 LIVE_TRADING=true +
          LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS 가 모두 있어야 한다.
          없으면 모의투자로 조용히 바꾸지 않고 BrokerError로 멈춘다.
        - dry_run=True(기본)면 어떤 서버든 주문은 전송되지 않는다.

    읽는 .env 값:
        KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO("12345678-01"), KIS_ENV(vts|prod),
        KIS_MAX_ORDER_KRW(기본 500000), KIS_MAX_ORDER_USD(기본 500),
        KIS_US_SLIPPAGE_PCT(기본 0.005), KIS_US_EXCHANGES("AAPL:NASD,KO:NYSE", 선택)

    Args:
        dry_run: True면 주문 미전송 (검증만).
        allowed_symbols: 주문 허용 종목 화이트리스트 (None이면 형식 검증만).

    Returns:
        KisBroker.

    Raises:
        BrokerError: 키 누락, 계좌번호 형식 오류, KIS_ENV 값 오류, 실전 잠금 미해제.
    """
    from src.execution.kis_broker import KisBroker, KisCredentials, KisEnv  # 지연 import

    env_raw = os.getenv("KIS_ENV", "vts").strip().lower() or "vts"
    try:
        env = KisEnv(env_raw)
    except ValueError as exc:
        raise BrokerError(f"KIS_ENV는 'vts'(모의투자) 또는 'prod'(실전)여야 합니다: {env_raw!r}") from exc

    if env == KisEnv.REAL and not is_live_mode_requested():
        raise BrokerError(
            "KIS_ENV=prod(실전 계좌)가 설정됐지만 실전 잠금이 풀려 있지 않습니다. "
            f".env에 LIVE_TRADING=true 와 LIVE_TRADING_CONFIRM={_LIVE_CONFIRM_PHRASE} 를 추가하거나, "
            "KIS_ENV=vts(모의투자)로 바꾸세요."
        )

    missing = [n for n in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO") if not os.getenv(n, "").strip()]
    if missing:
        raise BrokerError(
            ".env에 " + ", ".join(missing) + " 가 없습니다. 한국투자증권 KIS Developers에서 "
            f"{'실전' if env == KisEnv.REAL else '모의투자'}용 앱키를 발급받아 입력하세요."
        )

    creds = KisCredentials.from_values(
        os.getenv("KIS_APP_KEY", "").strip(),
        os.getenv("KIS_APP_SECRET", "").strip(),
        os.getenv("KIS_ACCOUNT_NO", "").strip(),
    )
    broker = KisBroker(
        credentials=creds,
        env=env,
        dry_run=dry_run,
        max_order_krw=_env_float("KIS_MAX_ORDER_KRW", 500_000.0),
        max_order_usd=_env_float("KIS_MAX_ORDER_USD", 500.0),
        us_slippage_pct=_env_float("KIS_US_SLIPPAGE_PCT", 0.005),
        allowed_symbols=allowed_symbols,
        us_exchanges=_parse_us_exchanges(os.getenv("KIS_US_EXCHANGES", "")),
    )
    level = logging.WARNING if env == KisEnv.REAL else logging.INFO
    logger.log(level, "주식 브로커: %s", broker.mode_label)
    return broker
