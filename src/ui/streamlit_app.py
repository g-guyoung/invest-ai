# -*- coding: utf-8 -*-
"""
Streamlit Multi-Market Investment Dashboard.

Supports: Crypto (Binance), US Stocks (Yahoo), Korean Stocks (Yahoo).

Run: streamlit run src/ui/streamlit_app.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fetcher.fetcher_registry import FetcherRegistry
from src.engine import indicators
from src.engine.claude_analyzer import ClaudeAnalyzer

logger = logging.getLogger(__name__)

# ============================================================================
# Streamlit Configuration
# ============================================================================

st.set_page_config(
    page_title="투자 AI - 멀티마켓 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling
st.markdown(
    """
    <style>
    .main {
        padding-top: 0;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# Sidebar: Market & Symbol Selection
# ============================================================================

st.sidebar.title("📊 시장 & 심볼")
st.sidebar.divider()

# Market selection
selected_market = st.sidebar.selectbox(
    "🌐 시장 선택",
    options=["바이낸스 (암호화폐)", "야후 (미국/한국 주식)"],
    index=0,
)

market_key = "binance" if "바이낸스" in selected_market else "yahoo"

# Symbol selection based on market
if market_key == "binance":
    crypto_symbols = list(FetcherRegistry.CRYPTO_SYMBOLS.keys())
    selected_symbols = st.sidebar.multiselect(
        "₿ 암호화폐 선택",
        options=crypto_symbols,
        default=["BTC", "ETH"],
        help="추적할 암호화폐를 하나 이상 선택하세요.",
    )
else:  # yahoo
    stock_symbols = [
        "미국 주식",
        "AAPL",
        "TSLA",
        "MSFT",
        "GOOGL",
        "AMZN",
        "─" * 20,
        "한국 주식",
        "005930.KS",  # 삼성전자
        "000660.KS",  # SK 하이닉스
        "066570.KS",  # LG전자
        "035720.KS",  # 네이버
        "005380.KS",  # 현대자동차
    ]
    selected_symbols = st.sidebar.multiselect(
        "📈 주식 선택",
        options=[s for s in stock_symbols if "─" not in s],
        default=["AAPL", "005930.KS"],
        help="미국 주식(AAPL, TSLA) 또는 한국 주식(.KS)을 선택하세요.",
    )

# Interval selection
selected_interval = st.sidebar.selectbox(
    "⏱️ 간격",
    options=["1d", "1h", "15m", "5m", "1m"],
    index=0,
    help="차트 캔들 간격을 선택하세요.",
)

# Date range
date_range = st.sidebar.date_input(
    "📅 날짜 범위",
    value=(datetime.now() - timedelta(days=90), datetime.now()),
    max_value=datetime.now(),
)

st.sidebar.divider()

# Fetch settings
fetch_limit = st.sidebar.slider("📍 데이터 개수", 10, 500, 100)

st.sidebar.divider()

# AI Analysis toggle
enable_ai = st.sidebar.checkbox("🤖 AI 분석 활성화", value=True)

# ============================================================================
# Main Content
# ============================================================================

st.title("📈 투자 AI - 멀티마켓 대시보드")
st.markdown(
    f"**시장:** {selected_market} | **심볼:** {', '.join(selected_symbols)}"
)

if not selected_symbols:
    st.warning("⚠️ 사이드바에서 최소 하나의 심볼을 선택해주세요.")
    st.stop()

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 가격 차트", "📈 기술적 지표", "🤖 AI 분석", "📋 포트폴리오"]
)

# ============================================================================
# Tab 1: Price Chart
# ============================================================================

