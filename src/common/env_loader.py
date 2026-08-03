# -*- coding: utf-8 -*-
"""
환경변수 로더 (.env + Streamlit Cloud secrets 브릿지).

목적: 로컬 환경(.env 파일)과 Streamlit Cloud 환경(st.secrets)에서
    동일한 코드(os.getenv)로 API 키/설정값을 읽을 수 있도록 통일한다.

배경
----
- 로컬 개발: `.env` 파일을 python-dotenv로 로드해 os.environ에 채운다.
- Streamlit Cloud 배포: `.env` 파일이 저장소에 없으므로(보안상 .gitignore 처리),
  Streamlit Cloud의 "Secrets" 설정(st.secrets)에 값을 넣는다. 이 값은 기본적으로
  os.environ에 자동 반영되지 않으므로, 앱 시작 시 명시적으로 복사해줘야 한다.
- 이 함수를 앱 진입점(streamlit_app.py) 최상단에서 한 번 호출하면, 이후
  모든 모듈은 로컬/클라우드 구분 없이 os.getenv(...)만으로 값을 읽을 수 있다.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_LOADED = False


def load_environment() -> None:
    """
    .env 파일과 Streamlit secrets를 os.environ으로 통합 로드한다.

    - 로컬: python-dotenv로 `.env` 파일 로드.
    - Streamlit Cloud: st.secrets의 모든 키를 os.environ에 복사
      (이미 os.environ에 값이 있으면 덮어쓰지 않음).

    여러 번 호출해도 안전하다 (idempotent, 내부적으로 1회만 실제 작업 수행).

    Returns:
        None
    """
    global _LOADED
    if _LOADED:
        return

    # 1. 로컬 .env 파일 로드
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.info("✅ .env 파일 로드 완료 (로컬 개발 환경)")
    except ImportError:
        logger.warning("python-dotenv가 설치되지 않았습니다.")

    # 2. Streamlit Cloud secrets → os.environ 브릿지
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            bridged_count = 0
            for key in st.secrets.keys():
                if key not in os.environ:
                    os.environ[key] = str(st.secrets[key])
                    bridged_count += 1
            if bridged_count > 0:
                logger.info(f"✅ Streamlit secrets {bridged_count}개를 환경변수로 연결했습니다.")
    except Exception as exc:
        # secrets.toml이 없는 로컬 환경 등에서는 조용히 무시한다.
        logger.debug(f"Streamlit secrets 연결 생략: {exc}")

    _LOADED = True


def check_required_keys(*keys: str) -> dict:
    """
    필수 환경변수가 설정되어 있는지 확인한다.

    Args:
        *keys: 확인할 환경변수 이름들.

    Returns:
        {key: bool} 형태의 딕셔너리 (설정 여부).
    """
    return {key: bool(os.getenv(key)) for key in keys}
