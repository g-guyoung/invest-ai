#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
자동매매 성과 분석 스크립트.

목적: data/auto_trading_log.csv를 읽어서 통계/성과를 자동 분석하고
     콘솔에 출력 및 요약 파일(analysis_summary.txt)에 저장한다.

실행:
    python scripts/analyze_auto_trading.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 프로젝트 루트 추가
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_log() -> pd.DataFrame:
    """로그 파일을 읽어서 DataFrame으로 반환."""
    log_file = _PROJECT_ROOT / "data" / "auto_trading_log.csv"

    if not log_file.exists():
        print(f"❌ 로그 파일이 없습니다: {log_file}")
        print("   → 아직 자동매매가 한 번도 실행되지 않았습니다.")
        return None

    df = pd.read_csv(log_file)
    print(f"✅ 로그 파일 로드: {len(df)}개 기록")
    return df


def analyze_overall(df: pd.DataFrame) -> dict:
    """전체 통계."""
    return {
        "total_records": len(df),
        "total_executed": (df["executed"] == "Yes").sum(),
        "total_forced": (df["forced"] == "Yes").sum(),
        "avg_confidence": df["confidence"].str.rstrip("%").astype(float).mean() / 100,
        "avg_risk": df["risk_score"].astype(float).mean(),
        "execution_rate": (df["executed"] == "Yes").sum() / len(df),
        "forced_rate": (df["forced"] == "Yes").sum() / len(df),
    }


def analyze_by_category(df: pd.DataFrame) -> dict:
    """카테고리별 통계."""
    result = {}
    for category in df["category"].unique():
        cat_df = df[df["category"] == category]
        result[category] = {
            "count": len(cat_df),
            "executed": (cat_df["executed"] == "Yes").sum(),
            "execution_rate": (cat_df["executed"] == "Yes").sum() / len(cat_df),
            "avg_confidence": cat_df["confidence"].str.rstrip("%").astype(float).mean() / 100,
            "avg_risk": cat_df["risk_score"].astype(float).mean(),
        }
    return result


def analyze_by_signal(df: pd.DataFrame) -> dict:
    """신호별 통계."""
    result = {}
    for signal in ["BUY", "SELL", "HOLD"]:
        sig_df = df[df["signal"] == signal]
        if len(sig_df) == 0:
            continue
        result[signal] = {
            "count": len(sig_df),
            "executed": (sig_df["executed"] == "Yes").sum(),
            "execution_rate": (sig_df["executed"] == "Yes").sum() / len(sig_df),
            "avg_confidence": sig_df["confidence"].str.rstrip("%").astype(float).mean() / 100,
        }
    return result


def analyze_by_date(df: pd.DataFrame) -> dict:
    """날짜별 통계 (최근 7일)."""
    df["date"] = pd.to_datetime(df["date"])
    result = {}

    for date in sorted(df["date"].unique())[-7:]:  # 최근 7일
        date_df = df[df["date"] == date]
        date_str = date.strftime("%Y-%m-%d")
        result[date_str] = {
            "count": len(date_df),
            "executed": (date_df["executed"] == "Yes").sum(),
            "forced": (date_df["forced"] == "Yes").sum(),
            "avg_confidence": (
                date_df["confidence"].str.rstrip("%").astype(float).mean() / 100
            ),
        }

    return result


def print_report(overall: dict, by_category: dict, by_signal: dict, by_date: dict) -> str:
    """보고서 생성."""
    lines = []

    lines.append("=" * 70)
    lines.append("📊 자동매매 성과 분석 리포트")
    lines.append("=" * 70)
    lines.append(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. 전체 통계
    lines.append("1️⃣ 전체 통계")
    lines.append("-" * 70)
    lines.append(f"  총 분석 종목: {overall['total_records']}개")
    lines.append(f"  체결 건수: {overall['total_executed']}개 ({overall['execution_rate']*100:.1f}%)")
    lines.append(f"  강제매수: {overall['total_forced']}개 ({overall['forced_rate']*100:.1f}%)")
    lines.append(f"  평균 신뢰도: {overall['avg_confidence']:.1%}")
    lines.append(f"  평균 위험도: {overall['avg_risk']:.2f}\n")

    # 2. 카테고리별
    lines.append("2️⃣ 카테고리별 분석")
    lines.append("-" * 70)
    for cat, stats in by_category.items():
        lines.append(f"  {cat}")
        lines.append(f"    - 분석: {stats['count']}개, 체결: {stats['executed']}개 ({stats['execution_rate']*100:.1f}%)")
        lines.append(f"    - 신뢰도: {stats['avg_confidence']:.1%}, 위험도: {stats['avg_risk']:.2f}")
    lines.append()

    # 3. 신호별
    if by_signal:
        lines.append("3️⃣ 신호별 분석")
        lines.append("-" * 70)
        for sig, stats in by_signal.items():
            lines.append(f"  {sig}: {stats['count']}개, 체결 {stats['executed']}개 ({stats['execution_rate']*100:.1f}%)")
        lines.append()

    # 4. 최근 7일
    if by_date:
        lines.append("4️⃣ 최근 7일 추이")
        lines.append("-" * 70)
        for date, stats in by_date.items():
            lines.append(
                f"  {date}: {stats['count']}개 분석, "
                f"{stats['executed']}개 체결, "
                f"강제 {stats['forced']}개, "
                f"신뢰도 {stats['avg_confidence']:.1%}"
            )
        lines.append()

    lines.append("=" * 70)

    return "\n".join(lines)


def main() -> None:
    """메인 함수."""
    print("\n🔍 자동매매 성과 분석 중...\n")

    df = load_log()
    if df is None:
        return

    # 분석 수행
    overall = analyze_overall(df)
    by_category = analyze_by_category(df)
    by_signal = analyze_by_signal(df)
    by_date = analyze_by_date(df)

    # 리포트 생성 및 출력
    report = print_report(overall, by_category, by_signal, by_date)
    print(report)

    # 파일 저장
    summary_file = _PROJECT_ROOT / "data" / "analysis_summary.txt"
    summary_file.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ 요약 파일 저장: {summary_file}\n")


if __name__ == "__main__":
    main()
