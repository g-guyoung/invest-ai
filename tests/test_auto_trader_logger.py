# -*- coding: utf-8 -*-
"""
자동매매 로거 테스트.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.engine.base_analyzer import Signal
from src.trading.auto_trader import TradeDecision, WatchlistItem
from src.trading.auto_trader_logger import AutoTraderLogger


class TestAutoTraderLogger:
    """AutoTraderLogger 테스트."""

    def test_log_decisions_creates_csv(self, tmp_path):
        """로그 파일이 생성되는지 확인."""
        # 임시 경로 설정
        AutoTraderLogger.LOG_FILE = tmp_path / "test_log.csv"

        # 테스트 데이터
        item = WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자")
        decision = TradeDecision(
            item=item,
            signal=Signal.BUY,
            confidence=0.75,
            executed=True,
            forced=False,
            message="매수 신호",
            error=None,
        )

        # 로깅
        AutoTraderLogger.log_decisions([decision])

        # CSV 파일이 생성됨
        assert AutoTraderLogger.LOG_FILE.exists()

        # CSV 내용 확인
        with open(AutoTraderLogger.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 2  # 헤더 + 데이터
            assert "005930" in lines[1]
            assert "BUY" in lines[1]

    def test_log_decisions_multiple(self, tmp_path):
        """여러 종목을 동시에 로깅."""
        AutoTraderLogger.LOG_FILE = tmp_path / "test_log.csv"

        items = [
            WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자"),
            WatchlistItem("🇺🇸 미국 주식", "AAPL", "AAPL", "Apple"),
        ]

        decisions = [
            TradeDecision(
                item=items[0],
                signal=Signal.BUY,
                confidence=0.75,
                    executed=True,
                forced=False,
                message="매수",
                error=None,
            ),
            TradeDecision(
                item=items[1],
                signal=Signal.HOLD,
                confidence=0.50,
                    executed=False,
                forced=False,
                message=None,
                error="신뢰도 부족",
            ),
        ]

        AutoTraderLogger.log_decisions(decisions)

        # CSV 확인
        with open(AutoTraderLogger.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 3  # 헤더 + 2 데이터
            assert "005930" in lines[1]
            assert "AAPL" in lines[2]

    def test_log_decisions_forced_buy(self, tmp_path):
        """강제매수 기록."""
        AutoTraderLogger.LOG_FILE = tmp_path / "test_log.csv"

        item = WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자")
        decision = TradeDecision(
            item=item,
            signal=Signal.HOLD,
            confidence=0.30,
            executed=True,
            forced=True,  # ← 강제매수
            message="1개월 소진 강제매수",
            error=None,
        )

        AutoTraderLogger.log_decisions([decision])

        with open(AutoTraderLogger.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert "forced" in lines[1].lower() or "Yes" in lines[1]

    def test_log_decisions_append(self, tmp_path):
        """로그 append (기존 데이터 유지)."""
        AutoTraderLogger.LOG_FILE = tmp_path / "test_log.csv"

        item = WatchlistItem("🇰🇷 한국 주식", "005930.KS", "005930", "삼성전자")

        # 첫 로깅
        decision1 = TradeDecision(
            item=item,
            signal=Signal.BUY,
            confidence=0.75,
            executed=True,
            forced=False,
            message="매수 1",
            error=None,
        )
        AutoTraderLogger.log_decisions([decision1])

        # 두 번째 로깅 (append)
        decision2 = TradeDecision(
            item=item,
            signal=Signal.SELL,
            confidence=0.80,
            executed=True,
            forced=False,
            message="매도 1",
            error=None,
        )
        AutoTraderLogger.log_decisions([decision2])

        # CSV 확인
        with open(AutoTraderLogger.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 3  # 헤더 + 2 데이터 (헤더는 한 번만)
            assert "BUY" in lines[1]
            assert "SELL" in lines[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
