# -*- coding: utf-8 -*-
"""
Streamlit Multi-Market Investment Dashboard.

시장: 한국 주식 / 미국 주식 / 암호화폐 (모두 Yahoo Finance 통일 + TradingView 차트)

Run: streamlit run src/ui/streamlit_app.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fetcher.fetcher_registry import FetcherRegistry
from src.engine import indicators
from src.engine.claude_analyzer import ClaudeAnalyzer
from src.ui.symbol_catalog import MARKET_CATALOG, DEFAULT_SYMBOLS, get_symbol_info
from src.ui.tradingview_widget import render_advanced_chart, render_symbol_overview

# ============================================================================
# Streamlit Configuration
# ============================================================================

st.set_page_config(
    page_title="투자 AI - 멀티마켓 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main { padding-top: 0; }
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
# 캐시된 데이터 조회 (Yahoo Finance 통일 - Binance API 클라우드 차단 회피)
# ============================================================================


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_symbol_data(
    yahoo_symbol: str,
    interval: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame | None:
    """
    Yahoo Finance에서 OHLCV 데이터를 조회한다 (30분 캐시).

    Args:
        yahoo_symbol: Yahoo Finance 심볼 (예: "AAPL", "005930.KS", "BTC-USD").
        interval: 캔들 간격.
        limit: 조회 개수.
        start_date: 시작일(YYYY-MM-DD).
        end_date: 종료일(YYYY-MM-DD).

    Returns:
        OHLCV DataFrame 또는 실패 시 None.
    """
    try:
        return FetcherRegistry.get_ohlcv(
            symbol=yahoo_symbol,
            market="yahoo",
            interval=interval,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        logger.error(f"데이터 조회 실패 {yahoo_symbol}: {exc}")
        return None


# ============================================================================
# Sidebar: Market & Symbol Selection
# ============================================================================

st.sidebar.title("📊 시장 & 심볼")
st.sidebar.divider()

market_category = st.sidebar.radio(
    "🌐 시장 선택",
    options=list(MARKET_CATALOG.keys()),
    index=0,
)

catalog = MARKET_CATALOG[market_category]

selected_symbols = st.sidebar.multiselect(
    "📈 종목 선택",
    options=list(catalog.keys()),
    default=DEFAULT_SYMBOLS[market_category],
    format_func=lambda s: f"{s} · {catalog[s]['name']}",
    help="추적할 종목을 하나 이상 선택하세요.",
)

# 차트 간격 (TradingView 형식: 1, 5, 15, 60, D, W, M)
interval_labels = {
    "1일": "D", "1주": "W", "1시간": "60", "15분": "15", "5분": "5",
}
selected_interval_label = st.sidebar.selectbox(
    "⏱️ 차트 간격", options=list(interval_labels.keys()), index=0
)
tv_interval = interval_labels[selected_interval_label]

# 백엔드 데이터(AI 분석용) 조회 간격은 일봉으로 고정 (안정성 우선)
backend_interval = "1d"

date_range = st.sidebar.date_input(
    "📅 날짜 범위 (AI 분석용 데이터)",
    value=(datetime.now() - timedelta(days=90), datetime.now()),
    max_value=datetime.now(),
)

st.sidebar.divider()
fetch_limit = st.sidebar.slider("📍 데이터 개수 (AI 분석용)", 30, 500, 100)
st.sidebar.divider()
enable_ai = st.sidebar.checkbox("🤖 AI 분석 활성화", value=True)

st.sidebar.divider()
st.sidebar.caption(
    "💡 차트는 TradingView 실시간 위젯을 사용합니다. "
    "AI 분석은 Yahoo Finance 데이터를 기반으로 합니다."
)

# ============================================================================
# Main Content
# ============================================================================

st.title("📈 투자 AI - 멀티마켓 대시보드")
st.markdown(f"**시장:** {market_category} | **선택 종목:** {', '.join(selected_symbols) if selected_symbols else '없음'}")

if not selected_symbols:
    st.warning("⚠️ 사이드바에서 최소 하나의 종목을 선택해주세요.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📊 실시간 차트", "🤖 AI 분석", "📋 포트폴리오"])

# ============================================================================
# Tab 1: 실시간 차트 (TradingView)
# ============================================================================

with tab1:
    main_symbol = st.selectbox(
        "메인 차트 종목",
        options=selected_symbols,
        format_func=lambda s: f"{s} · {catalog[s]['name']}",
    )
    main_info = get_symbol_info(market_category, main_symbol)

    st.caption(f"실시간 차트 (RSI · MACD · 볼린저밴드 포함) — {main_info['name']}")
    render_advanced_chart(
        tv_symbol=main_info["tv_symbol"],
        height=550,
        interval=tv_interval,
        show_studies=True,
    )

    if len(selected_symbols) > 1:
        st.divider()
        st.subheader("선택 종목 한눈에 보기")
        overview_symbols = [
            (catalog[s]["name"], catalog[s]["tv_symbol"]) for s in selected_symbols
        ]
        render_symbol_overview(overview_symbols, height=280)

# ============================================================================
# 백엔드 데이터 조회 (AI 분석 / 포트폴리오 공용)
# ============================================================================

data_dict: dict[str, pd.DataFrame] = {}
for symbol in selected_symbols:
    info = get_symbol_info(market_category, symbol)
    df = fetch_symbol_data(
        info["yahoo_symbol"],
        backend_interval,
        fetch_limit,
        date_range[0].strftime("%Y-%m-%d") if len(date_range) > 0 else None,
        date_range[1].strftime("%Y-%m-%d") if len(date_range) > 1 else None,
    )
    if df is not None and not df.empty:
        data_dict[symbol] = df

# ============================================================================
# Tab 2: AI 분석
# ============================================================================

with tab2:
    st.subheader("🤖 AI 분석 (Claude)")

    if not enable_ai:
        st.info("AI 분석이 비활성화되어 있습니다. 사이드바에서 활성화하여 AI 예측을 확인하세요.")
    elif not data_dict:
        st.warning("⚠️ AI 분석을 위한 데이터를 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        ai_symbol = st.selectbox(
            "AI 분석 대상 종목:", list(data_dict.keys()),
            format_func=lambda s: f"{s} · {catalog[s]['name']}",
            key="ai_symbol",
        )

        df = data_dict[ai_symbol]

        # 기술적 지표 계산 (AI 분석 입력용)
        df_analysis = df.copy()
        df_analysis["rsi"] = indicators.calc_rsi(df["close"], period=14)
        macd_result = indicators.calc_macd(df["close"])
        df_analysis["macd"] = macd_result["macd"]
        df_analysis["macd_signal"] = macd_result["macd_signal"]
        bb_result = indicators.calc_bollinger_bands(df["close"], period=20, num_std=2)
        df_analysis["bb_upper"] = bb_result["bb_upper"]
        df_analysis["bb_lower"] = bb_result["bb_lower"]

        # 최신 지표 수치 표시
        latest = df_analysis.iloc[-1]
        ind_col1, ind_col2, ind_col3 = st.columns(3)
        with ind_col1:
            st.metric("RSI(14)", f"{latest['rsi']:.1f}" if pd.notna(latest['rsi']) else "N/A")
        with ind_col2:
            st.metric("MACD", f"{latest['macd']:.2f}" if pd.notna(latest['macd']) else "N/A")
        with ind_col3:
            st.metric("종가", f"{latest['close']:.2f}")

        with st.spinner("🔄 Claude AI로 분석 중..."):
            try:
                analyzer = ClaudeAnalyzer()
                result = analyzer.analyze(df_analysis[-50:], symbol=ai_symbol)

                col1, col2, col3 = st.columns(3)
                with col1:
                    signal_color = (
                        "🟢" if result.signal == "BUY"
                        else "🔴" if result.signal == "SELL"
                        else "🟡"
                    )
                    st.metric("신호", f"{signal_color} {result.signal}")
                with col2:
                    st.metric("신뢰도", f"{result.confidence:.1%}")
                with col3:
                    st.metric("위험도", f"{result.risk_score:.2f}")

                st.info(f"**분석 이유:**\n\n{result.reason}")

            except Exception as e:
                st.error(f"❌ AI 분석 오류: {str(e)}")

# ============================================================================
# Tab 3: 포트폴리오 요약
# ============================================================================

with tab3:
    st.subheader("포트폴리오 요약")

    if not data_dict:
        st.warning("⚠️ 표시할 데이터가 없습니다.")
    else:
        portfolio_data = []
        for symbol, df in data_dict.items():
            info = get_symbol_info(market_category, symbol)
            latest_price = df["close"].iloc[-1]
            prev_price = df["close"].iloc[-2] if len(df) > 1 else latest_price
            change = latest_price - prev_price
            change_pct = (change / prev_price * 100) if prev_price != 0 else 0

            portfolio_data.append({
                "종목": f"{symbol} ({info['name']})",
                "최신 가격": f"{latest_price:,.2f}",
                "변동": f"{change:+,.2f}",
                "변동률": f"{change_pct:+.2f}%",
                "데이터 개수": len(df),
            })

        st.dataframe(pd.DataFrame(portfolio_data), use_container_width=True)

        st.subheader("통계")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("총 종목 수", len(data_dict))
        with col2:
            st.metric("총 데이터 개수", sum(len(df) for df in data_dict.values()))
        with col3:
            st.metric("시장", market_category)

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    """
    ---
    **투자 AI 대시보드** | 멀티마켓 투자 분석 플랫폼
    - **차트**: TradingView 실시간 위젯 (RSI · MACD · 볼린저밴드 내장)
    - **데이터**: Yahoo Finance (한국/미국 주식, 암호화폐 통일)
    - **AI 분석**: Claude API 기반 거래 신호
    """
)
