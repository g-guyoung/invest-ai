# -*- coding: utf-8 -*-
"""
벡터화 백테스트 엔진 (롱 온리 현물) + Walk-Forward 검증.

목적:
    "어떤 전략이 수익률이 높은가"를 감이 아니라 숫자로 고른다.
    단, 과거 전체에 파라미터를 맞추면 무조건 좋아 보이므로(과적합), 최종 판단은
    **walk-forward(안 본 구간 성적)** 기준으로 한다.

체결 모델 (보수적 가정):
    - 봉 t 종가에 신호 확정 → 봉 t 종가 근처 시장가 체결 → 봉 t+1 수익부터 반영
      (= positions.shift(1) × 수익률). 같은 봉 안에서 미래를 보고 사는 일은 없다.
    - 포지션이 바뀔 때마다 (수수료 + 슬리피지) × 변경량 만큼 비용 차감.
      업비트 원화마켓 수수료 0.05% + 슬리피지 가정 0.05% = 편도 0.1%.

데이터 흐름:
    OHLCV ──▶ Strategy.generate_positions ──▶ run_backtest ──▶ BacktestResult(지표·자산곡선)
                                    └─ walk_forward: 학습구간 최적 파라미터 → 검증구간 적용 → 이어붙여 1회 평가
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.strategy.base_strategy import BaseStrategy

DEFAULT_FEE = 0.0005       # 업비트 KRW 마켓 수수료 (편도)
DEFAULT_SLIPPAGE = 0.0005  # 시장가 체결 미끄러짐 가정 (편도)

#: interval → 연간 봉 수 (암호화폐는 365일 24시간)
PERIODS_PER_YEAR: dict[str, int] = {"1d": 365, "4h": 365 * 6, "1h": 365 * 24}


@dataclass
class BacktestResult:
    """백테스트 결과.

    Attributes:
        total_return: 기간 총수익률 (0.25 = +25%).
        cagr: 연환산 수익률.
        sharpe: 연환산 샤프 비율 (무위험수익률 0 가정).
        sortino: 연환산 소르티노 비율.
        max_drawdown: 최대 낙폭 (음수, -0.3 = -30%).
        n_trades: 진입 횟수 (완료 + 미청산).
        win_rate: 청산 완료된 거래 중 수익 거래 비율 (거래 없으면 NaN).
        exposure: 보유 기간 비율.
        final_equity: 최종 자산.
        equity: 자산 곡선.
        returns: 봉별 전략 수익률 (비용 차감 후).
    """

    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    n_trades: int
    win_rate: float
    exposure: float
    final_equity: float
    equity: pd.Series = field(repr=False)
    returns: pd.Series = field(repr=False)

    def summary(self) -> dict[str, float]:
        """리포트용 핵심 지표 dict (자산곡선 제외)."""
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "n_trades": self.n_trades,
            "win_rate": self.win_rate,
            "exposure": self.exposure,
            "final_equity": self.final_equity,
        }


def run_backtest(
    df: pd.DataFrame,
    positions: pd.Series,
    *,
    initial_capital: float = 50_000,
    fee: float = DEFAULT_FEE,
    slippage: float = DEFAULT_SLIPPAGE,
    periods_per_year: int = 365,
) -> BacktestResult:
    """목표 포지션 시계열을 받아 비용 반영 성과를 계산한다.

    Args:
        df: OHLCV (close 필수). positions와 같은 인덱스.
        positions: 봉 t 종가 기준 목표 포지션 (0~1).
        initial_capital: 초기 자본 (기본 5만원).
        fee: 편도 수수료율.
        slippage: 편도 슬리피지율.
        periods_per_year: 연환산용 봉 수.

    Returns:
        BacktestResult.

    Raises:
        ValueError: 데이터가 2봉 미만이거나 인덱스가 맞지 않을 때.

    Examples:
        >>> idx = pd.RangeIndex(3)
        >>> df = pd.DataFrame({"close": [100.0, 110.0, 121.0]}, index=idx)
        >>> r = run_backtest(df, pd.Series([1.0, 1.0, 1.0], index=idx), fee=0, slippage=0)
        >>> round(r.total_return, 4)
        0.21
    """
    if len(df) < 2:
        raise ValueError("백테스트에는 최소 2개 봉이 필요합니다.")
    if not positions.index.equals(df.index):
        raise ValueError("positions와 df의 인덱스가 다릅니다.")

    market_ret = df["close"].pct_change().fillna(0.0)
    held = positions.shift(1).fillna(0.0)               # 봉 t에 실제로 들고 있던 포지션
    turnover = held.diff().abs().fillna(held.iloc[0])   # 포지션 변경량 (첫 봉 진입 포함)
    strat_ret = held * market_ret - turnover * (fee + slippage)

    equity = initial_capital * (1.0 + strat_ret).cumprod()
    return _build_result(strat_ret, held, equity, periods_per_year)


def _build_result(
    strat_ret: pd.Series, held: pd.Series, equity: pd.Series, periods_per_year: int
) -> BacktestResult:
    """수익률·포지션·자산곡선에서 지표를 계산한다 (DRY: run_backtest/walk_forward 공용)."""
    n = len(strat_ret)
    total_return = float((1.0 + strat_ret).prod() - 1.0)
    years = n / periods_per_year
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 and total_return > -1 else float("nan")

    std = strat_ret.std(ddof=0)
    sharpe = float(strat_ret.mean() / std * math.sqrt(periods_per_year)) if std > 0 else 0.0
    downside = strat_ret[strat_ret < 0].std(ddof=0)
    sortino = float(strat_ret.mean() / downside * math.sqrt(periods_per_year)) if downside and downside > 0 else 0.0

    running_max = equity.cummax()
    max_dd = float((equity / running_max - 1.0).min())

    trade_returns = _trade_returns(strat_ret, held)
    closed = trade_returns[:-1] if (len(held) and held.iloc[-1] > 0 and trade_returns) else trade_returns
    win_rate = float(np.mean([r > 0 for r in closed])) if closed else float("nan")

    return BacktestResult(
        total_return=total_return,
        cagr=float(cagr),
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        n_trades=len(trade_returns),
        win_rate=win_rate,
        exposure=float((held > 0).mean()),
        final_equity=float(equity.iloc[-1]),
        equity=equity,
        returns=strat_ret,
    )


def _trade_returns(strat_ret: pd.Series, held: pd.Series) -> list[float]:
    """보유 구간(0→양수 … →0)별 누적 수익률 목록. 진입·청산 비용 포함."""
    in_pos = (held > 0).to_numpy()
    rets = strat_ret.to_numpy()
    out: list[float] = []
    growth: Optional[float] = None
    for i, flag in enumerate(in_pos):
        if flag:
            growth = (growth if growth is not None else 1.0) * (1.0 + rets[i])
        elif growth is not None:
            growth *= 1.0 + rets[i]  # 청산 봉의 비용 반영
            out.append(growth - 1.0)
            growth = None
    if growth is not None:
        out.append(growth - 1.0)  # 미청산 거래
    return out


# ── Walk-Forward ───────────────────────────────────────────────
@dataclass
class WalkForwardResult:
    """Walk-forward 결과: 검증(OOS) 구간만 이어 붙인 성과와 폴드별 선택 파라미터."""

    oos: BacktestResult
    folds: list[dict]


def walk_forward(
    df: pd.DataFrame,
    strategy_cls: type[BaseStrategy],
    *,
    train_bars: int,
    test_bars: int,
    initial_capital: float = 50_000,
    fee: float = DEFAULT_FEE,
    slippage: float = DEFAULT_SLIPPAGE,
    periods_per_year: int = 365,
    min_trades: int = 2,
) -> WalkForwardResult:
    """학습 구간에서 샤프가 가장 높은 파라미터를 고르고, 바로 다음 검증 구간에 적용한다.

    검증 구간들의 목표 포지션을 이어 붙인 뒤 **한 번에** run_backtest 하므로,
    폴드 경계에서 파라미터가 바뀌며 생기는 매매 비용도 정확히 반영된다.

    Args:
        df: 전체 OHLCV.
        strategy_cls: 평가할 전략 클래스 (param_grid 사용).
        train_bars: 학습 구간 길이 (봉 수).
        test_bars: 검증 구간 길이 (봉 수) — 이만큼씩 앞으로 이동한다.
        min_trades: 학습 구간에서 이 횟수 미만으로 거래한 파라미터는 탈락 (우연 방지).
            BuyAndHold처럼 거래가 1번뿐인 기준선은 예외로 허용한다.

    Returns:
        WalkForwardResult.

    Raises:
        ValueError: 데이터가 학습+검증 1폴드보다 짧을 때.
    """
    if len(df) < train_bars + test_bars:
        raise ValueError(f"데이터 부족: {len(df)}봉 < 학습 {train_bars} + 검증 {test_bars}")

    grid = strategy_cls.param_grid or [strategy_cls.default_params]
    # 전략 포지션은 과거 데이터만 쓰므로, 전체 구간에서 한 번 계산해두고 잘라 써도 look-ahead가 없다.
    all_positions = {i: strategy_cls(**p).generate_positions(df) for i, p in enumerate(grid)}
    is_baseline = len(grid) == 1 and not grid[0]

    oos_positions: list[pd.Series] = []
    folds: list[dict] = []
    start = train_bars
    while start < len(df) - 1:
        end = min(start + test_bars, len(df))
        train_slice = slice(start - train_bars, start)

        best_i, best_sharpe = 0, -math.inf
        for i, pos in all_positions.items():
            res = run_backtest(
                df.iloc[train_slice], pos.iloc[train_slice],
                initial_capital=initial_capital, fee=fee, slippage=slippage,
                periods_per_year=periods_per_year,
            )
            if res.n_trades < min_trades and not is_baseline:
                continue
            if res.sharpe > best_sharpe:
                best_i, best_sharpe = i, res.sharpe

        oos_positions.append(all_positions[best_i].iloc[start:end])
        folds.append({
            "test_start": str(df["open_time"].iloc[start]) if "open_time" in df else start,
            "params": grid[best_i],
            "train_sharpe": round(best_sharpe, 3) if best_sharpe != -math.inf else None,
        })
        start = end

    # 검증 구간 첫 봉은 직전 포지션이 없으므로 현금에서 출발한다 (보수적, look-ahead 없음).
    oos_pos = pd.concat(oos_positions)
    result = run_backtest(
        df.loc[oos_pos.index], oos_pos, initial_capital=initial_capital, fee=fee,
        slippage=slippage, periods_per_year=periods_per_year,
    )
    return WalkForwardResult(oos=result, folds=folds)
