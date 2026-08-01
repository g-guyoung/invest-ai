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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fetcher.fetcher_registry import FetcherRegistry
from src.engine.indicators import IndicatorCalculator
from src.engine.claude_analyzer import ClaudeAnalyzer

logger = logging.getLogger(__name__)

# ============================================================================
# Streamlit Configuration
# ============================================================================

st.set_page_config(
    page_title="Invest AI - Multi-Market Dashboard",
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

st.sidebar.title("📊 Market & Symbol")
st.sidebar.divider()

# Market selection
selected_market = st.sidebar.selectbox(
    "🌐 Select Market",
    options=["Binance (Crypto)", "Yahoo (US/Korea Stocks)"],
    index=0,
)

market_key = "binance" if "Binance" in selected_market else "yahoo"

# Symbol selection based on market
if market_key == "binance":
    crypto_symbols = list(FetcherRegistry.CRYPTO_SYMBOLS.keys())
    selected_symbols = st.sidebar.multiselect(
        "₿ Select Cryptocurrencies",
        options=crypto_symbols,
        default=["BTC", "ETH"],
        help="Select one or more cryptocurrencies to track.",
    )
else:  # yahoo
    stock_symbols = [
        "US Stocks",
        "AAPL",
        "TSLA",
        "MSFT",
        "GOOGL",
        "AMZN",
        "─" * 20,
        "Korean Stocks",
        "005930.KS",  # Samsung
        "000660.KS",  # SK Hynix
        "066570.KS",  # LG
        "035720.KS",  # Naver
        "005380.KS",  # Hyundai
    ]
    selected_symbols = st.sidebar.multiselect(
        "📈 Select Stocks",
        options=[s for s in stock_symbols if "─" not in s],
        default=["AAPL", "005930.KS"],
        help="Select US stocks (AAPL, TSLA) or Korean stocks (.KS suffix).",
    )

# Interval selection
selected_interval = st.sidebar.selectbox(
    "⏱️ Interval",
    options=["1d", "1h", "15m", "5m", "1m"],
    index=0,
    help="Candle interval for charts.",
)

# Date range
date_range = st.sidebar.date_input(
    "📅 Date Range",
    value=(datetime.now() - timedelta(days=90), datetime.now()),
    max_value=datetime.now(),
)

st.sidebar.divider()

# Fetch settings
fetch_limit = st.sidebar.slider("📍 Limit", 10, 500, 100)

st.sidebar.divider()

# AI Analysis toggle
enable_ai = st.sidebar.checkbox("🤖 Enable AI Analysis", value=True)

# ============================================================================
# Main Content
# ============================================================================

st.title("📈 Invest AI - Multi-Market Dashboard")
st.markdown(
    f"**Market:** {selected_market} | **Symbols:** {', '.join(selected_symbols)}"
)

if not selected_symbols:
    st.warning("⚠️ Please select at least one symbol from the sidebar.")
    st.stop()

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Price Chart", "📈 Technical Indicators", "🤖 AI Analysis", "📋 Portfolio"]
)

# ============================================================================
# Tab 1: Price Chart
# ============================================================================

with tab1:
    st.subheader("Price Chart")

    try:
        # Fetch data for all selected symbols
        data_dict = {}
        for symbol in selected_symbols:
            try:
                df = FetcherRegistry.get_ohlcv(
                    symbol=symbol,
                    market=market_key,
                    interval=selected_interval,
                    limit=fetch_limit,
                    start_date=date_range[0].strftime("%Y-%m-%d")
                    if len(date_range) > 0
                    else None,
                    end_date=date_range[1].strftime("%Y-%m-%d")
                    if len(date_range) > 1
                    else None,
                )
                if not df.empty:
                    data_dict[symbol] = df
            except Exception as e:
                st.error(f"❌ Error fetching {symbol}: {str(e)}")

        if not data_dict:
            st.error("❌ No data available for selected symbols.")
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
            title="Close Price Over Time",
            xaxis_title="Time",
            yaxis_title="Close Price",
            hovermode="x unified",
            height=500,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Display latest prices
        st.subheader("Latest Prices")
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
        st.error(f"❌ Error in Price Chart: {str(e)}")

