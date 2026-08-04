# -*- coding: utf-8 -*-
"""src/engine/market_profiles.py 에 대한 pytest 테스트."""

from __future__ import annotations

from src.engine.market_profiles import MARKET_PROFILES, get_profile
from src.portfolio.constants import CATEGORIES


def test_market_profiles_defined_for_every_category():
    assert set(MARKET_PROFILES.keys()) == set(CATEGORIES)


def test_each_profile_has_non_empty_prompt_context():
    for category, profile in MARKET_PROFILES.items():
        assert profile.prompt_context.strip() != "", category


def test_crypto_profile_is_more_conservative_than_stock_profiles():
    crypto = MARKET_PROFILES["₿ 암호화폐"]
    kr = MARKET_PROFILES["🇰🇷 한국 주식"]
    us = MARKET_PROFILES["🇺🇸 미국 주식"]

    assert crypto.max_position_pct < kr.max_position_pct
    assert crypto.max_position_pct < us.max_position_pct
    assert crypto.max_risk_score <= kr.max_risk_score
    assert crypto.max_risk_score <= us.max_risk_score


def test_get_profile_returns_neutral_default_for_unknown_category():
    profile = get_profile("존재하지 않는 시장")

    assert profile.prompt_context == ""
    assert profile.min_confidence == 0.6  # 기본값 유지
