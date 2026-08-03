# -*- coding: utf-8 -*-
"""
src/engine/claude_analyzer.py 에 대한 pytest 테스트.

실제 Anthropic API는 호출하지 않고, client를 mock으로 주입하여
정상/재시도/실패 시나리오를 검증한다.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.engine.base_analyzer import AnalyzerError
from src.engine.claude_analyzer import ClaudeAnalyzer
from src.engine.indicators import add_indicators


def _make_analysis_df(n: int = 40) -> pd.DataFrame:
    rng = np.arange(n, dtype=float)
    close = 100 + rng + np.sin(rng / 3)
    df = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.full(n, 1000.0),
    })
    return add_indicators(df)


class _FakeBlock:
    """Anthropic SDK의 TextBlock을 흉내낸다 (type="text" 속성 포함).

    실제 Claude 응답은 ThinkingBlock 등 text가 아닌 블록을 포함할 수 있으므로,
    ClaudeAnalyzer는 block.type == "text"인 블록만 골라서 읽는다.
    """

    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class _FakeThinkingBlock:
    """text 속성이 없는 ThinkingBlock을 흉내낸다."""

    def __init__(self):
        self.type = "thinking"


class _FakeMessage:
    def __init__(self, text, with_thinking_block=False):
        blocks = []
        if with_thinking_block:
            blocks.append(_FakeThinkingBlock())
        blocks.append(_FakeBlock(text))
        self.content = blocks


class _FakeMessagesAPI:
    """호출 시나리오를 스크립트로 지정할 수 있는 가짜 messages API."""

    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakeClient:
    def __init__(self, side_effects):
        self.messages = _FakeMessagesAPI(side_effects)


VALID_JSON = json.dumps({
    "signal": "BUY",
    "confidence": 0.82,
    "reason": "RSI가 과매도 구간에서 반등하고 있고 거래량이 증가하고 있습니다.",
    "risk_score": 0.35,
})


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("src.common.retry.time.sleep", lambda _: None)


# ── 정상 케이스 ──────────────────────────────────────────────
def test_analyze_success_returns_analysis_result():
    client = _FakeClient([_FakeMessage(VALID_JSON)])
    analyzer = ClaudeAnalyzer(client=client, max_retries=3)

    result = analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")

    assert result.signal.value == "BUY"
    assert result.confidence == 0.82
    assert 0.0 <= result.risk_score <= 1.0
    assert client.messages.call_count == 1


def test_analyze_success_when_json_wrapped_in_extra_text():
    wrapped = f"물론입니다, 분석 결과입니다:\n\n{VALID_JSON}\n\n이상입니다."
    client = _FakeClient([_FakeMessage(wrapped)])
    analyzer = ClaudeAnalyzer(client=client)

    result = analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")

    assert result.signal.value == "BUY"


def test_analyze_success_with_thinking_block_ignores_it():
    """Claude Sonnet 5의 ThinkingBlock이 응답에 섞여 있어도 text 블록만 읽어야 한다."""
    client = _FakeClient([_FakeMessage(VALID_JSON, with_thinking_block=True)])
    analyzer = ClaudeAnalyzer(client=client, max_retries=1)

    result = analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")

    assert result.signal.value == "BUY"


def test_analyze_retries_then_succeeds():
    client = _FakeClient([
        ConnectionError("일시적 네트워크 오류"),
        _FakeMessage(VALID_JSON),
    ])
    analyzer = ClaudeAnalyzer(client=client, max_retries=3, backoff_seconds=0)

    result = analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")

    assert result.signal.value == "BUY"
    assert client.messages.call_count == 2


# ── 실패 케이스 ──────────────────────────────────────────────
def test_analyze_empty_dataframe_raises_immediately():
    client = _FakeClient([])
    analyzer = ClaudeAnalyzer(client=client)

    with pytest.raises(AnalyzerError):
        analyzer.analyze(pd.DataFrame(), symbol="BTCUSDT")

    assert client.messages.call_count == 0


def test_analyze_invalid_json_exhausts_retries():
    client = _FakeClient([_FakeMessage("이건 JSON이 아닙니다.")] * 2)
    analyzer = ClaudeAnalyzer(client=client, max_retries=2, backoff_seconds=0)

    with pytest.raises(AnalyzerError):
        analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")

    assert client.messages.call_count == 2


def test_analyze_schema_violation_exhausts_retries():
    # signal 값이 BUY/SELL/HOLD가 아니므로 pydantic 검증에 실패해야 한다.
    bad_json = json.dumps({
        "signal": "STRONG_BUY",
        "confidence": 0.9,
        "reason": "잘못된 신호 값",
        "risk_score": 0.2,
    })
    client = _FakeClient([_FakeMessage(bad_json)] * 2)
    analyzer = ClaudeAnalyzer(client=client, max_retries=2, backoff_seconds=0)

    with pytest.raises(AnalyzerError):
        analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")


def test_analyze_confidence_out_of_range_raises():
    bad_json = json.dumps({
        "signal": "HOLD",
        "confidence": 1.5,  # 범위 초과
        "reason": "범위를 벗어난 confidence",
        "risk_score": 0.5,
    })
    client = _FakeClient([_FakeMessage(bad_json)])
    analyzer = ClaudeAnalyzer(client=client, max_retries=1, backoff_seconds=0)

    with pytest.raises(AnalyzerError):
        analyzer.analyze(_make_analysis_df(), symbol="BTCUSDT")


def test_missing_api_key_raises_analyzer_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(AnalyzerError):
        ClaudeAnalyzer(api_key=None)
