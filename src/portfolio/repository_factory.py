# -*- coding: utf-8 -*-
"""
포트폴리오 저장소 팩토리 (Factory Pattern).

목적: SUPABASE_URL/SUPABASE_KEY 설정 여부와 실제 연결 성공 여부에 따라
    적절한 PortfolioRepository 구현체를 자동으로 선택한다.

동작
----
1. SUPABASE_URL/SUPABASE_KEY가 둘 다 설정되어 있고, 실제로 연결(health_check)에
   성공하면 SupabasePortfolioRepository를 사용한다 (영구 저장).
2. 그 외 모든 경우(키 없음, 패키지 미설치, 연결 실패 등)는
   SessionPortfolioRepository로 폴백한다 (앱이 죽지 않는다).

한 번 판단한 결과는 모듈 내부에 캐싱한다 (반복적인 네트워크 호출 방지).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.common.env_loader import check_required_keys
from src.portfolio.base_repository import PortfolioRepository
from src.portfolio.session_repository import SessionPortfolioRepository

logger = logging.getLogger(__name__)

_cached_repository: Optional[PortfolioRepository] = None


def get_repository(force_refresh: bool = False) -> PortfolioRepository:
    """현재 환경설정에 맞는 포트폴리오 저장소를 반환한다.

    Args:
        force_refresh: True면 캐시를 무시하고 다시 판단한다 (주로 테스트용).

    Returns:
        SupabasePortfolioRepository (Supabase 설정 + 연결 성공 시) 또는
        SessionPortfolioRepository (그 외 모든 경우, 안전한 폴백).
    """
    global _cached_repository
    if _cached_repository is not None and not force_refresh:
        return _cached_repository

    keys = check_required_keys("SUPABASE_URL", "SUPABASE_KEY")
    if keys["SUPABASE_URL"] and keys["SUPABASE_KEY"]:
        try:
            from src.portfolio.supabase_repository import SupabasePortfolioRepository

            repo = SupabasePortfolioRepository()
            if repo.health_check():
                logger.info("✅ Supabase 포트폴리오 저장소 사용 (영구 저장 활성화)")
                _cached_repository = repo
                return _cached_repository
            logger.warning("⚠️ Supabase 연결 확인 실패 → 세션 저장소로 폴백합니다.")
        except Exception as exc:  # noqa: BLE001 - 저장소 초기화 실패 시 세션으로 안전하게 폴백
            logger.warning(f"⚠️ Supabase 저장소 초기화 실패({exc}) → 세션 저장소로 폴백합니다.")
    else:
        logger.info("ℹ️ SUPABASE_URL/KEY 미설정 → 세션 저장소 사용 (새로고침 시 초기화됨)")

    _cached_repository = SessionPortfolioRepository()
    return _cached_repository


def reset_cache() -> None:
    """캐시된 저장소를 초기화한다 (테스트 간 격리용)."""
    global _cached_repository
    _cached_repository = None
