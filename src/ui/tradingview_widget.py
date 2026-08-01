# -*- coding: utf-8 -*-
"""
TradingView 위젯 렌더링 헬퍼.

목적: Streamlit 대시보드에 TradingView의 실시간 차트 위젯을 임베드한다.
      위젯은 브라우저에서 TradingView 서버와 직접 통신하므로, 우리 서버가
      Binance/Yahoo API를 직접 호출할 필요가 없다 (클라우드 API 차단 문제 회피).

설계 노트
---------
- Advanced Real-Time Chart 위젯: 캔들 차트 + RSI/MACD/볼린저밴드 스터디를
  TradingView 자체 기능으로 렌더링한다 (우리가 직접 지표를 그릴 필요 없음).
- Symbol Overview 위젯: 여러 종목을 한 번에 미니 차트로 보여준다 (포트폴리오 요약용).
- 컨테이너 id는 심볼마다 고유해야 하므로 특수문자를 제거해 생성한다.
"""

from __future__ import annotations

import re
from typing import List, Tuple

import streamlit.components.v1 as components


def _safe_container_id(prefix: str, symbol: str) -> str:
    """HTML id로 사용 가능한 안전한 문자열을 생성한다."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", "_", symbol)
    return f"{prefix}_{cleaned}"


def render_advanced_chart(
    tv_symbol: str,
    height: int = 550,
    interval: str = "D",
    theme: str = "light",
    show_studies: bool = True,
) -> None:
    """
    TradingView Advanced Real-Time Chart 위젯을 렌더링한다.
    RSI, MACD, 볼린저밴드 스터디가 기본 포함된다.

    Args:
        tv_symbol: TradingView 심볼 (예: "NASDAQ:AAPL", "KRX:005930", "BINANCE:BTCUSDT").
        height: 위젯 높이(px).
        interval: 캔들 간격 ("1", "5", "15", "60", "D", "W", "M").
        theme: 테마 ("light" 또는 "dark").
        show_studies: RSI/MACD/볼린저밴드 스터디 표시 여부.

    Returns:
        None (Streamlit에 직접 렌더링).
    """
    container_id = _safe_container_id("tv_adv", tv_symbol)

    studies_json = (
        '["RSI@tv-basicstudies", "MACD@tv-basicstudies", "BB@tv-basicstudies"]'
        if show_studies
        else "[]"
    )

    html = f"""
    <div class="tradingview-widget-container">
      <div id="{container_id}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "height": {height},
        "symbol": "{tv_symbol}",
        "interval": "{interval}",
        "timezone": "Asia/Seoul",
        "theme": "{theme}",
        "style": "1",
        "locale": "kr",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": false,
        "studies": {studies_json},
        "container_id": "{container_id}"
      }});
      </script>
    </div>
    """
    components.html(html, height=height + 20)


def render_symbol_overview(
    symbols: List[Tuple[str, str]],
    height: int = 300,
    theme: str = "light",
) -> None:
    """
    TradingView Symbol Overview 위젯을 렌더링한다 (여러 종목 미니 차트).

    Args:
        symbols: (표시이름, tv_symbol) 튜플 리스트. 예: [("삼성전자", "KRX:005930")]
        height: 위젯 높이(px).
        theme: 테마 ("light" 또는 "dark").

    Returns:
        None (Streamlit에 직접 렌더링).
    """
    if not symbols:
        return

    symbols_json = ", ".join(
        f'["{name}", "{tv_symbol}|1D"]' for name, tv_symbol in symbols
    )

    html = f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js" async>
      {{
        "symbols": [{symbols_json}],
        "chartOnly": false,
        "width": "100%",
        "height": {height},
        "locale": "kr",
        "colorTheme": "{theme}",
        "autosize": true,
        "showVolume": false,
        "showMA": false,
        "hideDateRanges": false,
        "hideMarketStatus": false,
        "hideSymbolLogo": false,
        "scalePosition": "right",
        "scaleMode": "Normal",
        "fontFamily": "-apple-system, BlinkMacSystemFont, Trebuchet MS, Roboto, Ubuntu, sans-serif",
        "noTimeScale": false,
        "valuesTracking": "1",
        "changeMode": "price-and-percent",
        "chartType": "area"
      }}
      </script>
    </div>
    """
    components.html(html, height=height + 20)


def render_mini_ticker(tv_symbol: str, height: int = 80, theme: str = "light") -> None:
    """
    TradingView 단일 종목 미니 시세 티커 위젯을 렌더링한다.

    Args:
        tv_symbol: TradingView 심볼.
        height: 위젯 높이(px).
        theme: 테마.

    Returns:
        None (Streamlit에 직접 렌더링).
    """
    html = f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js" async>
      {{
        "symbol": "{tv_symbol}",
        "width": "100%",
        "locale": "kr",
        "colorTheme": "{theme}"
      }}
      </script>
    </div>
    """
    components.html(html, height=height)
