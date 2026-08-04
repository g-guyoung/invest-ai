# -*- coding: utf-8 -*-
"""
Claude API 기반 AI 분석기.

목적: 기술적 지표가 추가된 OHLCV DataFrame을 Claude에게 보내
    {signal, confidence, reason, risk_score} 형태의 투자 신호를 받는다.

설계 노트
---------
- BaseAnalyzer를 상속하므로, 추후 GPTAnalyzer/GeminiAnalyzer/LocalLLMAnalyzer도
  동일한 인터페이스로 추가할 수 있다 (Phase 7: Multi AI).
- LLM 응답은 신뢰할 수 없으므로 정규식으로 JSON 블록을 추출한 뒤
  Pydantic(AnalysisResult)으로 검증한다. 형식이 잘못되면 재시도 대상이 된다.
- API 키는 .env의 ANTHROPIC_API_KEY에서 읽는다. 코드에 직접 작성하지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DEFAULT_BACKOFF_SECONDS, DEFAULT_MAX_RETRIES
from src.common.retry import retry_with_backoff
from src.engine.base_analyzer import AnalysisResult, AnalyzerError, BaseAnalyzer

logger = logging.getLogger(__name__)

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"

# 인디케이터 컬럼 중 프롬프트에 요약해서 보여줄 목록
_PROMPT_INDICATOR_COLUMNS = [
    "rsi", "macd", "macd_signal", "ma5", "ma20", "ma60",
    "bb_upper", "bb_lower", "bb_width", "stoch", "atr",
    "momentum_10", "volume_ratio", "trend",
]

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeAnalyzer(BaseAnalyzer):
    """Claude API로 OHLCV+기술지표 데이터를 분석하는 AI 분석기."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_CLAUDE_MODEL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        max_tokens: int = 1024,
        client: Optional[Any] = None,
    ) -> None:
        """ClaudeAnalyzer를 초기화한다.

        Args:
            api_key: Anthropic API 키. 생략 시 환경변수 ANTHROPIC_API_KEY를 사용한다.
            model: 사용할 Claude 모델명.
            max_retries: API 호출/응답 파싱 실패 시 최대 재시도 횟수.
            backoff_seconds: 재시도 간 초기 대기 시간(초).
            max_tokens: 응답 최대 토큰 수.
            client: 외부에서 주입할 Anthropic 클라이언트 (테스트 시 mock 주입용).
                지정하면 api_key/anthropic 패키지 설치 여부를 검사하지 않는다.

        Raises:
            AnalyzerError: client가 없고, API 키도 찾을 수 없거나 anthropic
                패키지가 설치되어 있지 않은 경우.
        """
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_tokens = max_tokens

        if client is not None:
            self.client = client
            return

        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise AnalyzerError(
                "ANTHROPIC_API_KEY가 설정되어 있지 않습니다. .env 파일에 키를 추가하세요."
            )
        try:
            import anthropic
        except ImportError as exc:
            raise AnalyzerError(
                "anthropic 패키지가 설치되어 있지 않습니다. `pip install anthropic`을 실행하세요."
            ) from exc

        self.client = anthropic.Anthropic(api_key=resolved_key)

    def _build_prompt(
        self, df: pd.DataFrame, symbol: str, market_context: Optional[str] = None
    ) -> str:
        """최신 지표 값을 요약하여 Claude에게 보낼 프롬프트를 생성한다.

        Args:
            df: 지표가 포함된 OHLCV DataFrame.
            symbol: 분석 대상 심볼.
            market_context: 시장별 맥락 설명 (생략 가능, market_profiles 참고).
        """
        latest = df.iloc[-1]
        recent_closes = ", ".join(f"{v:.2f}" for v in df["close"].tail(5))

        indicator_lines = "\n".join(
            f"- {col}: {latest[col]:.4f}"
            for col in _PROMPT_INDICATOR_COLUMNS
            if col in latest.index and pd.notna(latest[col])
        )
        if not indicator_lines:
            indicator_lines = "(지표 데이터 부족 - 최근 데이터 구간이 너무 짧음)"

        context_line = f"\n시장 맥락: {market_context}\n" if market_context else ""

        return (
            f"당신은 신중한 퀀트 투자 분석가입니다. 아래 {symbol}의 최신 기술적 지표를 "
            "바탕으로 투자 신호를 판단하세요.\n"
            f"{context_line}\n"
            f"최근 종가 (오래된순): {recent_closes}\n"
            f"현재가: {latest['close']:.2f}\n\n"
            f"기술적 지표:\n{indicator_lines}\n\n"
            "다음 JSON 형식으로만 응답하세요. 다른 설명이나 마크다운 코드블록은 포함하지 마세요.\n"
            "{\n"
            '  "signal": "BUY 또는 SELL 또는 HOLD",\n'
            '  "confidence": 0.0에서 1.0 사이 숫자,\n'
            '  "reason": "판단 근거를 한국어로 2~3문장",\n'
            '  "risk_score": 0.0에서 1.0 사이 숫자 (높을수록 위험)\n'
            "}"
        )

    @staticmethod
    def _parse_response(raw_text: str) -> AnalysisResult:
        """Claude 응답 텍스트에서 JSON을 추출해 AnalysisResult로 검증한다.

        Args:
            raw_text: Claude 응답의 텍스트 본문.

        Returns:
            검증된 AnalysisResult.

        Raises:
            ValueError: 응답에서 JSON 블록을 찾지 못한 경우.
            json.JSONDecodeError: JSON 파싱에 실패한 경우.
            pydantic.ValidationError: 스키마 검증에 실패한 경우 (예: signal 값이
                BUY/SELL/HOLD가 아니거나 confidence가 범위를 벗어난 경우).
        """
        match = _JSON_BLOCK_RE.search(raw_text)
        if not match:
            raise ValueError(f"응답에서 JSON을 찾을 수 없습니다: {raw_text[:200]!r}")
        parsed = json.loads(match.group(0))
        return AnalysisResult.model_validate(parsed)

    def analyze(
        self, df: pd.DataFrame, symbol: str, market_context: Optional[str] = None
    ) -> AnalysisResult:
        """OHLCV+지표 DataFrame을 Claude로 분석하여 투자 신호를 반환한다.

        Args:
            df: src.engine.indicators.add_indicators()를 거친 DataFrame
                (최소 1행 이상, close 컬럼 필수).
            symbol: 분석 대상 심볼 (예: "BTCUSDT").
            market_context: 시장별 맥락 설명 (생략 가능). 한국/미국 주식,
                암호화폐마다 거래시간/변동성/영향 요인이 다르므로
                src.engine.market_profiles의 프로필을 넘기면 더 맥락에
                맞는 판단을 받을 수 있다.

        Returns:
            AnalysisResult(signal, confidence, reason, risk_score).

        Raises:
            AnalyzerError: df가 비어있거나, API 호출/응답 파싱이 max_retries회
                모두 실패한 경우.
        """
        if df.empty:
            raise AnalyzerError("빈 DataFrame은 분석할 수 없습니다.")
        if "close" not in df.columns:
            raise AnalyzerError("DataFrame에 close 컬럼이 없습니다.")

        prompt = self._build_prompt(df, symbol, market_context=market_context)

        def _call_and_parse() -> AnalysisResult:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            # Claude 응답은 Thinking 블록 등 text가 아닌 블록을 포함할 수 있으므로
            # type이 "text"인 블록만 골라 이어붙인다 (첫 블록을 무조건 텍스트로
            # 가정하면 ThinkingBlock에서 AttributeError가 발생한다).
            text_parts = [
                block.text for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            if not text_parts:
                raise ValueError("Claude 응답에서 텍스트 블록을 찾을 수 없습니다.")
            raw_text = "\n".join(text_parts)
            return self._parse_response(raw_text)

        try:
            return retry_with_backoff(
                _call_and_parse,
                max_retries=self.max_retries,
                backoff_seconds=self.backoff_seconds,
                retry_exceptions=(Exception,),
                logger=logger,
                action_name=f"Claude 분석({symbol})",
            )
        except Exception as exc:
            raise AnalyzerError(
                f"Claude 분석이 {self.max_retries}회 모두 실패했습니다: {exc}"
            ) from exc


if __name__ == "__main__":
    from src.engine.indicators import add_indicators
    from src.fetcher.binance_fetcher import BinanceFetcher

    logging.basicConfig(level=logging.INFO)
    fetcher = BinanceFetcher()
    ohlcv = add_indicators(fetcher.get_klines(symbol="BTCUSDT", interval="1d", limit=100))

    analyzer = ClaudeAnalyzer()
    result = analyzer.analyze(ohlcv, symbol="BTCUSDT")
    print(result.model_dump_json(indent=2))
