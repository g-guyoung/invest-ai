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

→ 즉, 이 파일이 있는 한 "설정 실수로 실돈 매매가 시작되는" 사고는 불가능하다.
"""

from __future__ import annotations

import logging
import os

from src.execution.base_broker import BaseBroker, BrokerError
from src.execution.paper_broker import PaperBroker

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
