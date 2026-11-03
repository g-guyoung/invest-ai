"""scripts/analyze_auto_trading.py 회귀 테스트.

2026-11-03 정비 때 발견한 버그(로그 없음/risk_score 컬럼 부재/빈 신뢰도/
lines.append() 인자 누락으로 인한 크래시)가 다시 생기지 않도록 고정한다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_auto_trading.py"


@pytest.fixture(scope="module")
def analyzer():
    """스크립트를 모듈로 로드한다 (scripts/는 패키지가 아니므로 경로로 직접 로드)."""
    spec = importlib.util.spec_from_file_location("analyze_auto_trading", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _logger_style_df(confidences: list) -> pd.DataFrame:
    """AutoTraderLogger가 실제로 쓰는 CSV 컬럼/값 형식 그대로 DataFrame을 만든다."""
    n = len(confidences)
    return pd.DataFrame(
        {
            "timestamp": ["2026-11-03T00:31:00"] * n,
            "date": ["2026-11-03"] * n,
            "time": ["00:31:00"] * n,
            "category": ["🇰🇷 한국 주식", "₿ 암호화폐"][:n] + ["₿ 암호화폐"] * max(0, n - 2),
            "symbol": ["005930"] * n,
            "name": ["삼성전자"] * n,
            "signal": ["BUY", "HOLD"][:n] + ["HOLD"] * max(0, n - 2),
            "confidence": confidences,
            "executed": ["Yes", "No"][:n] + ["No"] * max(0, n - 2),
            "forced": ["No"] * n,
            "message": [""] * n,
            "error": [""] * n,
        }
    )


def test_full_report_from_logger_format(analyzer) -> None:
    """정상: 로거 형식("72.00%") 그대로 리포트가 끝까지 생성된다."""
    df = _logger_style_df(["72.00%", "55.00%"])
    overall = analyzer.analyze_overall(df)
    report = analyzer.print_report(
        overall,
        analyzer.analyze_by_category(df),
        analyzer.analyze_by_signal(df),
        analyzer.analyze_by_date(df.copy()),
    )
    assert overall["total_executed"] == 1
    assert overall["avg_confidence"] == pytest.approx(0.635)
    assert overall["avg_risk"] is None  # 로거에 risk_score 컬럼이 없어도 크래시하지 않음
    assert "자동매매 성과 분석 리포트" in report
    assert "위험도" not in report


def test_empty_confidence_column_does_not_crash(analyzer) -> None:
    """엣지: 신뢰도가 전부 비어 float(NaN)로 읽혀도 계산이 실패하지 않는다."""
    df = _logger_style_df([float("nan"), float("nan")])
    overall = analyzer.analyze_overall(df)
    assert pd.isna(overall["avg_confidence"])


def test_risk_score_used_when_present(analyzer) -> None:
    """확장: risk_score 컬럼이 추가되면 평균 위험도를 계산한다."""
    df = _logger_style_df(["70.00%", "60.00%"])
    df["risk_score"] = [0.2, 0.4]
    assert analyzer.analyze_overall(df)["avg_risk"] == pytest.approx(0.3)


def test_missing_log_returns_none(analyzer, tmp_path, monkeypatch) -> None:
    """실패: 로그 파일이 없으면 예외 대신 None을 돌려준다."""
    monkeypatch.setattr(analyzer, "_PROJECT_ROOT", tmp_path)
    assert analyzer.load_log() is None
