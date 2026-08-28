# -*- coding: utf-8 -*-
"""
AI 자동 트레이딩 엔진 (Phase 5 Part 3).

목적: Claude 분석 결과(BUY/SELL/HOLD + Confidence + Risk Score)에 따라
    사람 개입 없이 가상 매수/매도를 자동으로 실행하고 기록한다.

동작 개요
---------
1. 매 실행마다 시장별 후보 풀(CANDIDATE_POOLS)에서 몇 개씩 무작위로 뽑아
   감시 종목을 구성한다 (build_daily_watchlist) — 매번 삼성전자/애플/테슬라
   같은 유명 종목만 반복 거래하지 않고, 덜 알려진 중소형 종목까지 골고루
   사고파는 연습을 하도록 하기 위함이다.
2. 종목마다 Yahoo Finance에서 OHLCV 데이터를 조회하고 기술적 지표를 추가한다.
3. ClaudeAnalyzer(BaseAnalyzer)로 분석해 {signal, confidence, reason, risk_score}를
   얻는다 — 이때 시장별 맥락(market_profiles.MarketProfile.prompt_context)을
   함께 전달해, 한국장/미국장/암호화폐의 서로 다른 특성(거래시간, 변동성,
   영향 요인)을 반영한 판단을 받는다.
4. 리스크 규칙을 통과하면 session_portfolio.buy()/sell()을 호출해 가상
   매매를 실행한다 — 기존 수동 매매(Streamlit UI)와 완전히 동일한
   검증/계산 로직을 재사용한다 (중복 코드 없음). 리스크 규칙(TradingConfig)은
   명시적으로 주지 않으면 시장별 기본값(market_profiles)을 자동 적용한다
   (암호화폐는 변동성이 크므로 1회 매수 비중을 더 보수적으로 잡는 식).
5. 포트폴리오 저장소가 Supabase로 연결되어 있으면 결과가 영구 저장되고,
   아니라면(로컬 테스트, Supabase 미설정 등) 세션(plain dict) 저장소로
   자동 폴백한다 — 이 모듈은 어느 쪽인지 신경 쓸 필요가 없다.
6. (신규) src.trading.deployment_pacing으로 "1개월 내 카테고리별 100만원
   소진" 진행 상태를 계산해, 목표 소진 속도보다 뒤처지면 min_confidence를
   자동으로 낮추고(연성 유도), 마감이 임박했는데도 크게 뒤처졌으면 HOLD
   신호라도 강제로 매수를 발동한다(경성 강제) — 관망만 하다 끝나는 것을 막고
   실제 매매 데이터를 확보하기 위함이다. 자세한 규칙은 deployment_pacing.py 참고.

실행 방법
---------
    python -m src.trading.auto_trader

GitHub Actions로 매일 자동 실행한다 (.github/workflows/auto_trade.yml 참고).

리스크 관리 (이번 버전 범위)
---------------------------
- 최소 신뢰도(min_confidence) 미만이면 매매하지 않고 관망한다 — 단, 아래
  "1개월 소진 페이싱" 규칙에 따라 이 기준 자체가 동적으로 낮아질 수 있다.
- 위험도(risk_score)가 max_risk_score를 넘으면 BUY를 보류한다 — 강제 매수
  모드에서는 이 기준 대신 더 느슨한 FORCE_BUY_MAX_RISK_SCORE(0.9)를 쓴다.
- 1회 매수 금액은 카테고리 보유 현금의 max_position_pct를 넘지 않으며,
  신뢰도가 높을수록 비중을 키운다(선형 스케일). 시장별 기본값은
  market_profiles.MARKET_PROFILES 참고 (암호화폐는 더 보수적).
- Stop Loss / ATR Stop / Daily Loss Limit / Max Drawdown 등은 다음 단계에서
  거래 이력이 쌓인 뒤 확장한다 (CLAUDE.md 리스크 관리 원칙 참고).

1개월 소진 페이싱 (신규, deployment_pacing.py)
----------------------------------------------
- 목표: 캠페인 시작일(2026-08-04)로부터 30일 안에 카테고리별 100만원을
  전부(또는 최대한) 투입해, 관망 위주가 아니라 실제 매매 데이터를 쌓는다.
- 연성 유도: 오늘까지 도달했어야 할 소진율(target_pct)보다 실제 소진율이
  낮으면 min_confidence를 점진적으로 낮춘다 (최저 0.35).
- 경성 강제: 마감 5일 전인데도 소진율이 70% 미만이면, HOLD 신호라도
  강제로 매수한다 (SELL 신호는 이미 보유 중이라는 뜻이므로 존중해 예외).
  이때도 risk_score가 0.9를 넘으면 강제 매수를 보류한다(최소 안전장치).

종목 풀 관련 알려진 한계
------------------------
- CANDIDATE_POOLS는 실제 스크리너 API 없이 수동으로 큐레이션한 목록이다
  (완전히 무작위인 초소형주까지는 다루지 않는다). 스크리너를 연동하면
  더 넓은 유니버스에서 자동으로 후보를 뽑을 수 있다 (다음 단계 후보).
"""

