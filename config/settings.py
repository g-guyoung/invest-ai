# -*- coding: utf-8 -*-
"""
전역 설정값 모듈.

목적: 프로젝트 전반에서 재사용하는 기본값(데이터 경로, 기본 심볼,
    기본 인터벌 등)을 한 곳에서 관리하여 하드코딩을 방지한다.
"""

import os
from pathlib import Path

# 프로젝트 루트 기준 경로
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"

# Binance 데이터 수집 기본값
DEFAULT_SYMBOL: str = "BTCUSDT"
DEFAULT_INTERVAL: str = "1d"
BINANCE_BASE_URL: str = "https://api.binance.com"

# 재시도 정책 기본값
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BACKOFF_SECONDS: float = 1.0

# data 디렉토리가 없으면 생성
DATA_DIR.mkdir(parents=True, exist_ok=True)
