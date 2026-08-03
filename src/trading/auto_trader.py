# -*- coding: utf-8 -*-
"""
AI 자동 트레이딩 엔진 (Phase 5 Part 3).

목적: Claude 분석 결과(BUY/SELL/HOLD + Confidence + Risk Score)에 따라
    사람 개입 없이 가상 매수/매도를 자동으로 실행하고 기록한다.

동작 개요
---------
1. 감시 종목 목록(watchlist)을 순회하며 Yahoo Finance에서 OHLCV 데이터를 조회한다.
2. 기술적 지표를 추가하고 ClaudeAnalyzer(BaseAnalyzer)로 분석해
   {signal, confidence, reason, risk_score}를 얻는다.
3. 리스크 규칙(TradingConfig)을 통과하면 session_portfolio.buy()/sell()을
   호출해 가상 매매를 실행한다 — 기존 수동 매매(Streamlit UI)와 완전히
   동일한 검증/계산 로직을 재사용한다 (중복 코드 없음).
4. 포트폴리오 저장소가 Supabase로 연결되어 있으면 결과가 영구 저장되고,
   아니라면(로컬 테스트, Supabase 미설정 등) 세션(plain dict) 저장소로
   자동 폴백한다 — 이 모듈은 어느 쪽인지 신경 쓸 필요가 없다.

실행 방법
---------
    python -m src.trading.auto_trader

GitHub Actions로 매일 자동 실행한다 (.github/workflows/auto_trade.yml 참고).

리스크 관리 (이번 버전 범위)
---------------------------
- 최소 신뢰도(min_confidence) 미만이면 매매하지 않고 관망한다.
- 위험도(risk_score)가 max_risk_score를 넘으면 BUY를 보류한다.
- 1회 매수 금액은 카테고리 보유 현금의 max_position_pct를 넘지 않으며,
  신뢰도가 높을수록 비중을 키운다(선형 스케일).
- Stop Loss / ATR Stop / Daily Loss Limit / Max Drawdown 등은 다음 단계에서
  거래 이력이 쌓인 뒤 확장한다 (CLAUDE.md 리스크 관리 원칙 참고).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.env_loader import load_environment
from src.engine.base_analyzer import AnalysisResult, AnalyzerError, BaseAnalyzer, Signal
from src.engine.indicators import add_indicators
from src.fetcher.base_fetcher import FetcherError
from src.fetcher.fetcher_registry import FetcherRegistry
from src.portfolio import session_portfolio as sp

logger = logging.getLogger(__name__)


@dataclass
class WatchlistItem:
    """자동매매 감시 대상 1개 종목.

    Attributes:
        category: sp.CATEGORIES 중 하나 (시장 카테고리).
        yahoo_symbol: Yahoo Finance 조회용 심볼 (예: "005930.KS", "AAPL", "BTC-USD").
        display_symbol: 포트폴리오/거래 내역에 표시할 심볼 (예: "005930", "AAPL", "BTC").
        name: 표시 이름.
    """

    category: str
    yahoo_symbol: str
    display_symbol: str
    name: str


# 기본 감시 종목 (Phase 5 Part 3 최초 버전).
# 향후 설정 파일/Supabase 테이블로 이전해 사용자가 직접 편집할 수 있게 확장 가능.
DEFAULT_WATCHLIST: list[WatchlistItem] = [
    WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자"),
    WatchlistItem("🇰🇷 한국 주식", "000660.KS", "000660", "SK하이닉스"),
    WatchlistItem("🇺🇸 미국 주식", "AAPL", "AAPL", "Apple"),
    WatchlistItem("🇺🇸 미국 주식", "TSLA", "TSLA", "Tesla"),
    WatchlistItem("₿ 암호화폐", "BTC-USD", "BTC", "Bitcoin"),
    WatchlistItem("₿ 암호화폐", "ETH-USD", "ETH", "Ethereum"),
]


@dataclass
class TradingConfig:
    """자동매매 리스크/포지션 규칙.

    Attributes:
        min_confidence: 이 값 미만이면 신호를 무시하고 관망한다.
        max_risk_score: 이 값을 초과하면(위험도 높음) BUY 신호를 보류한다.
        max_position_pct: 1회 매수 시 카테고리 현금 대비 최대 매수 비중(0~1).
        min_trade_amount: 이 금액 미만이면 매수를 실행하지 않는다(너무 작은 거래 방지).
    """

    min_confidence: float = 0.6
    max_risk_score: float = 0.7
    max_position_pct: float = 0.3
    min_trade_amount: float = 10_000.0


@dataclass
class TradeDecision:
    """종목 1개에 대한 자동매매 실행 결과 (로그/테스트 검증용)."""

    item: WatchlistItem
    signal: Optional[Signal] = None
    confidence: Optional[float] = None
    executed: bool = False
    message: str = ""
    error: Optional[str] = None


class AutoTrader:
    """AI 분석 신호에 따라 가상 매수/매도를 자동 실행하는 엔진."""

    def __init__(
        self,
        analyzer: BaseAnalyzer,
        config: Optional[TradingConfig] = None,
        watchlist: Optional[list[WatchlistItem]] = None,
    ) -> None:
        """AutoTrader를 초기화한다.

        Args:
            analyzer: BaseAnalyzer 구현체 (예: ClaudeAnalyzer). 테스트 시 mock 주입 가능.
            config: 리스크/포지션 규칙. 생략 시 기본값(TradingConfig()) 사용.
            watchlist: 감시 종목 목록. 생략 시 DEFAULT_WATCHLIST 사용.
        """
        self.analyzer = analyzer
        self.config = config or TradingConfig()
        self.watchlist = watchlist if watchlist is not None else DEFAULT_WATCHLIST

    def _decide_position_size(self, cash: float, confidence: float) -> float:
        """신뢰도에 비례해 매수 금액을 계산한다 (Position Sizing).

        min_confidence~1.0 구간을 max_position_pct의 절반~전체 비중으로
        선형 스케일한다. 신뢰도가 낮을수록 작게, 높을수록 크게 베팅한다.

        Args:
            cash: 해당 카테고리의 현재 보유 현금.
            confidence: AI 분석 신뢰도(0.0~1.0, 이미 min_confidence 이상으로 필터링됨).

        Returns:
            매수에 사용할 금액.
        """
        denom = 1 - self.config.min_confidence
        scale = (
            min(max((confidence - self.config.min_confidence) / denom, 0.0), 1.0)
            if denom > 0 else 1.0
        )
        pct = self.config.max_position_pct * (0.5 + 0.5 * scale)
        return cash * pct

    def run_once(self, state: dict, item: WatchlistItem) -> TradeDecision:
        """종목 1개에 대해 분석 → 매매 판단 → 실행까지 한 번 수행한다.

        Args:
            state: session_portfolio가 사용하는 포트폴리오 dict (Streamlit
                session_state 또는 plain dict — 둘 다 동작한다).
            item: 감시 대상 종목.

        Returns:
            TradeDecision. 실패해도 예외를 던지지 않는다 — watchlist 전체
            순회가 한 종목의 오류로 멈추면 안 되기 때문이다.
        """
        decision = TradeDecision(item=item)
        try:
            df = FetcherRegistry.get_ohlcv(
                symbol=item.yahoo_symbol, market="yahoo", interval="1d", limit=100,
            )
            if df is None or df.empty:
                decision.error = "가격 데이터를 가져오지 못했습니다."
                return decision

            df = add_indicators(df)
            result: AnalysisResult = self.analyzer.analyze(df.tail(50), symbol=item.yahoo_symbol)
            decision.signal = result.signal
            decision.confidence = result.confidence

            price = float(df["close"].iloc[-1])
            sp.init_portfolio(state)
            book = state["portfolio"][item.category]

            if result.confidence < self.config.min_confidence:
                decision.message = (
                    f"신뢰도 부족({result.confidence:.2f} < {self.config.min_confidence}) - 관망"
                )
                return decision

            if result.signal == Signal.BUY:
                if result.risk_score > self.config.max_risk_score:
                    decision.message = f"위험도 과다({result.risk_score:.2f}) - 매수 보류"
                    return decision

                amount = self._decide_position_size(book["cash"], result.confidence)
                if amount < self.config.min_trade_amount:
                    decision.message = f"매수 가능 금액 부족({amount:,.0f})"
                    return decision

                ok, msg = sp.buy(
                    state, item.category, item.display_symbol, item.name, price, amount,
                    source="AUTO_AI", ai_signal=result.signal.value,
                    ai_confidence=result.confidence, ai_reason=result.reason,
                )
                decision.executed = ok
                decision.message = msg

            elif result.signal == Signal.SELL:
                holding = book["holdings"].get(item.display_symbol)
                if not holding or holding["qty"] <= 0:
                    decision.message = "보유 중이 아니므로 매도 생략"
                    return decision

                ok, msg = sp.sell(
                    state, item.category, item.display_symbol, price,
                    source="AUTO_AI", ai_signal=result.signal.value,
                    ai_confidence=result.confidence, ai_reason=result.reason,
                )
                decision.executed = ok
                decision.message = msg

            else:
                decision.message = "HOLD 신호 - 매매 없음"

        except (AnalyzerError, FetcherError) as exc:
            decision.error = str(exc)
            logger.error(f"{item.display_symbol} 자동매매 실패: {exc}")
        except Exception as exc:  # noqa: BLE001 - 한 종목 실패가 전체를 막지 않도록 광범위 처리
            decision.error = str(exc)
            logger.exception(f"{item.display_symbol} 자동매매 중 예상치 못한 오류")

        return decision

    def run_all(self) -> list[TradeDecision]:
        """감시 종목 전체에 대해 자동매매를 1회 실행한다.

        Returns:
            종목별 TradeDecision 리스트.
        """
        state: dict = {}
        decisions = []
        for item in self.watchlist:
            decision = self.run_once(state, item)
            decisions.append(decision)
            logger.info(
                f"[{item.category}] {item.display_symbol}: "
                f"{decision.signal} (conf={decision.confidence}) -> "
                f"{decision.message or decision.error}"
            )
        return decisions


def main() -> None:
    """CLI 진입점: 감시 종목 전체에 대해 자동매매를 1회 실행한다."""
    logging.basicConfig(level=logging.INFO)
    load_environment()

    from src.engine.claude_analyzer import ClaudeAnalyzer

    trader = AutoTrader(analyzer=ClaudeAnalyzer())
    decisions = trader.run_all()

    executed = sum(1 for d in decisions if d.executed)
    logger.info(f"자동매매 완료: {len(decisions)}개 종목 분석, {executed}건 체결")


if __name__ == "__main__":
    main()