from __future__ import annotations

import logging
import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.env_loader import load_environment
from src.engine.base_analyzer import AnalysisResult, AnalyzerError, BaseAnalyzer, Signal
from src.engine.indicators import add_indicators
from src.engine.market_profiles import MarketProfile, get_profile
from src.fetcher.base_fetcher import FetcherError
from src.fetcher.fetcher_registry import FetcherRegistry
from src.portfolio import session_portfolio as sp
from src.trading.deployment_pacing import (
    CAMPAIGN_DURATION_DAYS,
    CAMPAIGN_START_DATE,
    FORCE_BUY_MAX_RISK_SCORE,
    DeploymentStatus,
    catch_up_amount,
    compute_deployment_status,
    pacing_adjusted_min_confidence,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
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


# ============================================================================
# 시장별 후보 풀 — 대형주(익숙한 종목) + 중소형주(덜 알려진 종목)를 섞어서,
# 매일 다른 조합을 거래하며 다양한 종목을 사고파는 연습을 하도록 한다.
# ============================================================================

_KR_POOL: list[WatchlistItem] = [
    # 대형주 (기준점 역할)
    WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자"),
    WatchlistItem("🇰🇷 한국 주식", "000660.KS", "000660", "SK하이닉스"),
    # 중견/중소형주 (상대적으로 덜 유명한 종목)
    WatchlistItem("🇰🇷 한국 주식", "035420.KS", "035420", "NAVER"),
    WatchlistItem("🇰🇷 한국 주식", "035720.KS", "035720", "카카오"),
    WatchlistItem("🇰🇷 한국 주식", "051910.KS", "051910", "LG화학"),
    WatchlistItem("🇰🇷 한국 주식", "006400.KS", "006400", "삼성SDI"),
    WatchlistItem("🇰🇷 한국 주식", "207940.KS", "207940", "삼성바이오로직스"),
    WatchlistItem("🇰🇷 한국 주식", "068270.KS", "068270", "셀트리온"),
    WatchlistItem("🇰🇷 한국 주식", "003670.KS", "003670", "포스코퓨처엠"),
    WatchlistItem("🇰🇷 한국 주식", "096770.KS", "096770", "SK이노베이션"),
    WatchlistItem("🇰🇷 한국 주식", "011200.KS", "011200", "HMM"),
    WatchlistItem("🇰🇷 한국 주식", "010130.KS", "010130", "고려아연"),
]

_US_POOL: list[WatchlistItem] = [
    # 대형주 (기준점 역할)
    WatchlistItem("🇺🇸 미국 주식", "AAPL", "AAPL", "Apple"),
    WatchlistItem("🇺🇸 미국 주식", "TSLA", "TSLA", "Tesla"),
    # 중소형 성장주 (상대적으로 덜 유명한 종목)
    WatchlistItem("🇺🇸 미국 주식", "PLTR", "PLTR", "Palantir"),
    WatchlistItem("🇺🇸 미국 주식", "SOFI", "SOFI", "SoFi Technologies"),
    WatchlistItem("🇺🇸 미국 주식", "RIVN", "RIVN", "Rivian"),
    WatchlistItem("🇺🇸 미국 주식", "U", "U", "Unity Software"),
    WatchlistItem("🇺🇸 미국 주식", "RBLX", "RBLX", "Roblox"),
    WatchlistItem("🇺🇸 미국 주식", "DKNG", "DKNG", "DraftKings"),
    WatchlistItem("🇺🇸 미국 주식", "CELH", "CELH", "Celsius Holdings"),
    WatchlistItem("🇺🇸 미국 주식", "IONQ", "IONQ", "IonQ"),
    WatchlistItem("🇺🇸 미국 주식", "ASTS", "ASTS", "AST SpaceMobile"),
    WatchlistItem("🇺🇸 미국 주식", "HOOD", "HOOD", "Robinhood"),
]

_CRYPTO_POOL: list[WatchlistItem] = [
    # 대형 코인 (기준점 역할)
    WatchlistItem("₿ 암호화폐", "BTC-USD", "BTC", "Bitcoin"),
    WatchlistItem("₿ 암호화폐", "ETH-USD", "ETH", "Ethereum"),
    # 중소형 알트코인 (상대적으로 덜 유명한 코인)
    WatchlistItem("₿ 암호화폐", "XRP-USD", "XRP", "Ripple"),
    WatchlistItem("₿ 암호화폐", "SOL-USD", "SOL", "Solana"),
    WatchlistItem("₿ 암호화폐", "ADA-USD", "ADA", "Cardano"),
    WatchlistItem("₿ 암호화폐", "DOGE-USD", "DOGE", "Dogecoin"),
    WatchlistItem("₿ 암호화폐", "LINK-USD", "LINK", "Chainlink"),
    WatchlistItem("₿ 암호화폐", "AVAX-USD", "AVAX", "Avalanche"),
]

CANDIDATE_POOLS: dict[str, list[WatchlistItem]] = {
    "🇰🇷 한국 주식": _KR_POOL,
    "🇺🇸 미국 주식": _US_POOL,
    "₿ 암호화폐": _CRYPTO_POOL,
}

# 하위 호환용 — 이전 버전은 고정 6종목을 썼다. 이제는 build_daily_watchlist()로
# 매번 다르게 구성하는 것을 기본으로 하지만, 필요 시 참고용으로 남겨둔다.
DEFAULT_WATCHLIST: list[WatchlistItem] = [pool[0] for pool in CANDIDATE_POOLS.values()] + [
    pool[1] for pool in CANDIDATE_POOLS.values()
]


def build_daily_watchlist(
    sample_size: int = 3, rng: Optional[random.Random] = None
) -> list[WatchlistItem]:
    """카테고리별 후보 풀에서 매번 다른 조합을 무작위로 추출한다.

    Args:
        sample_size: 카테고리(시장)당 뽑을 종목 수. 풀보다 크면 풀 전체를 쓴다.
        rng: 난수 생성기. 생략하면 매 실행마다 다른 결과(OS 엔트로피 기반)가
            나온다. 테스트에서 결과를 고정하고 싶으면 시드를 준 random.Random을 넘긴다.

    Returns:
        카테고리별로 sample_size개씩 뽑은 WatchlistItem 리스트.
    """
    rng = rng or random.Random()
    watchlist: list[WatchlistItem] = []
    for category, pool in CANDIDATE_POOLS.items():
        k = min(sample_size, len(pool))
        watchlist.extend(rng.sample(pool, k))
    return watchlist


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

    @classmethod
    def from_profile(cls, profile: MarketProfile) -> "TradingConfig":
        """MarketProfile의 리스크 파라미터로 TradingConfig를 만든다."""
        return cls(
            min_confidence=profile.min_confidence,
            max_risk_score=profile.max_risk_score,
            max_position_pct=profile.max_position_pct,
            min_trade_amount=profile.min_trade_amount,
        )


@dataclass
class TradeDecision:
    """종목 1개에 대한 자동매매 실행 결과 (로그/테스트 검증용).

    Attributes:
        item: 대상 종목.
        signal: AI가 실제로 낸 원본 신호 (강제 매수여도 원본 그대로 기록).
        confidence: AI 신뢰도.
        executed: 매매 체결 여부.
        message: 결과 메시지 (관망 사유, 체결 결과 등).
        error: 예외 발생 시 메시지.
        forced: 1개월 소진 페이싱에 의해 강제로 매수가 발동됐는지 여부
            (True면 executed=True라도 AI의 자체 판단만으로 산 것이 아니라는 뜻).
    """

    item: WatchlistItem
    signal: Optional[Signal] = None
    confidence: Optional[float] = None
    executed: bool = False
    message: str = ""
    error: Optional[str] = None
    forced: bool = False


class AutoTrader:
    """AI 분석 신호에 따라 가상 매수/매도를 자동 실행하는 엔진."""

    def __init__(
        self,
        analyzer: BaseAnalyzer,
        config: Optional[TradingConfig] = None,
        watchlist: Optional[list[WatchlistItem]] = None,
        sample_size: int = 3,
        rng: Optional[random.Random] = None,
        today: Optional[date] = None,
        campaign_start_date: date = CAMPAIGN_START_DATE,
        campaign_duration_days: int = CAMPAIGN_DURATION_DAYS,
        risk_guard: Optional["RiskGuard"] = None,
    ) -> None:
        """AutoTrader를 초기화한다.

        Args:
            analyzer: BaseAnalyzer 구현체 (예: ClaudeAnalyzer). 테스트 시 mock 주입 가능.
            config: 리스크/포지션 규칙. 생략하면(None) 종목마다 시장별 기본값
                (market_profiles.MARKET_PROFILES)을 자동으로 적용한다.
                명시적으로 지정하면 모든 종목에 동일하게 적용된다.
            watchlist: 감시 종목 목록. 생략하면 build_daily_watchlist()로
                시장별 후보 풀에서 매번 무작위로 구성한다.
            sample_size: watchlist를 생략했을 때, 카테고리(시장)당 뽑을 종목 수.
            rng: watchlist를 생략했을 때 사용할 난수 생성기 (테스트용).
            today: 1개월 소진 페이싱 계산의 기준 날짜. 생략하면 오늘 날짜를 쓴다
                (테스트에서는 고정된 날짜를 넘겨 재현 가능하게 만든다).
            campaign_start_date: 소진 캠페인 시작일. 기본값은 deployment_pacing의
                CAMPAIGN_START_DATE(2026-08-04).
            campaign_duration_days: 소진 캠페인 전체 기간(일). 기본값 30일.
        """
        self.analyzer = analyzer
        self.config = config
        self.watchlist = (
            watchlist if watchlist is not None
            else build_daily_watchlist(sample_size=sample_size, rng=rng)
        )
        self.today = today
        self.campaign_start_date = campaign_start_date
        self.campaign_duration_days = campaign_duration_days
        # 리스크 가드: Kill Switch / 낙폭 한도 / 주문 크기 검증 (실전 대비 최종 방어선).
        # 생략하면 기본 한도로 생성한다. 테스트에서는 mock/커스텀 주입 가능.
        from src.execution.risk_guard import RiskGuard as _RiskGuard

        self.risk_guard = risk_guard if risk_guard is not None else _RiskGuard()

    def _resolve_config(self, item: WatchlistItem) -> TradingConfig:
        """종목에 적용할 TradingConfig를 결정한다.

        명시적으로 config가 주어졌으면 모든 종목에 그대로 쓰고, 아니면
        종목의 시장 카테고리에 맞는 기본 프로필(market_profiles)에서 만든다.
        """
        if self.config is not None:
            return self.config
        return TradingConfig.from_profile(get_profile(item.category))

    def _decide_position_size(self, cash: float, confidence: float, cfg: TradingConfig) -> float:
        """신뢰도에 비례해 매수 금액을 계산한다 (Position Sizing).

        cfg.min_confidence~1.0 구간을 cfg.max_position_pct의 절반~전체 비중으로
        선형 스케일한다. 신뢰도가 낮을수록 작게, 높을수록 크게 베팅한다.

        Args:
            cash: 해당 카테고리의 현재 보유 현금.
            confidence: AI 분석 신뢰도(0.0~1.0, 이미 min_confidence 이상으로 필터링됨).
            cfg: 적용할 리스크 설정.

        Returns:
            매수에 사용할 금액.
        """
        denom = 1 - cfg.min_confidence
        scale = (
            min(max((confidence - cfg.min_confidence) / denom, 0.0), 1.0)
            if denom > 0 else 1.0
        )
        pct = cfg.max_position_pct * (0.5 + 0.5 * scale)
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
        cfg = self._resolve_config(item)
        profile = get_profile(item.category)
        try:
            df = FetcherRegistry.get_ohlcv(
                symbol=item.yahoo_symbol, market="yahoo", interval="1d", limit=100,
            )
            if df is None or df.empty:
                decision.error = "가격 데이터를 가져오지 못했습니다."
                return decision

            df = add_indicators(df)
            result: AnalysisResult = self.analyzer.analyze(
                df.tail(50), symbol=item.yahoo_symbol, market_context=profile.prompt_context,
            )
            decision.signal = result.signal
            decision.confidence = result.confidence

            price = float(df["close"].iloc[-1])
            sp.init_portfolio(state)
            book = state["portfolio"][item.category]

            status: DeploymentStatus = compute_deployment_status(
                category=item.category,
                initial_balance=sp.INITIAL_BALANCE,
                current_cash=book["cash"],
                today=self.today,
                start_date=self.campaign_start_date,
                duration_days=self.campaign_duration_days,
            )
            effective_min_confidence = pacing_adjusted_min_confidence(cfg.min_confidence, status)
            pacing_note = (
                f" [소진 {status.deployed_pct:.0%}/목표 {status.target_pct:.0%}, "
                f"D-{status.days_remaining}]"
            )
            # SELL은 이미 보유 중이라는 뜻이므로(=이미 소진에 기여) 강제 대상에서 제외한다.
            is_forced = status.force_mode and result.signal != Signal.SELL

            if result.confidence < effective_min_confidence and not is_forced:
                decision.message = (
                    f"신뢰도 부족({result.confidence:.2f} < {effective_min_confidence:.2f}) "
                    f"- 관망{pacing_note}"
                )
                return decision

            if result.signal == Signal.SELL:
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

            elif result.signal == Signal.BUY or is_forced:
                if not is_forced and result.risk_score > cfg.max_risk_score:
                    decision.message = f"위험도 과다({result.risk_score:.2f}) - 매수 보류"
                    return decision
                if is_forced and result.risk_score > FORCE_BUY_MAX_RISK_SCORE:
                    decision.message = (
                        f"강제매수 보류 - 위험도 과도({result.risk_score:.2f} > "
                        f"{FORCE_BUY_MAX_RISK_SCORE}){pacing_note}"
                    )
                    return decision

                amount = self._decide_position_size(book["cash"], result.confidence, cfg)
                if is_forced:
                    amount = max(amount, min(catch_up_amount(status), book["cash"]))

                if amount <= 0:
                    decision.message = f"매수 가능한 현금이 없습니다.{pacing_note}"
                    return decision
                if amount < cfg.min_trade_amount and not is_forced:
                    decision.message = f"매수 가능 금액 부족({amount:,.0f})"
                    return decision

                # ── RiskGuard 최종 검사 (Kill Switch / 낙폭 / 주문 크기) ──
                # AI 판단과 독립적으로 동작하는 마지막 방어선. 실전 전환 시에도
                # 동일 코드가 실돈을 보호한다.
                holdings_cost = sum(
                    float(h.get("qty", 0)) * float(h.get("avg_price", 0))
                    for h in book["holdings"].values()
                )
                verdict = self.risk_guard.check_buy(
                    amount=amount,
                    available_cash=book["cash"],
                    initial_balance=sp.INITIAL_BALANCE,
                    current_total=book["cash"] + holdings_cost,
                    allow_full_cash=is_forced,  # 강제매수(전액 소진 정책)는 비중 상한 면제
                )
                if not verdict.allowed:
                    decision.message = f"🛡️ RiskGuard 차단: {verdict.reason}"
                    return decision

                reason = result.reason
                if is_forced:
                    reason = f"[1개월 소진 목표 강제매수]{pacing_note} {reason}"

                ok, msg = sp.buy(
                    state, item.category, item.display_symbol, item.name, price, amount,
                    source="AUTO_AI", ai_signal=result.signal.value,
                    ai_confidence=result.confidence, ai_reason=reason,
                )
                decision.executed = ok
                decision.forced = is_forced
                decision.message = (f"[강제매수]{pacing_note} " if is_forced else "") + msg

            else:
                decision.message = f"HOLD 신호 - 매매 없음{pacing_note}"

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
    """CLI 진입점: 오늘의 감시 종목(시장별 후보 풀에서 무작위 추출)에 대해 자동매매를 1회 실행한다."""
    logging.basicConfig(level=logging.INFO)
    load_environment()

    from src.engine.claude_analyzer import ClaudeAnalyzer
    from src.trading.auto_trader_logger import log_auto_trade_result

    watchlist = build_daily_watchlist(sample_size=3)
    logger.info(
        "오늘의 감시 종목: " + ", ".join(f"{i.category}:{i.display_symbol}" for i in watchlist)
    )

    trader = AutoTrader(analyzer=ClaudeAnalyzer(), watchlist=watchlist)
    decisions = trader.run_all()

    # 📊 자동으로 CSV/JSON에 기록 (로그 저장)
    log_auto_trade_result(decisions)

    executed = sum(1 for d in decisions if d.executed)
    forced = sum(1 for d in decisions if d.forced)
    logger.info(
        f"자동매매 완료: {len(decisions)}개 종목 분석, {executed}건 체결"
        f"(그 중 강제매수 {forced}건)"
    )


if __name__ == "__main__":
    main()