# ============================================================================
# Tab 2: Technical Indicators
# ============================================================================

with tab2:
    st.subheader("Technical Indicators (RSI, MACD, Bollinger Bands)")

    try:
        if data_dict:
            symbol = st.selectbox("Select symbol for indicators:", list(data_dict.keys()))

            if symbol in data_dict:
                df = data_dict[symbol]

                # Calculate indicators
                calc = IndicatorCalculator()
                df = calc.calculate_rsi(df, period=14)
                df = calc.calculate_macd(df)
                df = calc.calculate_bollinger_bands(df, period=20, std_dev=2)

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
                    y=70, line_dash="dash", line_color="red", annotation_text="Overbought"
                )
                fig_rsi.add_hline(
                    y=30, line_dash="dash", line_color="green", annotation_text="Oversold"
                )
                fig_rsi.update_layout(
                    title=f"RSI(14) - {symbol}",
                    xaxis_title="Time",
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
                        name="Signal",
                        line=dict(color="red"),
                    )
                )
                fig_macd.update_layout(
                    title=f"MACD - {symbol}",
                    xaxis_title="Time",
                    yaxis_title="Value",
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
    st.subheader("🤖 AI Analysis (Claude)")

    if enable_ai:
        try:
            if data_dict:
                symbol = st.selectbox(
                    "Select symbol for AI analysis:", list(data_dict.keys()), key="ai_symbol"
                )

                if symbol in data_dict:
                    df = data_dict[symbol]

                    # Calculate indicators for analysis
                    calc = IndicatorCalculator()
                    df = calc.calculate_rsi(df, period=14)
                    df = calc.calculate_macd(df)
                    df = calc.calculate_bollinger_bands(df, period=20, std_dev=2)

                    with st.spinner("🔄 Analyzing with Claude AI..."):
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
                                st.metric("Signal", f"{signal_color} {result.signal}")

                            with col2:
                                st.metric(
                                    "Confidence",
                                    f"{result.confidence:.1%}",
                                )

                            with col3:
                                st.metric("Risk Score", f"{result.risk_score:.2f}")

                            with col4:
                                st.metric("Reason", "👇")

                            st.info(f"**Analysis Reason:**\n\n{result.reason}")

                        except Exception as e:
                            st.error(f"❌ AI Analysis Error: {str(e)}")

        except Exception as e:
            st.error(f"❌ Error in AI Analysis tab: {str(e)}")
    else:
        st.info("AI Analysis is disabled. Enable it in the sidebar to see AI predictions.")

# ============================================================================
# Tab 4: Portfolio Summary
# ============================================================================

with tab4:
    st.subheader("Portfolio Summary")

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
                        "Symbol": symbol,
                        "Latest Price": f"${latest_price:.2f}",
                        "Change (24h)": f"{change:+.2f}",
                        "Change %": f"{change_pct:+.2f}%",
                        "Data Points": len(df),
                    }
                )

            portfolio_df = pd.DataFrame(portfolio_data)
            st.dataframe(portfolio_df, use_container_width=True)

            # Summary statistics
            st.subheader("Summary Statistics")
            col1, col2, col3 = st.columns(3)

            with col1:
                total_symbols = len(data_dict)
                st.metric("Total Symbols", total_symbols)

            with col2:
                total_data_points = sum(len(df) for df in data_dict.values())
                st.metric("Total Data Points", total_data_points)

            with col3:
                market_name = "Crypto" if market_key == "binance" else "Stocks"
                st.metric("Market", market_name)

    except Exception as e:
        st.error(f"❌ Error in Portfolio tab: {str(e)}")

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    """
    ---
    **Invest AI Dashboard** | Multi-Market Investment Analysis Platform
    - **Crypto**: Binance USDT pairs (BTC, ETH, XRP, SOL, ADA, etc.)
    - **Stocks**: Yahoo Finance (US & Korean stocks)
    - **AI Analysis**: Claude API for trading signals
    """
)