with tab1:
    st.subheader("가격 차트")

    try:
        # Fetch data for all selected symbols
        @st.cache_data(ttl=3600)
        def get_market_data(symbol, market_key, interval, limit, start_date, end_date):
            """캐시된 시장 데이터 조회"""
            try:
                return FetcherRegistry.get_ohlcv(
                    symbol=symbol,
                    market=market_key,
                    interval=interval,
                    limit=limit,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                logger.error(f"데이터 조회 실패 {symbol}: {e}")
                return None

        data_dict = {}
        for symbol in selected_symbols:
            df = get_market_data(
                symbol,
                market_key,
                selected_interval,
                fetch_limit,
                date_range[0].strftime("%Y-%m-%d") if len(date_range) > 0 else None,
                date_range[1].strftime("%Y-%m-%d") if len(date_range) > 1 else None,
            )
            if df is not None and not df.empty:
                data_dict[symbol] = df
            else:
                st.warning(f"⚠️ {symbol}: 데이터를 가져올 수 없습니다. (API 제한 또는 심볼 오류)")

        if not data_dict:
            st.error("❌ 선택한 심볼에 사용 가능한 데이터가 없습니다.")
            st.info("💡 팁: 잠시 후 다시 시도하거나, 다른 심볼을 선택해주세요.")
            st.stop()

        # Create multi-line chart
        fig = go.Figure()

        for symbol, df in data_dict.items():
            fig.add_trace(
                go.Scatter(
                    x=df["open_time"],
                    y=df["close"],
                    mode="lines",
                    name=symbol,
                    hovertemplate=f"<b>{symbol}</b><br>Time: %{{x}}<br>Close: %{{y:.2f}}<extra></extra>",
                )
            )

        fig.update_layout(
            title="종가 변동 추이",
            xaxis_title="시간",
            yaxis_title="종가",
            hovermode="x unified",
            height=500,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Display latest prices
        st.subheader("최신 가격")
        price_cols = st.columns(len(data_dict))

        for idx, (symbol, df) in enumerate(data_dict.items()):
            with price_cols[idx]:
                latest_price = df["close"].iloc[-1]
                prev_price = df["close"].iloc[-2] if len(df) > 1 else latest_price
                change = latest_price - prev_price
                change_pct = (change / prev_price * 100) if prev_price != 0 else 0

                st.metric(
                    label=symbol,
                    value=f"${latest_price:.2f}",
                    delta=f"{change:+.2f} ({change_pct:+.2f}%)",
                )

    except Exception as e:
        st.error(f"❌ 가격 차트 오류: {str(e)}")

# ============================================================================
# Tab 2: Technical Indicators
# ============================================================================

with tab2:
    st.subheader("기술적 지표 (RSI, MACD, 볼린저 밴드)")

    try:
        if data_dict:
            symbol = st.selectbox("지표를 볼 심볼 선택:", list(data_dict.keys()))

            if symbol in data_dict:
                df = data_dict[symbol]

                # Calculate indicators
                df_with_indicators = df.copy()
                df_with_indicators["rsi"] = indicators.calc_rsi(df["close"], period=14)
                macd_result = indicators.calc_macd(df["close"])
                df_with_indicators["macd"] = macd_result["macd"]
                df_with_indicators["macd_signal"] = macd_result["macd_signal"]
                bb_result = indicators.calc_bollinger_bands(df["close"], period=20, num_std=2)
                df_with_indicators["bb_upper"] = bb_result["bb_upper"]
                df_with_indicators["bb_lower"] = bb_result["bb_lower"]
                df = df_with_indicators

                # RSI Chart
                fig_rsi = go.Figure()
                fig_rsi.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["rsi"],
                        mode="lines",
                        name="RSI(14)",
                        line=dict(color="orange"),
                    )
                )
                fig_rsi.add_hline(
                    y=70, line_dash="dash", line_color="red", annotation_text="과매수"
                )
                fig_rsi.add_hline(
                    y=30, line_dash="dash", line_color="green", annotation_text="과매도"
                )
                fig_rsi.update_layout(
                    title=f"RSI(14) - {symbol}",
                    xaxis_title="시간",
                    yaxis_title="RSI",
                    height=400,
                )
                st.plotly_chart(fig_rsi, use_container_width=True)

                # MACD Chart
                fig_macd = go.Figure()
                fig_macd.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["macd"],
                        mode="lines",
                        name="MACD",
                        line=dict(color="blue"),
                    )
                )
                fig_macd.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["macd_signal"],
                        mode="lines",
                        name="시그널",
                        line=dict(color="red"),
                    )
                )
                fig_macd.update_layout(
                    title=f"MACD - {symbol}",
                    xaxis_title="시간",
                    yaxis_title="값",
                    height=400,
                )
                st.plotly_chart(fig_macd, use_container_width=True)

                # Bollinger Bands Chart
                fig_bb = go.Figure()
                fig_bb.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["close"],
                        mode="lines",
                        name="Close",
                        line=dict(color="black"),
                    )
                )
                fig_bb.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["bb_upper"],
                        mode="lines",
                        name="Upper Band",
                        line=dict(color="lightgray"),
                        showlegend=True,
                    )
                )
                fig_bb.add_trace(
                    go.Scatter(
                        x=df["open_time"],
                        y=df["bb_lower"],
                        mode="lines",
                        name="Lower Band",
                        line=dict(color="lightgray"),
                        fill="tonexty",
                    )
                )
                fig_bb.update_layout(
                    title=f"Bollinger Bands(20,2) - {symbol}",
                    xaxis_title="Time",
                    yaxis_title="Price",
                    height=400,
                )
                st.plotly_chart(fig_bb, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error calculating indicators: {str(e)}")

# ============================================================================
# Tab 3: AI Analysis
# ============================================================================

with tab3:
    st.subheader("🤖 AI 분석 (Claude)")

    if enable_ai:
        try:
            if data_dict:
                symbol = st.selectbox(
                    "AI 분석 대상 심볼:", list(data_dict.keys()), key="ai_symbol"
                )

                if symbol in data_dict:
                    df = data_dict[symbol]

                    # Calculate indicators for analysis
                    df_analysis = df.copy()
                    df_analysis["rsi"] = indicators.calc_rsi(df["close"], period=14)
                    macd_result = indicators.calc_macd(df["close"])
                    df_analysis["macd"] = macd_result["macd"]
                    df_analysis["macd_signal"] = macd_result["macd_signal"]
                    df = df_analysis

                    with st.spinner("🔄 Claude AI로 분석 중..."):
                        try:
                            analyzer = ClaudeAnalyzer()
                            result = analyzer.analyze(df[-50:], symbol=symbol)

                            # Display results
                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                signal_color = (
                                    "🟢" if result.signal == "BUY"
                                    else "🔴" if result.signal == "SELL"
                                    else "🟡"
                                )
                                st.metric("신호", f"{signal_color} {result.signal}")

                            with col2:
                                st.metric(
                                    "신뢰도",
                                    f"{result.confidence:.1%}",
                                )

                            with col3:
                                st.metric("위험도", f"{result.risk_score:.2f}")

                            with col4:
                                st.metric("분석", "👇")

                            st.info(f"**분석 이유:**\n\n{result.reason}")

                        except Exception as e:
                            st.error(f"❌ AI 분석 오류: {str(e)}")

        except Exception as e:
            st.error(f"❌ AI 분석 탭 오류: {str(e)}")
    else:
        st.info("AI 분석이 비활성화되어 있습니다. 사이드바에서 활성화하여 AI 예측을 확인하세요.")

# ============================================================================
# Tab 4: Portfolio Summary
# ============================================================================

with tab4:
    st.subheader("포트폴리오 요약")

    try:
        if data_dict:
            # Create portfolio table
            portfolio_data = []
            for symbol, df in data_dict.items():
                latest_price = df["close"].iloc[-1]
                prev_price = df["close"].iloc[-2] if len(df) > 1 else latest_price
                change = latest_price - prev_price
                change_pct = (change / prev_price * 100) if prev_price != 0 else 0

                portfolio_data.append(
                    {
                        "심볼": symbol,
                        "최신 가격": f"${latest_price:.2f}",
                        "변동 (24h)": f"{change:+.2f}",
                        "변동률": f"{change_pct:+.2f}%",
                        "데이터 개수": len(df),
                    }
                )

            portfolio_df = pd.DataFrame(portfolio_data)
            st.dataframe(portfolio_df, use_container_width=True)

            # Summary statistics
            st.subheader("통계")
            col1, col2, col3 = st.columns(3)

            with col1:
                total_symbols = len(data_dict)
                st.metric("총 심볼 수", total_symbols)

            with col2:
                total_data_points = sum(len(df) for df in data_dict.values())
                st.metric("총 데이터 개수", total_data_points)

            with col3:
                market_name = "암호화폐" if market_key == "binance" else "주식"
                st.metric("시장", market_name)

    except Exception as e:
        st.error(f"❌ 포트폴리오 탭 오류: {str(e)}")

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    """
    ---
    **투자 AI 대시보드** | 멀티마켓 투자 분석 플랫폼
    - **암호화폐**: 바이낸스 USDT 쌍 (BTC, ETH, XRP, SOL, ADA 등)
    - **주식**: 야후 파이낸스 (미국 & 한국 주식)
    - **AI 분석**: Claude API 기반 거래 신호
    """
)
