# -*- coding: utf-8 -*-
"""
시장별 분석 프로필 (Phase 5 Part 3 확장).

목적: 한국 주식 / 미국 주식 / 암호화폐는 거래 시간, 변동성, 가격에 영향을
    미치는 요인이 서로 다르다. RSI/MACD 같은 기술적 지표의 계산식 자체는
    시장과 무관하게 동일하지만, "무엇을 더 비중있게 볼지"와 "리스크를
    어느 정도까지 감수할지"는 시장마다 달라야 한다.

    - 한국 주식: 정규장 시간(평일 09:00~15:30 KST)에만 거래, 외국인/기관
      수급과 코스피/코스닥 전체 지수, 원달러 환율의 영향을 받는다.
    - 미국 주식: 실적 발표, 연준(Fed) 금리 정책, 거시경제 지표에 민감하다.
    - 암호화폐: 24시간 365일(주말 포함) 거래되고 전통 자산보다 변동성이
      훨씬 크며, 실적보다 시장 심리/레버리지 청산의 영향을 크게 받는다.

이 모듈은 그 차이를 두 가지로 반영한다.
1. AI 프롬프트에 추가할 시장별 맥락 문장 (prompt_context)
2. 시장별 기본 리스크 파라미터 (min_confidence / max_risk_score / max_position_pct)
   — 예: 암호화폐는 변동성이 크므로 1회 매수 비중을 더 낮게 잡는다.

src.trading.auto_trader.AutoTrader가 명시적으로 config를 지정하지 않으면
이 프로필의 값을 카테고리별로 자동 적용한다 (Strategy Pattern의 일종 —
시장마다 다른 리스크 전략을 꽂아 쓰는 구조. 향후 시장별로 완전히 다른
분석 전략(Phase: 투자 전략 다양화)으로 확장할 수 있는 지점이기도 하다).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    """시장 하나에 대한 분석 맥락 + 기본 리스크 파라미터.

    Attributes:
        prompt_context: Claude 프롬프트에 추가로 삽입할 시장 설명 문장.
        min_confidence: 이 시장에서 매매를 실행할 최소 신뢰도.
        max_risk_score: 이 시장에서 BUY를 허용할 최대 위험도.
        max_position_pct: 1회 매수 시 현금 대비 최대 비중.
        min_trade_amount: 이 금액 미만이면 매수를 실행하지 않는다.
    """

    prompt_context: str
    min_confidence: float = 0.6
    max_risk_score: float = 0.7
    max_position_pct: float = 0.3
    min_trade_amount: float = 10_000.0


MARKET_PROFILES: dict[str, MarketProfile] = {
    "🇰🇷 한국 주식": MarketProfile(
        prompt_context=(
            "이 종목은 한국거래소(KRX)에 상장된 주식으로 원화(KRW)로 거래되며, "
            "평일 정규장(09:00~15:30 KST)에만 가격이 움직입니다. 외국인/기관 "
            "수급, 코스피·코스닥 전체 지수 흐름, 원달러 환율의 영향을 함께 고려하세요."
        ),
        min_confidence=0.6, max_risk_score=0.7, max_position_pct=0.3,
    ),
    "🇺🇸 미국 주식": MarketProfile(
        prompt_context=(
            "이 종목은 미국 증권거래소(NYSE/NASDAQ)에 상장된 주식으로 달러(USD)로 "
            "거래됩니다. 분기 실적 발표 시즌, 연준(Fed) 금리 정책, 거시경제 지표에 "
            "민감하게 반응할 수 있다는 점을 감안하세요."
        ),
        min_confidence=0.6, max_risk_score=0.7, max_position_pct=0.3,
    ),
    "₿ 암호화폐": MarketProfile(
        prompt_context=(
            "이 자산은 24시간 365일(주말 포함) 거래되는 암호화폐로, 전통 주식보다 "
            "변동성이 훨씬 크고 실적/거시지표보다 시장 심리, 온체인 수급, 레버리지 "
            "청산 등의 영향을 크게 받습니다. 급격한 가격 변동 가능성을 감안해 신중하게 판단하세요."
        ),
        # 변동성이 큰 자산이므로 같은 신뢰도라도 1회 매수 비중과 허용 위험도를 더 보수적으로.
        min_confidence=0.6, max_risk_score=0.6, max_position_pct=0.2,
    ),
}

DEFAULT_PROFILE = MarketProfile(prompt_context="")


def get_profile(category: str) -> MarketProfile:
    """카테고리에 해당하는 시장 프로필을 반환한다 (없으면 중립 기본값)."""
    return MARKET_PROFILES.get(category, DEFAULT_PROFILE)
