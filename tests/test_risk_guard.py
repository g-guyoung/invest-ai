# -*- coding: utf-8 -*-
"""RiskGuard 테스트 (정상/차단/엣지 케이스)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.execution.risk_guard import RiskGuard, RiskLimits


@pytest.fixture
def guard(tmp_path):
    """Kill Switch가 꺼진 기본 가드."""
    return RiskGuard(kill_switch_file=tmp_path / "KILL_SWITCH")


class TestKillSwitch:
    def test_off_by_default(self, guard):
        assert not guard.is_kill_switch_on()

    def test_blocks_all_buys_when_on(self, tmp_path):
        ks = tmp_path / "KILL_SWITCH"
        ks.write_text("stop")
        guard = RiskGuard(kill_switch_file=ks)
        verdict = guard.check_buy(
            amount=10_000, available_cash=100_000,
            initial_balance=1_000_000, current_total=1_000_000,
        )
        assert not verdict.allowed
        assert "KILL SWITCH" in verdict.reason


class TestOrderSize:
    def test_normal_order_allowed(self, guard):
        verdict = guard.check_buy(
            amount=50_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
        )
        assert verdict.allowed

    def test_too_small_order_blocked(self, guard):
        verdict = guard.check_buy(
            amount=1_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
        )
        assert not verdict.allowed
        assert "최소 주문" in verdict.reason

    def test_exceeds_cash_blocked(self, guard):
        verdict = guard.check_buy(
            amount=600_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
        )
        assert not verdict.allowed

    def test_exceeds_pct_of_cash_blocked(self, guard):
        # 기본 상한: 현금의 50%
        verdict = guard.check_buy(
            amount=400_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
        )
        assert not verdict.allowed
        assert "비중" in verdict.reason

    def test_full_cash_allowed_when_forced(self, guard):
        # 강제매수(전액 소진)는 비중 상한 면제 — 단, 현금 초과는 여전히 차단
        verdict = guard.check_buy(
            amount=500_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
            allow_full_cash=True,
        )
        assert verdict.allowed

        verdict2 = guard.check_buy(
            amount=600_000, available_cash=500_000,
            initial_balance=1_000_000, current_total=1_000_000,
            allow_full_cash=True,
        )
        assert not verdict2.allowed


class TestDrawdown:
    def test_within_limit_allowed(self, guard):
        # -10% (한도 15%)
        verdict = guard.check_drawdown(1_000_000, 900_000)
        assert verdict.allowed

    def test_exceeds_limit_blocked(self, guard):
        # -20% (한도 15%)
        verdict = guard.check_drawdown(1_000_000, 800_000)
        assert not verdict.allowed
        assert "낙폭" in verdict.reason

    def test_zero_initial_balance_blocked(self, guard):
        verdict = guard.check_drawdown(0, 100)
        assert not verdict.allowed


class TestDailyLoss:
    def test_within_limit_allowed(self, guard):
        # 오늘 -2% (한도 3%)
        verdict = guard.check_daily_loss(1_000_000, 1_000_000, 980_000)
        assert verdict.allowed

    def test_exceeds_limit_blocked(self, guard):
        # 오늘 -5% (한도 3%)
        verdict = guard.check_daily_loss(1_000_000, 1_000_000, 950_000)
        assert not verdict.allowed


class TestOrderCount:
    def test_under_limit_allowed(self, guard):
        assert guard.check_order_count(5).allowed

    def test_at_limit_blocked(self, guard):
        assert not guard.check_order_count(10).allowed


class TestCustomLimits:
    def test_custom_limits_applied(self, tmp_path):
        strict = RiskGuard(
            limits=RiskLimits(max_drawdown_pct=0.05),
            kill_switch_file=tmp_path / "KILL_SWITCH",
        )
        # -10% 낙폭: 기본(15%)이면 통과지만 커스텀(5%)에선 차단
        assert not strict.check_drawdown(1_000_000, 900_000).allowed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
