# -*- coding: utf-8 -*-
"""
전체 종목 목록 수집기 — 한국투자증권 종목정보(마스터) 파일.

목적: 봇이 .env에 적은 몇 종목이 아니라 시장 전체(코스피·코스닥 / NASDAQ·NYSE·AMEX)를
    후보로 쓸 수 있도록, KIS가 매일 공개하는 종목 마스터 파일을 받아 파싱한다.
    (인증 불필요한 공개 다운로드 — API 키를 쓰지 않는다)

파일 형식 (KIS 공식 샘플 open-trading-api/stocks_info 기준)
-----------------------------------------------------------
- kospi_code.mst / kosdaq_code.mst (cp949, 줄 단위):
    [단축코드 9][표준코드 12][한글명 가변][고정폭 꼬리]
    고정폭 꼬리 길이(줄바꿈 제외): 코스피 227, 코스닥 221. 꼬리 앞 2글자 = 그룹코드
    (ST 주식, EF ETF, EN ETN, RT 리츠, MF 뮤추얼펀드, SC 선박투자 등)
- nasmst.cod / nysmst.cod / amsmst.cod (cp949, 탭 구분):
    [국가, 거래소ID, 거래소코드, 거래소명, 심볼, 실시간심볼, 한글명, 영문명, 증권종류(1지수/2주식/3ETF/4워런트), ...]

형식이 바뀌어 파싱 결과가 비정상이면(정상 주식이 거의 없음) KisMasterError로 멈춘다 —
엉뚱한 목록으로 매매하는 것보다 멈추는 게 안전하다.

출력: UniverseItem 리스트 (KIS 주문용 심볼 + Yahoo 시세용 심볼)
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from src.common.retry import retry_with_backoff
from src.execution.market_hours import KR_CATEGORY, US_CATEGORY

logger = logging.getLogger(__name__)

MASTER_BASE_URL = "https://new.real.download.dws.co.kr/common/master/"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "universe"

#: (파일명, 시장명, 고정폭 꼬리 길이)
KR_MASTER_FILES: tuple[tuple[str, str, int], ...] = (
    ("kospi_code.mst", "KOSPI", 227),
    ("kosdaq_code.mst", "KOSDAQ", 221),
)
US_MASTER_FILES: tuple[tuple[str, str], ...] = (
    ("nasmst.cod", "NASD"),
    ("nysmst.cod", "NYSE"),
    ("amsmst.cod", "AMEX"),
)
_KR_STOCK_GROUPS = {"ST"}
_KR_ETF_GROUPS = {"EF"}
_KR_CODE_RE = re.compile(r"^\d{6}$")
_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z./\-]{0,9}$")
_MIN_SANE_ITEMS = 50  # 이보다 적게 파싱되면 형식 변경으로 판단


class KisMasterError(Exception):
    """종목 마스터 다운로드/파싱 실패."""


@dataclass(frozen=True)
class UniverseItem:
    """매매 후보 종목 1개.

    Attributes:
        category: 시장 카테고리.
        symbol: KIS 주문용 심볼 (한국 6자리 / 미국 티커).
        yahoo_symbol: 시세 조회용 Yahoo 심볼 (005930.KS / BRK-B 등).
        name: 종목명.
        exchange: KOSPI | KOSDAQ | NASD | NYSE | AMEX.
        is_etf: ETF 여부.
    """

    category: str
    symbol: str
    yahoo_symbol: str
    name: str
    exchange: str
    is_etf: bool = False


def parse_kr_master(text: str, exchange: str, tail_len: int, include_etf: bool = False) -> list[UniverseItem]:
    """코스피/코스닥 마스터 텍스트를 파싱한다.

    Args:
        text: 디코딩된 파일 내용.
        exchange: "KOSPI" | "KOSDAQ".
        tail_len: 고정폭 꼬리 길이(줄바꿈 제외).
        include_etf: ETF 포함 여부.

    Returns:
        UniverseItem 리스트 (일반 주식, 선택 시 ETF).
    """
    suffix = ".KS" if exchange == "KOSPI" else ".KQ"
    allowed = _KR_STOCK_GROUPS | (_KR_ETF_GROUPS if include_etf else set())
    items: list[UniverseItem] = []
    for raw in text.splitlines():
        if len(raw) <= tail_len + 21:
            continue
        head, tail = raw[:-tail_len], raw[-tail_len:]
        code = head[0:9].strip()
        group = tail[:2]
        if not _KR_CODE_RE.match(code) or group not in allowed:
            continue
        items.append(UniverseItem(
            category=KR_CATEGORY, symbol=code, yahoo_symbol=code + suffix,
            name=head[21:].strip(), exchange=exchange, is_etf=group in _KR_ETF_GROUPS,
        ))
    return items


def parse_us_master(text: str, exchange: str, include_etf: bool = False) -> list[UniverseItem]:
    """미국 거래소 마스터(.cod, 탭 구분) 텍스트를 파싱한다.

    Args:
        text: 디코딩된 파일 내용.
        exchange: "NASD" | "NYSE" | "AMEX" (KIS 주문 거래소 코드).
        include_etf: ETF 포함 여부.

    Returns:
        UniverseItem 리스트 (증권종류 2=주식, 선택 시 3=ETF).
    """
    allowed = {"2", "3"} if include_etf else {"2"}
    items: list[UniverseItem] = []
    for raw in text.splitlines():
        cols = raw.split("\t")
        if len(cols) < 9:
            continue
        symbol, sec_type = cols[4].strip().upper(), cols[8].strip()
        if sec_type not in allowed or not _US_SYMBOL_RE.match(symbol):
            continue
        items.append(UniverseItem(
            category=US_CATEGORY, symbol=symbol, yahoo_symbol=re.sub(r"[./]", "-", symbol),
            name=cols[7].strip() or cols[6].strip(), exchange=exchange, is_etf=sec_type == "3",
        ))
    return items


class KisMasterUniverse:
    """KIS 종목 마스터로 시장 전체 종목 목록을 만든다 (하루 1회 캐시).

    Args:
        cache_dir: 다운로드 캐시 폴더 (data/universe, git 제외).
        include_etf: ETF 포함 여부.
        fetch: (파일명) → zip 바이트. 테스트 주입용 (기본: HTTP 다운로드 + 재시도).
        today_fn: 캐시 날짜 기준.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        include_etf: bool = False,
        fetch: Optional[Callable[[str], bytes]] = None,
        today_fn: Callable[[], date] = date.today,
    ) -> None:
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.include_etf = include_etf
        self._fetch = fetch or self._http_fetch
        self._today_fn = today_fn

    @staticmethod
    def _http_fetch(filename: str) -> bytes:
        import requests

        def attempt() -> bytes:
            resp = requests.get(MASTER_BASE_URL + filename + ".zip", timeout=30)
            resp.raise_for_status()
            return resp.content

        try:
            return retry_with_backoff(
                attempt, max_retries=3, backoff_seconds=1.0, logger=logger, action_name=f"종목 마스터 {filename}",
            )
        except Exception as exc:  # noqa: BLE001
            raise KisMasterError(f"종목 마스터 다운로드 실패({filename}): {type(exc).__name__}") from exc

    def _read(self, filename: str) -> str:
        """파일 내용을 (오늘자 캐시 → 다운로드) 순으로 읽어 cp949 디코딩한다."""
        cache = self.cache_dir / f"{self._today_fn().isoformat()}_{filename}"
        if cache.exists():
            data = cache.read_bytes()
        else:
            blob = self._fetch(filename)
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    data = zf.read(zf.namelist()[0])
            except (zipfile.BadZipFile, IndexError) as exc:
                raise KisMasterError(f"종목 마스터 압축 해제 실패({filename})") from exc
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            except OSError:
                logger.warning("종목 마스터 캐시 저장 실패 — 계속 진행")
        return data.decode("cp949", errors="replace")

    def load(self, category: str) -> list[UniverseItem]:
        """시장 전체 종목을 반환한다.

        Raises:
            KisMasterError: 다운로드 실패 또는 파싱 결과가 비정상적으로 적을 때.
            ValueError: 주식 카테고리가 아닐 때.
        """
        items: list[UniverseItem] = []
        if category == KR_CATEGORY:
            for filename, exchange, tail in KR_MASTER_FILES:
                items += parse_kr_master(self._read(filename), exchange, tail, self.include_etf)
        elif category == US_CATEGORY:
            for filename, exchange in US_MASTER_FILES:
                items += parse_us_master(self._read(filename), exchange, self.include_etf)
        else:
            raise ValueError(f"주식 카테고리가 아닙니다: {category}")

        if len(items) < _MIN_SANE_ITEMS:
            raise KisMasterError(
                f"{category}: 종목 마스터에서 {len(items)}개만 읽혔습니다 — 파일 형식이 바뀌었을 수 있어 중단합니다. "
                "KIS_*_MODE=list 로 종목을 직접 지정해 운영하세요."
            )
        unique: dict[str, UniverseItem] = {i.symbol: i for i in items}
        logger.info(f"{category}: 전체 종목 {len(unique)}개 로드")
        return list(unique.values())


def items_from_symbols(category: str, symbols: Any) -> list[UniverseItem]:
    """직접 지정한 종목 목록을 UniverseItem으로 바꾼다 (한국은 .KS로 가정, 시세 조회 시 .KQ 재시도)."""
    items = []
    for s in symbols:
        s = str(s).strip().upper()
        if category == KR_CATEGORY:
            items.append(UniverseItem(category, s, f"{s}.KS", s, "KRX"))
        else:
            items.append(UniverseItem(category, s, re.sub(r"[./]", "-", s), s, "US"))
    return items
