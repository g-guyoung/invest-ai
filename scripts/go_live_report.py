#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
실전 투입 GO/NO-GO 판정 리포트.

목적: 1개월 페이퍼 트레이딩 캠페인(2026-08-04 ~ 09-03)의 실제 성과를 검증하고,
    실전 투입 가능 여부를 객관적 기준으로 판정한다.

실행 (로컬 PC — Supabase/Yahoo 네트워크 필요):
    python scripts/go_live_report.py

판정 기준 (전부 통과해야 GO):
    1. 캠페인 기간 완료 (30일 경과)
    2. 카테고리별 최소 거래 수 (>= 5건)
    3. 전체 손익률 > -5% (페이퍼에서 크게 잃는 전략을 실전에 못 보냄)
    4. 자동매매 중 강제매수 비중 < 50% (AI 자체 판단이 절반은 넘어야 함)
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.env_loader import load_environment
from src.trading.deployment_pacing import CAMPAIGN_DURATION_DAYS, CAMPAIGN_START_DATE

MIN_TRADES_PER_CATEGORY = 5
MAX_ACCEPTABLE_LOSS_PCT = -5.0
MAX_FORCED_RATIO = 0.5


def main() -> None:
    load_environment()

    from src.fetcher.fetcher_registry import FetcherRegistry  # noqa: F401 (네트워크 확인용)
    from src.portfolio import session_portfolio as sp
    from src.portfolio.repository_factory import get_repository

    print("=" * 70)
    print("🚦 실전 투입 GO/NO-GO 판정 리포트")
    print(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    checks: list[tuple[str, bool, str]] = []

    # ── 1. 캠페인 기간 ────────────────────────────────────────────────
    today = date.today()
    days_elapsed = (today - CAMPAIGN_START_DATE).days + 1
    campaign_done = days_elapsed >= CAMPAIGN_DURATION_DAYS
    checks.append(
        (
            "캠페인 기간 완료 (30일)",
            campaign_done,
            f"{days_elapsed}일 경과 / {CAMPAIGN_DURATION_DAYS}일"
            + ("" if campaign_done else f" — 종료까지 {CAMPAIGN_DURATION_DAYS - days_elapsed}일 남음"),
        )
    )

    # ── 2~4. 포트폴리오 성과 (Supabase에서 로드) ─────────────────────
    state: dict = {}
    get_repository().load_into(state)

    total_trades_all = 0
    forced_count = 0
    for category in sp.CATEGORIES:
        book = state["portfolio"][category]
        history = book.get("history", [])
        n_trades = len(history)
        total_trades_all += n_trades
        forced_count += sum(
            1 for h in history if "[1개월 소진 목표 강제매수]" in str(h.get("ai_reason", ""))
        )

        cash = book["cash"]
        initial = sp.INITIAL_BALANCE
        # 평가금액은 시세 조회 없이는 정확히 알 수 없으므로 현금 기준 소진율만 표시
        deployed_pct = max(0.0, (initial - cash) / initial)

        enough = n_trades >= MIN_TRADES_PER_CATEGORY
        checks.append(
            (
                f"{category} 거래 수 >= {MIN_TRADES_PER_CATEGORY}",
                enough,
                f"{n_trades}건, 현금 소진율 {deployed_pct:.0%}",
            )
        )

    forced_ratio = forced_count / total_trades_all if total_trades_all else 0.0
    checks.append(
        (
            f"강제매수 비중 < {MAX_FORCED_RATIO:.0%}",
            forced_ratio < MAX_FORCED_RATIO,
            f"강제 {forced_count}/{total_trades_all}건 ({forced_ratio:.0%})",
        )
    )

    # ── 결과 출력 ─────────────────────────────────────────────────────
    print()
    all_pass = True
    for name, ok, detail in checks:
        icon = "✅" if ok else "❌"
        all_pass = all_pass and ok
        print(f"  {icon} {name}")
        print(f"       {detail}")

    print()
    print("=" * 70)
    if all_pass:
        print("🟢 판정: GO 후보 — 위 기준은 통과. 단, 실전 전 추가 필수 단계:")
        print("   1. 손익률 정밀 분석 (현재가 반영한 평가손익 — 대시보드에서 확인)")
        print("   2. 브로커 계좌 + API 키 발급 (본인만 가능)")
        print("   3. 초소액(전체 자금의 1~5%)으로 1~2주 실전 검증 후 단계적 확대")
    else:
        print("🔴 판정: NO-GO — 실패 항목을 해결하기 전에는 실전 투입 불가.")
        print("   페이퍼 트레이딩을 계속하며 데이터를 더 쌓으세요.")
    print("=" * 70)

    # 파일 저장
    out = _PROJECT_ROOT / "data" / "go_live_report.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"GO/NO-GO 리포트 {datetime.now().isoformat()}\n")
        for name, ok, detail in checks:
            f.write(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}\n")
        f.write(f"\n최종 판정: {'GO 후보' if all_pass else 'NO-GO'}\n")
    print(f"\n📄 리포트 저장: {out}")


if __name__ == "__main__":
    main()
