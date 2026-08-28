# -*- coding: utf-8 -*-
"""
브로커 팩토리 — 가상/실전 모드 전환의 유일한 관문.

안전 설계 (실수로 실돈이 나가는 것을 막는 3중 잠금):
1. 기본값은 무조건 PaperBroker (아무 설정 없으면 절대 실전 안 됨).
2. 실전 전환은 .env에 두 값이 "모두" 정확히 있어야 한다:
       LIVE_TRADING=true
       LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS
   (오타/부분 설정이면 경고 로그 후 PaperBroker로 폴백)
3. 실전 브로커 구현체가 아직 없으므로, 두 값이 있어도 현재는
   NotImplementedError로 명시적으로 멈춘다 — 브로커 연동(업비트/KIS)이
   완성되고 사용자가 API 키를 발급한 뒤에만 열린다.

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


def get_broker(session_state: dict) -> BaseBroker:
    """설정에 따라 브로커를 반환한다 (기본: PaperBroker).

    Args:
        session_state: 가상 매매용 상태 dict (실전 모드에서는 무시됨).

    Returns:
        BaseBroker 구현체.

    Raises:
        BrokerError: 실전 모드가 요청됐지만 실전 브로커가 아직 연동되지 않은 경우.
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

    # 실전 모드 요청됨 — 그러나 실전 브로커는 아직 미연동.
    raise BrokerError(
        "실전 모드(LIVE_TRADING=true)가 요청됐지만 실전 브로커(업비트/KIS)가 "
        "아직 연동되지 않았습니다. 다음이 필요합니다:\n"
        "  1. 브로커 계좌 개설 + API 키 발급 (사용자 본인만 가능)\n"
        "  2. src/execution/에 해당 브로커 구현체 추가\n"
        "  3. 소액 테스트 후 단계적 확대\n"
        "그 전까지는 .env에서 LIVE_TRADING을 제거하고 가상 매매로 운영하세요."
    )
