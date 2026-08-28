# -*- coding: utf-8 -*-
"""
자동매매 엔진 로깅 모듈 (Auto Trader Logging).

목적: 매일 자동매매 실행 결과를 CSV/JSON으로 기록해서,
     나중에 성과 분석, 통계, 대시보드에 사용할 수 있도록 한다.

동작:
- AutoTrader.run_all() 후 결과를 자동으로 기록
- 파일 위치: data/auto_trading_log.csv
- 컬럼: 날짜, 시간, 카테고리, 종목, 신호, 신뢰도, 위험도, 체결여부, 강제매수여부
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.trading.auto_trader import TradeDecision

logger = logging.getLogger(__name__)


class AutoTraderLogger:
    """자동매매 결과를 기록하는 로거."""

    LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "auto_trading_log.csv"
    JSON_FILE = Path(__file__).resolve().parents[2] / "data" / "auto_trading_log.json"

    # CSV 헤더
    CSV_HEADERS = [
        "timestamp",
        "date",
        "time",
        "category",
        "symbol",
        "name",
        "signal",
        "confidence",
        "executed",
        "forced",
        "message",
        "error",
    ]

    @classmethod
    def log_decisions(cls, decisions: list[TradeDecision]) -> None:
        """여러 종목의 거래 결정을 기록한다.

        Args:
            decisions: AutoTrader.run_all()의 반환값 (TradeDecision 리스트).

        Returns:
            None (파일에 자동 저장).
        """
        now = datetime.now()
        timestamp = now.isoformat()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # CSV 로그
        cls._log_csv(timestamp, date_str, time_str, decisions)

        # JSON 로그 (JSON Lines 형식: 매 실행마다 1줄)
        cls._log_jsonl(timestamp, date_str, time_str, decisions)

        # 콘솔 요약
        cls._print_summary(date_str, time_str, decisions)

    @classmethod
    def _log_csv(
        cls, timestamp: str, date_str: str, time_str: str, decisions: list[TradeDecision]
    ) -> None:
        """CSV 파일에 기록 (append)."""
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 첫 실행이면 헤더 쓰기
        file_exists = cls.LOG_FILE.exists()

        with open(cls.LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cls.CSV_HEADERS)
            if not file_exists:
                writer.writeheader()

            for d in decisions:
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "date": date_str,
                        "time": time_str,
                        "category": d.item.category,
                        "symbol": d.item.display_symbol,
                        "name": d.item.name,
                        "signal": d.signal.value if hasattr(d.signal, "value") else str(d.signal),
                        "confidence": f"{d.confidence:.2%}" if d.confidence else "",
                        "executed": "Yes" if d.executed else "No",
                        "forced": "Yes" if d.forced else "No",
                        "message": d.message or "",
                        "error": d.error or "",
                    }
                )

        logger.info(f"✅ CSV 로그 기록 완료: {cls.LOG_FILE}")

    @classmethod
    def _log_jsonl(
        cls, timestamp: str, date_str: str, time_str: str, decisions: list[TradeDecision]
    ) -> None:
        """JSON Lines 파일에 기록 (append)."""
        cls.JSON_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(cls.JSON_FILE, "a", encoding="utf-8") as f:
            for d in decisions:
                record = {
                    "timestamp": timestamp,
                    "date": date_str,
                    "time": time_str,
                    "category": d.item.category,
                    "symbol": d.item.display_symbol,
                    "name": d.item.name,
                    "signal": d.signal.value if hasattr(d.signal, "value") else str(d.signal),
                    "confidence": round(d.confidence, 4) if d.confidence else None,
                    "executed": d.executed,
                    "forced": d.forced,
                    "message": d.message,
                    "error": d.error,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"✅ JSON 로그 기록 완료: {cls.JSON_FILE}")

    @classmethod
    def _print_summary(cls, date_str: str, time_str: str, decisions: list[TradeDecision]) -> None:
        """콘솔에 요약 정보 출력."""
        total = len(decisions)
        executed = sum(1 for d in decisions if d.executed)
        forced = sum(1 for d in decisions if d.forced)
        confidence_values = [d.confidence for d in decisions if d.confidence is not None]
        avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0

        print("\n" + "=" * 60)
        print(f"🤖 자동매매 실행 완료 | {date_str} {time_str}")
        print("=" * 60)
        print(f"  📊 분석 종목: {total}개")
        print(f"  ✅ 체결: {executed}개 ({executed/total*100:.1f}%)")
        print(f"  ⚡ 강제매수: {forced}개")
        print(f"  📈 평균 신뢰도: {avg_confidence:.1%}")
        print("=" * 60 + "\n")


def log_auto_trade_result(decisions: list[TradeDecision]) -> None:
    """편의 함수: 자동매매 결과를 기록한다.

    Usage:
        from src.trading.auto_trader_logger import log_auto_trade_result
        decisions = trader.run_all()
        log_auto_trade_result(decisions)
    """
    AutoTraderLogger.log_decisions(decisions)
