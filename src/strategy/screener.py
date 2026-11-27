# -*- coding: utf-8 -*-
"""
전 종목 스크리너 — 시장 전체에서 "오늘 살 만한" 후보를 고른다.

목적: 수천 종목을 매일 전부 사고팔 수는 없으므로, 아래 순서로 후보를 좁힌다.
    1. 전체 종목(UniverseItem) 일봉을 Yahoo에서 묶음 다운로드 (200개씩)
    2. 미완성 오늘 봉 제거 (look-ahead 방지)
    3. 필터: 최소 주가, 20일 평균 거래대금(유동성), 1주 가격 ≤ 종목당 예산
    4. 전략(봇과 같은 객체)이 "오늘 새로 진입 신호"를 낸 종목만 남김
    5. 거래대금 큰 순으로 상위 N개

입력: UniverseItem 리스트, ScreenerConfig
출력: ScreenCandidate 리스트 (거래대금 내림차순)

운영 메모: 미국 전 종목(약 6천 개)은 다운로드에 수 분이 걸린다. 결과는 날짜별로
data/universe/screen_<시장>_<날짜>.json 에 캐시되어 같은 날 재실행 시 재사용된다.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from src.execution.market_hours import drop_incomplete_stock_candle
from src.fetcher.kis_master import DEFAULT_CACHE_DIR, UniverseItem
from src.strategy.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

CHUNK_SIZE = 200
HISTORY_PERIOD = "6mo"  # 돌파 20일 + 유동성 20일 계산에 충분


@dataclass(frozen=True)
class ScreenerConfig:
    """스크리너 필터.

    Attributes:
        min_price: 최소 주가 (동전주 제외).
        min_avg_traded_value: 20일 평균 거래대금 하한 (현지 통화).
        max_price: 1주 가격 상한 (= 종목당 예산, 1주도 못 사는 종목 제외).
        max_candidates: 최종 후보 수.
        fresh_signal_only: True면 오늘 새로 진입 신호가 난 종목만 (기본, 권장).
    """

    min_price: float
    min_avg_traded_value: float
    max_price: float
    max_candidates: int = 10
    fresh_signal_only: bool = True


@dataclass(frozen=True)
class ScreenCandidate:
    """스크리너 통과 종목."""

    symbol: str
    yahoo_symbol: str
    name: str
    exchange: str
    last_close: float
    avg_traded_value: float


def yahoo_batch_download(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Yahoo 일봉을 묶음으로 받아 {yahoo심볼: OHLCV DataFrame(open_time 컬럼)}로 반환한다.

    실패한 종목은 결과에서 빠진다 (예외를 던지지 않음 — 일부 실패가 전체를 막지 않도록).
    """
    import yfinance as yf

    result: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), CHUNK_SIZE):
        chunk = symbols[i:i + CHUNK_SIZE]
        try:
            raw = yf.download(
                chunk, period=HISTORY_PERIOD, interval="1d", group_by="ticker",
                auto_adjust=False, progress=False, threads=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Yahoo 묶음 다운로드 실패({i}~{i + len(chunk)}): {type(exc).__name__}")
            continue
        for sym in chunk:
            try:
                df = raw[sym] if len(chunk) > 1 else raw
                df = df.dropna(subset=["Close"]).reset_index()
                df.columns = [str(c).lower() for c in df.columns]
                df = df.rename(columns={"date": "open_time"})
                if not df.empty:
                    result[sym] = df
            except (KeyError, AttributeError):
                continue
    return result


class StockScreener:
    """전 종목 스크리너.

    Args:
        category: 시장 카테고리.
        strategy: 봇과 같은 전략 객체 (신호 일치 보장).
        config: 필터 설정.
        download_fn: yahoo심볼 리스트 → {심볼: DataFrame} (테스트 주입용).
        now_fn: 현재 UTC 시각 (미완성 봉 판단).
        today_fn: 캐시 날짜.
        cache_dir: 결과 캐시 폴더 (None이면 캐시 안 함).
    """

    def __init__(
        self,
        category: str,
        strategy: BaseStrategy,
        config: ScreenerConfig,
        download_fn: Callable[[list[str]], dict[str, pd.DataFrame]] = yahoo_batch_download,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        today_fn: Callable[[], date] = date.today,
        cache_dir: Optional[Path] = DEFAULT_CACHE_DIR,
    ) -> None:
        self.category = category
        self.strategy = strategy
        self.config = config
        self._download = download_fn
        self._now_fn = now_fn
        self._today_fn = today_fn
        self.cache_dir = cache_dir

    def _cache_path(self, key: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"screen_{key}_{self._today_fn().isoformat()}.json"

    def evaluate(self, item: UniverseItem, df: pd.DataFrame) -> Optional[ScreenCandidate]:
        """종목 1개가 필터를 통과하면 후보를 반환한다 (순수 함수)."""
        cfg = self.config
        df = drop_incomplete_stock_candle(df, self.category, self._now_fn())
        if len(df) < 25:
            return None
        close = float(df["close"].iloc[-1])
        if not math.isfinite(close) or close < cfg.min_price or close > cfg.max_price:
            return None
        traded = (df["close"] * df["volume"]).tail(20).mean()
        if not math.isfinite(traded) or traded < cfg.min_avg_traded_value:
            return None
        positions = self.strategy.generate_positions(df)
        last, prev = float(positions.iloc[-1]), float(positions.iloc[-2])
        if last < 0.5 or (cfg.fresh_signal_only and prev >= 0.5):
            return None
        return ScreenCandidate(item.symbol, item.yahoo_symbol, item.name, item.exchange, close, float(traded))

    def screen(self, items: list[UniverseItem], cache_key: Optional[str] = None) -> list[ScreenCandidate]:
        """후보 종목을 고른다 (cache_key가 있으면 같은 날 결과를 재사용).

        Returns:
            거래대금 내림차순 상위 max_candidates개.
        """
        cache = self._cache_path(cache_key) if cache_key else None
        if cache is not None and cache.exists():
            try:
                return [ScreenCandidate(**row) for row in json.loads(cache.read_text(encoding="utf-8"))]
            except (ValueError, TypeError):
                logger.warning("스크리너 캐시 손상 — 다시 계산합니다.")

        by_yahoo = {i.yahoo_symbol: i for i in items}
        data = self._download(list(by_yahoo))
        candidates: list[ScreenCandidate] = []
        for ysym, df in data.items():
            item = by_yahoo.get(ysym)
            if item is None:
                continue
            try:
                cand = self.evaluate(item, df)
            except Exception as exc:  # noqa: BLE001 - 한 종목 데이터 이상이 전체를 막지 않도록
                logger.debug(f"{ysym} 평가 실패: {exc}")
                continue
            if cand is not None:
                candidates.append(cand)
        candidates.sort(key=lambda c: c.avg_traded_value, reverse=True)
        top = candidates[: self.config.max_candidates]
        logger.info(f"{self.category}: {len(items)}종목 중 데이터 {len(data)}개 → 후보 {len(candidates)}개 → 상위 {len(top)}개")

        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps([asdict(c) for c in top], ensure_ascii=False), encoding="utf-8")
            except OSError:
                logger.warning("스크리너 캐시 저장 실패")
        return top


def screen_universe_items(items: list[UniverseItem], extra: Any = ()) -> list[UniverseItem]:
    """전체 목록에 직접 지정 종목(extra)을 합친다 (중복 제거)."""
    merged = {i.symbol: i for i in items}
    for e in extra:
        merged.setdefault(e.symbol, e)
    return list(merged.values())
