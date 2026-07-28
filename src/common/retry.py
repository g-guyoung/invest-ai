# -*- coding: utf-8 -*-
"""
지수 백오프 재시도 공통 유틸리티.

목적: Binance 수집기, Claude 분석기 등 외부 API를 호출하는 모든 모듈이
    동일한 재시도 로직을 중복 작성하지 않도록 공통화한다(DRY).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_retries: int,
    backoff_seconds: float,
    retry_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    logger: Optional[logging.Logger] = None,
    action_name: str = "작업",
) -> T:
    """지수 백오프 방식으로 `func`를 최대 `max_retries`회 재시도한다.

    Args:
        func: 인자를 받지 않는 콜러블. 실패 시 retry_exceptions에 속하는
            예외를 발생시켜야 한다.
        max_retries: 최대 시도 횟수 (1 이상).
        backoff_seconds: 재시도 사이 초기 대기 시간(초). 시도마다 2배씩 증가한다.
        retry_exceptions: 재시도 대상으로 삼을 예외 타입들.
        logger: 재시도 경고 로그를 남길 로거. None이면 로깅하지 않는다.
        action_name: 로그 메시지에 표시할 작업 이름.

    Returns:
        func() 호출이 성공했을 때의 반환값.

    Raises:
        마지막 시도에서 발생한 예외를 그대로 다시 발생시킨다. 호출자가
        이를 잡아서 도메인에 맞는 예외로 감싸는 것을 권장한다.
    """
    if max_retries < 1:
        raise ValueError("max_retries는 1 이상이어야 합니다.")

    last_error: Optional[BaseException] = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except retry_exceptions as exc:
            last_error = exc
            if logger is not None:
                logger.warning(
                    "%s 실패 (시도 %d/%d): %s", action_name, attempt, max_retries, exc
                )
            if attempt < max_retries:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    assert last_error is not None  # max_retries >= 1 이므로 항상 한 번은 실행됨
    raise last_error
