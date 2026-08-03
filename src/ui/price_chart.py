# -*- coding: utf-8 -*-
"""
통합 가격 차트 모듈.

목적: 한국/미국 주식, 암호화폐를 동일한 방식(Plotly 캔들스틱 + 거래량 + RSI + MACD
      + 볼린저밴드)으로 시각화한다. TradingView 무료 위젯이 일부 거래소(KRX)를
      지원하지 않는 문제를 회피하고, AI 분석에 쓰이는 것과 동일한 데이터로 차트를
      그려 화면 수치와 분석 결과가 항상 일치하도록 보장한다.

설계 노트
---------
- plotly.subplots로 3단 패널(가격+BB / MACD / RSI)을 하나의 Figure로 구성한다.
- 큰 화면(기본 850px)으로 렌더링해 가독성을 높인다.
- 지표 계산은 src.engine.indicators를 재사용해 AI 분석과 동일한 로직을 보장한다.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.engine import indicators


def build_price_chart(
    df: pd.DataFrame,
    title: str,
    height: int = 850,
) -> go.Figure:
    """
    캔들스틱 + 거래량 + RSI + MACD + 볼린저밴드가 포함된 통합 차트를 생성한다.

    Args:
        df: OHLCV DataFrame (columns: open_time, open, high, low, close, volume).
        title: 차트 제목 (종목명 등).
        height: 차트 전체 높이(px).

    Returns:
        plotly Figure 객체 (st.plotly_chart로 렌더링).
    """
    work = df.copy()
    work["rsi"] = indicators.calc_rsi(work["close"], period=14)
    macd_result = indicators.calc_macd(work["close"])
    work["macd"] = macd_result["macd"]
    work["macd_signal"] = macd_result["macd_signal"]
    bb_result = indicators.calc_bollinger_bands(work["close"], period=20, num_std=2)
    work["bb_upper"] = bb_result["bb_upper"]
    work["bb_lower"] = bb_result["bb_lower"]
    bb_mid = work["close"].rolling(20).mean()

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.5, 0.15, 0.175, 0.175],
        subplot_titles=(title, "거래량", "MACD", "RSI(14)"),
    )

    # Row 1: 캔들스틱 + 볼린저밴드
    fig.add_trace(
        go.Candlestick(
            x=work["open_time"],
            open=work["open"], high=work["high"],
            low=work["low"], close=work["close"],
            name="가격",
            increasing_line_color="#e74c3c", decreasing_line_color="#3498db",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=work["bb_upper"], mode="lines",
                    name="BB 상단", line=dict(color="rgba(150,150,150,0.6)", width=1)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=work["bb_lower"], mode="lines",
                    name="BB 하단", line=dict(color="rgba(150,150,150,0.6)", width=1),
                    fill="tonexty", fillcolor="rgba(150,150,150,0.08)"),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=bb_mid, mode="lines",
                    name="20일 이평선", line=dict(color="rgba(255,165,0,0.8)", width=1, dash="dot")),
        row=1, col=1,
    )

    # Row 2: 거래량
    volume_colors = [
        "#e74c3c" if c >= o else "#3498db"
        for c, o in zip(work["close"], work["open"])
    ]
    fig.add_trace(
        go.Bar(x=work["open_time"], y=work["volume"], name="거래량",
               marker_color=volume_colors, showlegend=False),
        row=2, col=1,
    )

    # Row 3: MACD
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=work["macd"], mode="lines",
                    name="MACD", line=dict(color="#2980b9", width=1.5)),
        row=3, col=1,
    )
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=work["macd_signal"], mode="lines",
                    name="시그널", line=dict(color="#e67e22", width=1.5)),
        row=3, col=1,
    )
    macd_hist = work["macd"] - work["macd_signal"]
    hist_colors = ["#e74c3c" if v >= 0 else "#3498db" for v in macd_hist]
    fig.add_trace(
        go.Bar(x=work["open_time"], y=macd_hist, name="MACD 히스토그램",
               marker_color=hist_colors, showlegend=False),
        row=3, col=1,
    )

    # Row 4: RSI
    fig.add_trace(
        go.Scatter(x=work["open_time"], y=work["rsi"], mode="lines",
                    name="RSI(14)", line=dict(color="#8e44ad", width=1.5)),
        row=4, col=1,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=4, col=1)

    fig.update_layout(
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=20),
        xaxis4_title="시간",
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="가격", row=1, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    fig.update_yaxes(title_text="RSI", row=4, col=1, range=[0, 100])

    return fig
