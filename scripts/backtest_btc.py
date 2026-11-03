#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
업비트 KRW-BTC 실데이터로 전략 3종 + Buy&Hold를 비교하는 백테스트 리포트.

실행:
    python scripts/backtest_btc.py                 # 일봉 + 4시간봉
    python scripts/backtest_btc.py --capital 50000

출력:
    - 콘솔/GitHub Actions Summary: 전략별 성과 표 (전체 구간 + walk-forward 검증 구간)
    - data/backtest_btc_results.json: 기계 판독용 결과

판정 기준 (실전 후보 선정):
    walk-forward 검증 구간에서 Buy&Hold 대비 샤프가 높고, 최대 낙폭이 더 얕은 전략.
    전체 구간 성적은 참고용 — 파라미터를 과거 전체에 맞춘 값이라 낙관적으로 나온다.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.backtest.engine import PERIODS_PER_YEAR, run_backtest, walk_forward  # noqa: E402
from src.exchange.upbit_client import UpbitQuotationClient  # noqa: E402
from src.strategy.rule_strategies import STRATEGY_REGISTRY  # noqa: E402

#: interval별 (가져올 봉 수, 학습 봉 수, 검증 봉 수)
CONFIGS: dict[str, tuple[int, int, int]] = {
    "1d": (3000, 365, 90),          # 상장 이후 전체(~2017-09), 1년 학습 → 3개월 검증
    "4h": (3000, 6 * 120, 6 * 30),  # 최근 ~500일, 120일 학습 → 30일 검증
}


def _pct(x: float) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.1%}"


def _row(name: str, r) -> str:
    wr = "—" if math.isnan(r.win_rate) else f"{r.win_rate:.0%}"
    return (f"| {name} | {_pct(r.total_return)} | {_pct(r.cagr)} | {r.sharpe:.2f} | "
            f"{r.max_drawdown:.1%} | {r.n_trades} | {wr} | {r.exposure:.0%} | {r.final_equity:,.0f}원 |")


HEADER = ("| 전략 | 총수익 | 연환산 | 샤프 | 최대낙폭 | 거래 | 승률 | 보유비중 | 5만원→ |\n"
          "|---|---|---|---|---|---|---|---|---|")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=50_000)
    parser.add_argument("--market", default="KRW-BTC")
    args = parser.parse_args()

    client = UpbitQuotationClient()
    lines: list[str] = [f"# 📈 {args.market} 전략 백테스트 (초기자본 {args.capital:,.0f}원, 편도 비용 0.1%)"]
    results: dict = {}

    for interval, (count, train, test) in CONFIGS.items():
        df = client.get_ohlcv(args.market, interval, count=count)
        ppy = PERIODS_PER_YEAR[interval]
        span = f"{df['open_time'].iloc[0]:%Y-%m-%d} ~ {df['open_time'].iloc[-1]:%Y-%m-%d}"
        oos_start = df["open_time"].iloc[train]
        lines += ["", f"## {interval} 봉 — {len(df)}개 ({span})", "",
                  "### ① Walk-forward 검증 구간 (안 본 데이터 성적 — **판정 기준**)",
                  f"검증 구간: {oos_start:%Y-%m-%d} 이후, 학습 {train}봉 → 검증 {test}봉씩 이동", "", HEADER]
        results[interval] = {"span": span, "walk_forward": {}, "full_default": {}}

        for name, cls in STRATEGY_REGISTRY.items():
            wf = walk_forward(df, cls, train_bars=train, test_bars=test,
                              initial_capital=args.capital, periods_per_year=ppy)
            lines.append(_row(name, wf.oos))
            last_params = wf.folds[-1]["params"] if wf.folds else {}
            results[interval]["walk_forward"][name] = {**wf.oos.summary(), "latest_params": last_params}

        lines += ["", "### ② 전체 구간, 기본 파라미터 (참고용)", "", HEADER]
        for name, cls in STRATEGY_REGISTRY.items():
            r = run_backtest(df, cls().generate_positions(df), initial_capital=args.capital, periods_per_year=ppy)
            lines.append(_row(name, r))
            results[interval]["full_default"][name] = r.summary()

        latest = {n: v["latest_params"] for n, v in results[interval]["walk_forward"].items() if v["latest_params"]}
        lines += ["", f"최근 폴드에서 선택된 파라미터: `{json.dumps(latest, ensure_ascii=False)}`"]

    report = "\n".join(lines)
    print(report)

    out = _ROOT / "data" / "backtest_btc_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
