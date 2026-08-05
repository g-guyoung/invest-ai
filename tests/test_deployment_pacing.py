# -*- coding: utf-8 -*-
"""
src/trading/deployment_pacing.py 에 대한 pytest 테스트.

캠페인 시작일(2026-08-04)을 기준으로 날짜를 명시적으로 넘겨 결과를
재현 가능하게 만든다 (실제 오늘 날짜에 의존하지 않음).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.trading.deployment_pacing import (
    CAMPAIGN_START_DATE,
    FORCE_BUY_DEPLOYED_PCT_THRESHOLD,
    MIN_CONFIDENCE_FLOOR,
    catch_up_amount,
    compute_deployment_status,
    pacing_adjusted_min_confidence,
)

START = CAMPAIGN_START_DATE  # 2026-08-04
DURATION = 30


# ── compute_deployment_status ──────────────────────────────────
def test_status_on_day_one_with_no_deployment_is_behind_schedule():
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=1_000_000.0,
        today=START, start_date=START, duration_days=DURATION,
    )

    assert status.days_elapsed == 1
    assert status.days_remaining == 29
    assert status.deployed_pct == 0.0
    assert status.behind_schedule is True
    assert status.force_mode is False  # 마감이 한참 남았으므로 아직 강제는 아님


def test_status_on_pace_is_not_behind_schedule():
    today = START + timedelta(days=9)  # 10일째, 목표 소진율 = 10/30 = 33.3%
    # 40% 소진 = 목표보다 앞서 있음
    status = compute_deployment_status(
        category="🇺🇸 미국 주식", initial_balance=1_000_000.0, current_cash=600_000.0,
        today=today, start_date=START, duration_days=DURATION,
    )

    assert status.deployed_pct == pytest.approx(0.4)
    assert status.target_pct == pytest.approx(10 / 30)
    assert status.behind_schedule is False


def test_status_behind_schedule_but_not_yet_force_mode():
    today = START + timedelta(days=9)  # 10일째, 잔여일수 20일 (>5)
    status = compute_deployment_status(
        category="₿ 암호화폐", initial_balance=1_000_000.0, current_cash=900_000.0,  # 10%만 소진
        today=today, start_date=START, duration_days=DURATION,
    )

    assert status.behind_schedule is True
    assert status.days_remaining == 20
    assert status.force_mode is False


def test_status_triggers_force_mode_near_deadline_when_far_behind():
    today = START + timedelta(days=25)  # 26일째, 잔여 4일(<=5)
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=1_000_000.0,  # 0% 소진
        today=today, start_date=START, duration_days=DURATION,
    )

    assert status.days_remaining == 4
    assert status.deployed_pct == 0.0
    assert status.deployed_pct < FORCE_BUY_DEPLOYED_PCT_THRESHOLD
    assert status.force_mode is True


def test_status_does_not_force_mode_if_already_sufficiently_deployed():
    today = START + timedelta(days=27)  # 잔여 2일 - 마감 임박
    status = compute_deployment_status(
        category="🇺🇸 미국 주식", initial_balance=1_000_000.0, current_cash=250_000.0,  # 75% 소진
        today=today, start_date=START, duration_days=DURATION,
    )

    assert status.deployed_pct >= FORCE_BUY_DEPLOYED_PCT_THRESHOLD
    assert status.force_mode is False  # 이미 충분히 소진했으므로 강제할 필요 없음


def test_status_rejects_non_positive_initial_balance():
    with pytest.raises(ValueError):
        compute_deployment_status(
            category="🇰🇷 한국 주식", initial_balance=0.0, current_cash=0.0, today=START,
        )


def test_status_defaults_to_todays_date_when_omitted():
    # today를 생략해도 예외 없이 date.today() 기준으로 계산돼야 한다.
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=1_000_000.0,
    )
    assert status.days_elapsed >= 1


# ── pacing_adjusted_min_confidence ─────────────────────────────
def test_min_confidence_unchanged_when_on_pace():
    today = START + timedelta(days=9)
    status = compute_deployment_status(
        category="🇺🇸 미국 주식", initial_balance=1_000_000.0, current_cash=600_000.0,
        today=today, start_date=START, duration_days=DURATION,
    )

    assert pacing_adjusted_min_confidence(0.6, status) == 0.6


def test_min_confidence_lowered_when_behind_schedule():
    today = START + timedelta(days=9)
    status = compute_deployment_status(
        category="₿ 암호화폐", initial_balance=1_000_000.0, current_cash=950_000.0,  # 5%만 소진
        today=today, start_date=START, duration_days=DURATION,
    )

    adjusted = pacing_adjusted_min_confidence(0.6, status)

    assert MIN_CONFIDENCE_FLOOR <= adjusted < 0.6


def test_min_confidence_hits_floor_in_force_mode():
    today = START + timedelta(days=25)
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=1_000_000.0,
        today=today, start_date=START, duration_days=DURATION,
    )
    assert status.force_mode is True

    assert pacing_adjusted_min_confidence(0.6, status) == MIN_CONFIDENCE_FLOOR


# ── catch_up_amount ─────────────────────────────────────────────
def test_catch_up_amount_spreads_remaining_cash_over_remaining_days():
    today = START + timedelta(days=25)  # 잔여 4일
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=500_000.0,
        today=today, start_date=START, duration_days=DURATION,
    )

    amount = catch_up_amount(status)

    assert amount == pytest.approx(500_000.0 / (4 + 1))
    assert amount <= status.current_cash


def test_catch_up_amount_returns_full_cash_on_final_day():
    today = START + timedelta(days=29)  # 마지막 날, 잔여 0일
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=300_000.0,
        today=today, start_date=START, duration_days=DURATION,
    )

    assert status.days_remaining == 0
    assert catch_up_amount(status) == 300_000.0


def test_catch_up_amount_is_zero_when_no_cash_left():
    today = START + timedelta(days=10)
    status = compute_deployment_status(
        category="🇰🇷 한국 주식", initial_balance=1_000_000.0, current_cash=0.0,
        today=today, start_date=START, duration_days=DURATION,
    )

    assert catch_up_amount(status) == 0.0
