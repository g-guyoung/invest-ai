# -*- coding: utf-8 -*-
"""
포트폴리오 공통 상수.

목적: session_portfolio.py / base_repository.py / session_repository.py /
    supabase_repository.py가 모두 같은 값(카테고리, 초기자금)을 참조해야
    하는데, session_portfolio.py 안에 두면 저장소 모듈들이 그 모듈을
    역참조(circular import)하게 된다. 그래서 값만 이 파일로 분리했다.
"""

from __future__ import annotations

INITIAL_BALANCE = 1_000_000.0

CURRENCY_SYMBOL = {
    "🇰🇷 한국 주식": "₩",
    "🇺🇸 미국 주식": "$",
    "₿ 암호화폐": "$",
}

CATEGORIES = list(CURRENCY_SYMBOL.keys())
