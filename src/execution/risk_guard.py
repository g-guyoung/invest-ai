# -*- coding: utf-8 -*-
"""
리스크 가드 (Risk Guard) — 실전 투입 전 필수 안전장치.

목적: AI가 아무리 확신해도, 아래 하드 리밋을 넘는 주문은 기계적으로 차단한다.
    실전 매매에서 "코드 버그 하나 = 실제 돈 손실"이므로, AI 판단과 무관하게
    동작하는 독립적인 최종 방어선이 필요하다.

3중 방어선
----------
1. Kill Switch: data/KILL_SWITCH 파일이 존재하면 모든 신규 매수 차단.
   (사용자가 파일 하나만 만들면 즉시 자동매매를 멈출 수 있다 — 코드 수정/배포 불필요)
2. 일일 손실 한도(max_daily_loss_pct): 오늘 하루 손실이 한도를 넘으면 그날 매수 중단.
3. 최대 낙폭(max_drawdown_pct): 초기 자금 대비 총자산이 한도 이상 하락하면
   해당 카테고리 매수 전면 중단 (수동 리셋 전까지).

+ 기본 검증: 주문 금액 상한/하한, 1회 주문의 현금 대비 비중 상한.

이 모듈은 순수 계산 로직(Pure Function 지향)으로, 브로커/AI에 의존하지 않아
단독으로 완전히 테스트 가능하다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Kill Switch 파일 경로 — 이 파일이 존재하면 모든 신규 매수를 차단한다.
KILL_SWITCH_FILE = Path(__file__).resolve().parents[2] / "data" / "KILL_SWITCH"


@dataclass(frozen=True)
class RiskLimits:
    """리스크 하드 리밋 설정.

    Attributes:
        max_daily_loss_pct: 일일 손실 한도 (초기자금 대비, 0.03 = 3%).
        max_drawdown_pct: 최대 낙폭 한도 (초기자금 대비, 0.15 = 15%).
        max_order_pct_of_cash: 1회 주문이 보유 현금에서 차지할 수 있는 최대 비중.
        min_order_amount: 최소 주문 금액 (수수료 대비 실효성 없는 초소액 주문 방지).
        max_orders_per_day: 카테고리당 하루 최대 주문 횟수 (폭주 방지).
    """

    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.15
    max_order_pct_of_cash: float = 0.5
    min_order_amount: float = 5_000.0
    max_orders_per_day: int = 10


@dataclass(frozen=True)
class RiskVerdict:
    """리스크 검사 결과.

    Attributes:
        allowed: 주문 허용 여부.
        reason: 차단 사유 (허용이면 "OK").
    """

    allowed: bool
    reason: str = "OK"


class RiskGuard:
    """주문 전 최종 리스크 검사기.

    Args:
        limits: 리스크 한도 설정 (생략 시 보수적 기본값).
        kill_switch_file: Kill Switch 파일 경로 (테스트 주입용).
    """

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        kill_switch_file: Optional[Path] = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self.kill_switch_file = kill_switch_file or KILL_SWITCH_FILE

    # ------------------------------------------------------------------
    # 개별 검사 (전부 순수 함수 스타일 — 테스트 용이)
    # ------------------------------------------------------------------

    def is_kill_switch_on(self) -> bool:
        """Kill Switch 파일 존재 여부."""
        return self.kill_switch_file.exists()

    def check_daily_loss(
        self, initial_balance: float, day_start_total: float, current_total: float
    ) -> RiskVerdict:
        """오늘 하루 손실이 한도를 넘었는지 검사.

        Args:
            initial_balance: 카테고리 초기 자금.
            day_start_total: 오늘 시작 시점 총자산.
            current_total: 현재 총자산.
        """
        daily_loss = day_start_total - current_total
        limit = initial_balance * self.limits.max_daily_loss_pct
        if daily_loss > limit:
            return RiskVerdict(
                False,
                f"일일 손실 한도 초과: 오늘 -{daily_loss:,.0f} > 한도 {limit:,.0f}"
                f" ({self.limits.max_daily_loss_pct:.0%}) — 오늘 매수 중단",
            )
        return RiskVerdict(True)

    def check_drawdown(self, initial_balance: float, current_total: float) -> RiskVerdict:
        """초기자금 대비 최대 낙폭 한도 검사."""
        if initial_balance <= 0:
            return RiskVerdict(False, "초기 자금이 0 이하 — 설정 오류")
        drawdown = (initial_balance - current_total) / initial_balance
        if drawdown > self.limits.max_drawdown_pct:
            return RiskVerdict(
                False,
                f"최대 낙폭 한도 초과: -{drawdown:.1%} > 한도 "
                f"{self.limits.max_drawdown_pct:.0%} — 이 카테고리 매수 전면 중단",
            )
        return RiskVerdict(True)

    def check_order_size(self, amount: float, available_cash: float) -> RiskVerdict:
        """주문 금액이 상식적 범위인지 검사."""
        if amount < self.limits.min_order_amount:
            return RiskVerdict(
                False,
                f"최소 주문 금액 미달: {amount:,.0f} < {self.limits.min_order_amount:,.0f}",
            )
        if amount > available_cash:
            return RiskVerdict(
                False, f"현금 부족: 주문 {amount:,.0f} > 보유 {available_cash:,.0f}"
            )
        max_allowed = available_cash * self.limits.max_order_pct_of_cash
        if amount > max_allowed:
            return RiskVerdict(
                False,
                f"1회 주문 비중 초과: {amount:,.0f} > 현금의 "
                f"{self.limits.max_order_pct_of_cash:.0%} ({max_allowed:,.0f})",
            )
        return RiskVerdict(True)

    def check_order_count(self, orders_today: int) -> RiskVerdict:
        """하루 주문 횟수 한도 검사 (폭주 방지)."""
        if orders_today >= self.limits.max_orders_per_day:
            return RiskVerdict(
                False,
                f"일일 주문 횟수 한도 도달: {orders_today}/{self.limits.max_orders_per_day}",
            )
        return RiskVerdict(True)

    # ------------------------------------------------------------------
    # 통합 검사
    # ------------------------------------------------------------------

    def check_buy(
        self,
        amount: float,
        available_cash: float,
        initial_balance: float,
        current_total: float,
        day_start_total: Optional[float] = None,
        orders_today: int = 0,
        allow_full_cash: bool = False,
    ) -> RiskVerdict:
        """매수 주문에 대한 전체 리스크 검사 (하나라도 걸리면 차단).

        Args:
            amount: 주문 금액.
            available_cash: 주문 가능 현금.
            initial_balance: 카테고리 초기 자금.
            current_total: 현재 총자산 (현금 + 평가금액).
            day_start_total: 오늘 시작 시점 총자산 (없으면 일일 손실 검사 생략).
            orders_today: 오늘 이미 실행한 주문 수.
            allow_full_cash: True면 1회 주문 비중 상한(max_order_pct_of_cash)을
                건너뛴다 — 1개월 소진 캠페인의 "마감일 전액 투입" 같은
                명시적 정책 매수용. Kill Switch/낙폭/현금부족 검사는 그대로 적용.

        Returns:
            RiskVerdict — allowed=False면 reason에 차단 사유.
        """
        if self.is_kill_switch_on():
            return RiskVerdict(
                False,
                f"🛑 KILL SWITCH 활성화됨 ({self.kill_switch_file}) — 모든 매수 차단. "
                "재개하려면 이 파일을 삭제하세요.",
            )

        checks = [
            self.check_order_count(orders_today),
            self.check_drawdown(initial_balance, current_total),
        ]
        if allow_full_cash:
            # 비중 상한만 면제하고, 현금 초과 주문은 여전히 차단한다.
            if amount > available_cash:
                checks.append(
                    RiskVerdict(False, f"현금 부족: 주문 {amount:,.0f} > 보유 {available_cash:,.0f}")
                )
        else:
            checks.append(self.check_order_size(amount, available_cash))

        for verdict in checks:
            if not verdict.allowed:
                logger.warning(f"RiskGuard 차단: {verdict.reason}")
                return verdict

        if day_start_total is not None:
            verdict = self.check_daily_loss(initial_balance, day_start_total, current_total)
            if not verdict.allowed:
                logger.warning(f"RiskGuard 차단: {verdict.reason}")
                return verdict

        return RiskVerdict(True)
