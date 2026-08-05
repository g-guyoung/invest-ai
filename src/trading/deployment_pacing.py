# -*- coding: utf-8 -*-
"""
1개월 강제 소진 페이싱(pacing) 모듈 (Phase 5 Part 3 확장).

목적
----
사용자 요청: "1개월 내로 카테고리별 100만원을 반드시 다 써야 한다"는 가정 하에,
AI가 신뢰도 부족을 이유로 계속 관망(HOLD)만 하면 매매 학습(데이터 축적)에
도움이 되지 않는다. 이 모듈은 "지금까지 얼마나 썼어야 하는가(목표 소진 속도)"와
"실제로 얼마나 썼는가"를 비교해, 뒤처질수록 매매를 더 적극적으로 유도한다.

동작 방식 (2단계)
------------------
1. 연성 유도(soft nudge): 목표 소진 속도보다 뒤처질수록 min_confidence를
   점진적으로 낮춘다 (pacing_adjusted_min_confidence). AI 스스로 더 쉽게
   매수 기회를 잡도록 문턱을 낮추는 것 — 여전히 AI의 신호(BUY/SELL/HOLD)를 따른다.
2. 경성 강제(force_mode): 마감(FORCE_BUY_DAYS_REMAINING_THRESHOLD일 전)이
   임박했는데도 소진율이 FORCE_BUY_DEPLOYED_PCT_THRESHOLD 미만이면, HOLD
   신호라도 강제로 매수를 발동한다 (AutoTrader에서 처리). 이때도 SELL 신호는
   존중한다(이미 보유 중이라는 뜻이므로 강제 대상이 아니다).

이 모듈은 순수 계산 로직만 담당하고(Pure Function), 실제 매매 실행은
src.trading.auto_trader.AutoTrader가 담당한다 (관심사 분리).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# ============================================================================
# 캠페인 설정 — "1개월 내 100만원 소진" 실험의 기준값.
# 다음 라운드를 새로 시작하려면 이 값들만 바꾸면 된다.
# ============================================================================

# 캠페인(실 운영 자동매매) 시작일. 2026-08-04부터 매일 GitHub Actions로
# 자동매매가 실제로 돌아가기 시작했으므로 이 날짜를 기준으로 삼는다.
CAMPAIGN_START_DATE: date = date(2026, 8, 4)

# 캠페인 전체 기간(일). 원래 1~2개월로 지켜볼 계획이었으나, 사용자 요청으로
# 1개월(30일)로 단축하고 그 안에 반드시 소진하도록 강제한다.
CAMPAIGN_DURATION_DAYS: int = 30

# 마감까지 이 일수 이하로 남았는데도 소진이 부족하면 강제 매수를 발동한다.
FORCE_BUY_DAYS_REMAINING_THRESHOLD: int = 5

# 강제 매수 발동 기준 소진율. 이 값 이상 이미 소진했다면(=충분히 매매했다면)
# 마감이 임박해도 굳이 강제하지 않는다.
FORCE_BUY_DEPLOYED_PCT_THRESHOLD: float = 0.7

# 뒤처진 정도에 따라 min_confidence를 낮출 때, 아무리 뒤처져도 이 값 밑으로는
# 내려가지 않는다 (연성 유도 단계의 하한선 — 완전 무모한 매수까지는 막는 안전장치).
MIN_CONFIDENCE_FLOOR: float = 0.35

# 강제 매수(force_mode)에서도 이 위험도(risk_score)를 넘으면 매수를 보류한다
# (마감이 급해도 "매우 위험" 판정까지 무시하지는 않는다 — 최소한의 안전장치).
FORCE_BUY_MAX_RISK_SCORE: float = 0.9


@dataclass(frozen=True)
class DeploymentStatus:
    """카테고리(시장) 하나의 "1개월 내 100만원 소진" 진행 상태.

    Attributes:
        category: 시장 카테고리 (표시/로그용).
        initial_balance: 이 시장에 배정된 초기 가상자금.
        current_cash: 현재 남은 현금.
        deployed_amount: 지금까지 투입된 금액(initial_balance - current_cash, 0 이상).
        deployed_pct: 소진 비율(0~1). 매도로 현금이 늘면 다시 낮아질 수 있다
            (지금 이 순간 실제로 시장에 들어가 있는 비중을 뜻하기 때문 — 의도된 동작).
        target_pct: 오늘 날짜 기준 "제 속도로 가고 있다면" 도달했어야 할 소진 비율
            (선형 배분: 경과일수 / 전체기간).
        days_elapsed: 캠페인 시작일로부터 경과 일수(오늘 포함, 최소 1).
        days_remaining: 캠페인 종료일까지 남은 일수(최소 0).
        behind_schedule: deployed_pct가 target_pct보다 뒤처졌는지 여부.
        force_mode: 마감이 임박했는데도 소진이 크게 뒤처져, 신뢰도/위험도 기준을
            사실상 무시하고서라도 강제 매수를 발동해야 하는 상태인지 여부.
    """

    category: str
    initial_balance: float
    current_cash: float
    deployed_amount: float
    deployed_pct: float
    target_pct: float
    days_elapsed: int
    days_remaining: int
    behind_schedule: bool
    force_mode: bool


def compute_deployment_status(
    category: str,
    initial_balance: float,
    current_cash: float,
    today: Optional[date] = None,
    start_date: date = CAMPAIGN_START_DATE,
    duration_days: int = CAMPAIGN_DURATION_DAYS,
) -> DeploymentStatus:
    """오늘 기준으로 이 카테고리의 "1개월 내 소진" 진행 상태를 계산한다.

    Purpose:
        캠페인 시작일 대비 오늘이 며칠째인지, 목표 소진 속도(선형 배분) 대비
        실제로 얼마나 투입됐는지를 비교해 뒤처짐 여부와 강제 매수 필요 여부를 판단한다.

    Args:
        category: 시장 카테고리.
        initial_balance: 이 카테고리에 배정된 초기 가상자금 (0보다 커야 함).
        current_cash: 현재 남은 현금.
        today: 기준 날짜. 생략하면 오늘 날짜(date.today())를 쓴다. 테스트에서는
            고정된 날짜를 넘겨 결과를 재현 가능하게 만든다.
        start_date: 캠페인 시작일. 기본값은 CAMPAIGN_START_DATE.
        duration_days: 캠페인 전체 기간(일). 기본값은 CAMPAIGN_DURATION_DAYS.

    Returns:
        DeploymentStatus.

    Raises:
        ValueError: initial_balance가 0 이하인 경우.
    """
    if initial_balance <= 0:
        raise ValueError("initial_balance는 0보다 커야 합니다.")

    today = today or date.today()
    days_elapsed = max(1, (today - start_date).days + 1)
    days_remaining = max(0, duration_days - days_elapsed)

    deployed_amount = max(0.0, initial_balance - current_cash)
    deployed_pct = min(1.0, deployed_amount / initial_balance)
    target_pct = min(1.0, days_elapsed / duration_days)

    behind_schedule = deployed_pct < target_pct
    force_mode = (
        days_remaining <= FORCE_BUY_DAYS_REMAINING_THRESHOLD
        and deployed_pct < FORCE_BUY_DEPLOYED_PCT_THRESHOLD
    )

    return DeploymentStatus(
        category=category,
        initial_balance=initial_balance,
        current_cash=current_cash,
        deployed_amount=deployed_amount,
        deployed_pct=deployed_pct,
        target_pct=target_pct,
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        behind_schedule=behind_schedule,
        force_mode=force_mode,
    )


def pacing_adjusted_min_confidence(base_min_confidence: float, status: DeploymentStatus) -> float:
    """소진 진행 상태에 따라 min_confidence를 낮춘다 (뒤처질수록 더 관대하게).

    Purpose:
        "관망만 하면 학습에 도움이 안 된다"는 요구를 반영해, 목표 소진 속도보다
        뒤처질수록 매수 신호를 더 쉽게 통과시킨다. force_mode에서는 연성 유도가
        낼 수 있는 최저치(MIN_CONFIDENCE_FLOOR)까지 내려간다 — 그래도 남는
        간극은 AutoTrader의 강제 매수 로직(Tier 2)이 별도로 채운다.

    Args:
        base_min_confidence: 시장 프로필의 기본 min_confidence.
        status: compute_deployment_status()의 결과.

    Returns:
        조정된 min_confidence. base_min_confidence 이하, MIN_CONFIDENCE_FLOOR 이상.
    """
    if not status.behind_schedule:
        return base_min_confidence

    if status.force_mode:
        return MIN_CONFIDENCE_FLOOR

    gap = status.target_pct - status.deployed_pct  # 0~target_pct, 클수록 많이 뒤처짐
    relief = min(1.0, gap / max(status.target_pct, 1e-9))
    adjusted = base_min_confidence - (base_min_confidence - MIN_CONFIDENCE_FLOOR) * relief
    return max(MIN_CONFIDENCE_FLOOR, min(base_min_confidence, adjusted))


def catch_up_amount(status: DeploymentStatus) -> float:
    """오늘 강제로 투입해야 할 금액을 계산한다 (잔여 현금을 잔여일수+1로 균등 배분).

    Purpose:
        "남은 미소진 금액"을 "남은 일수"에 나눠 갚는 방식으로, 마감일까지
        부드럽게 목표(deployed_pct→1.0에 근접)에 도달하게 한다. 마감 당일
        (days_remaining=0)에는 남은 현금 전액을 반환해 확실히 소진을 끝낸다.

    Args:
        status: compute_deployment_status()의 결과.

    Returns:
        오늘 강제로 투입할 금액 (항상 status.current_cash 이하).
    """
    remaining_cash = status.current_cash
    if remaining_cash <= 0:
        return 0.0
    if status.days_remaining <= 0:
        return remaining_cash
    return remaining_cash / (status.days_remaining + 1)
