# -*- coding: utf-8 -*-
"""
Streamlit Multi-Market Investment Dashboard.

시장: 한국 주식 / 미국 주식 / 암호화폐 — 자유 텍스트 검색 + 통합 캔들스틱 차트
     + AI 분석(Claude) + 가상 포트폴리오(페이퍼 트레이딩 MVP)

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

# 환경변수/Secrets를 가장 먼저 로드한다 (이후 모든 모듈이 os.getenv로 값을 읽는다).
from src.common.env_loader import load_environment, check_required_keys

load_environment()

from src.fetcher.fetcher_registry import FetcherRegistry
from src.engine.claude_analyzer import ClaudeAnalyzer
from src.ui.symbol_catalog import CATEGORIES, CATEGORY_PLACEHOLDER, parse_symbol_list
from src.ui.price_chart import build_price_chart
from src.portfolio import session_portfolio as sp

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
    </style>
    """,
    unsafe_allow_html=True,
)

sp.init_portfolio(st.session_state)

# ============================================================================
# 캐시된 데이터 조회 (Yahoo Finance 통일 - 클라우드 API 차단 회피)
# ============================================================================


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_symbol_data(
    yahoo_symbol: str,
    interval: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame | None:
    """Yahoo Finance에서 OHLCV 데이터를 조회한다 (30분 캐시)."""
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
# Sidebar: 시장 선택 + 자유 텍스트 검색
# ============================================================================

st.sidebar.title("📊 시장 & 검색")
st.sidebar.divider()

market_category = st.sidebar.radio("🌐 시장 선택", options=CATEGORIES, index=0)

search_text = st.sidebar.text_input(
    "🔍 종목 검색 (쉼표로 여러 개)",
    placeholder=CATEGORY_PLACEHOLDER[market_category],
    help="원하는 종목 코드/티커를 자유롭게 입력하세요. 쉼표로 여러 개 입력 가능합니다.",
)

symbol_infos = parse_symbol_list(search_text, market_category)

st.sidebar.divider()
fetch_limit = st.sidebar.slider("📍 조회 기간 (캔들 개수)", 30, 500, 150)
st.sidebar.divider()
enable_ai = st.sidebar.checkbox("🤖 AI 분석 활성화", value=True)

# API 키 상태 표시
key_status = check_required_keys("ANTHROPIC_API_KEY")
if not key_status["ANTHROPIC_API_KEY"]:
    st.sidebar.warning("⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. AI 분석이 동작하지 않습니다.")

# ============================================================================
# Main
# ============================================================================

st.title("📈 투자 AI - 멀티마켓 대시보드")

if not symbol_infos:
    st.info(f"👈 사이드바에서 **{market_category}** 종목을 검색해 입력해주세요. (예: {CATEGORY_PLACEHOLDER[market_category]})")
    data_dict = {}
else:
    st.markdown(f"**시장:** {market_category} | **검색 종목:** {', '.join(i['symbol'] for i in symbol_infos)}")

    data_dict = {}
    for info in symbol_infos:
        df = fetch_symbol_data(info["yahoo_symbol"], "1d", fetch_limit, None, None)
        if df is not None and not df.empty:
            data_dict[info["symbol"]] = {"df": df, "name": info["name"], "yahoo_symbol": info["yahoo_symbol"]}
        else:
            st.warning(f"⚠️ {info['symbol']}: 데이터를 가져올 수 없습니다. 심볼을 다시 확인해주세요.")

tab1, tab2, tab3 = st.tabs(["📊 차트", "🤖 AI 분석", "💰 포트폴리오"])

# ============================================================================
# Tab 1: 통합 차트
# ============================================================================

with tab1:
    if not data_dict:
        st.info("검색된 종목이 없습니다.")
    else:
        chart_symbol = st.selectbox(
            "차트로 볼 종목",
            options=list(data_dict.keys()),
            format_func=lambda s: f"{s} ({data_dict[s]['name']})",
        )
        entry = data_dict[chart_symbol]
        fig = build_price_chart(entry["df"], title=f"{chart_symbol} · {entry['name']}", height=850)
        st.plotly_chart(fig, use_container_width=True)

        latest = entry["df"].iloc[-1]
        prev = entry["df"].iloc[-2] if len(entry["df"]) > 1 else latest
        change = latest["close"] - prev["close"]
        change_pct = (change / prev["close"] * 100) if prev["close"] else 0
        col1, col2, col3 = st.columns(3)
        col1.metric("현재가", f"{latest['close']:,.2f}")
        col2.metric("변동", f"{change:+,.2f}", f"{change_pct:+.2f}%")
        col3.metric("거래량", f"{latest['volume']:,.0f}")

# ============================================================================
# Tab 2: AI 분석
# ============================================================================

with tab2:
    st.subheader("🤖 AI 분석 (Claude)")

    if not enable_ai:
        st.info("AI 분석이 비활성화되어 있습니다. 사이드바에서 활성화해주세요.")
    elif not data_dict:
        st.info("먼저 사이드바에서 종목을 검색해주세요.")
    else:
        ai_symbol = st.selectbox(
            "AI 분석 대상 종목:", list(data_dict.keys()),
            format_func=lambda s: f"{s} ({data_dict[s]['name']})",
            key="ai_symbol",
        )
        entry = data_dict[ai_symbol]

        with st.spinner("🔄 Claude AI로 분석 중..."):
            try:
                analyzer = ClaudeAnalyzer()
                result = analyzer.analyze(entry["df"][-50:], symbol=ai_symbol)

                signal_value = result.signal.value if hasattr(result.signal, "value") else str(result.signal)

                col1, col2, col3 = st.columns(3)
                signal_color = (
                    "🟢" if signal_value == "BUY"
                    else "🔴" if signal_value == "SELL"
                    else "🟡"
                )
                col1.metric("신호", f"{signal_color} {signal_value}")
                col2.metric("신뢰도", f"{result.confidence:.1%}")
                col3.metric("위험도", f"{result.risk_score:.2f}")
                st.info(f"**분석 이유:**\n\n{result.reason}")

            except Exception as e:
                st.error(f"❌ AI 분석 오류: {str(e)}")

# ============================================================================
# Tab 3: 가상 포트폴리오 (페이퍼 트레이딩 MVP)
# ============================================================================

with tab3:
    st.subheader("💰 가상 포트폴리오 (페이퍼 트레이딩)")
    st.caption(
        "시장별로 가상자금 1,000,000을 배정해 매수/매도를 체험할 수 있습니다. "
        "(자동 AI 매매 엔진은 다음 단계에서 연결됩니다.)"
    )

    current_prices = {
        symbol: entry["df"]["close"].iloc[-1] for symbol, entry in data_dict.items()
    }

    # ── 매수/매도 실행 (현재 조회 중인 시장) ──────────────────────────────
    if data_dict:
        st.markdown(f"#### 🛒 거래 실행 — {market_category}")
        trade_symbol = st.selectbox(
            "거래할 종목",
            options=list(data_dict.keys()),
            format_func=lambda s: f"{s} ({data_dict[s]['name']})",
            key="trade_symbol",
        )
        price = current_prices[trade_symbol]
        currency = sp.CURRENCY_SYMBOL[market_category]
        st.write(f"현재가: **{currency}{price:,.2f}**")

        buy_col, sell_col = st.columns(2)
        with buy_col:
            amount = st.number_input(
                f"매수 금액 ({currency})", min_value=0.0, step=10000.0, value=100000.0, key="buy_amount"
            )
            if st.button("🟢 매수 실행", use_container_width=True):
                ok, msg = sp.buy(
                    st.session_state, market_category, trade_symbol,
                    data_dict[trade_symbol]["name"], price, amount,
                )
                (st.success if ok else st.error)(msg)

        with sell_col:
            holding = st.session_state["portfolio"][market_category]["holdings"].get(trade_symbol)
            max_qty = holding["qty"] if holding else 0.0
            st.write(f"보유 수량: {max_qty:.4f}")
            if st.button("🔴 전량 매도", use_container_width=True, disabled=max_qty <= 0):
                ok, msg = sp.sell(st.session_state, market_category, trade_symbol, price)
                (st.success if ok else st.error)(msg)

        st.divider()

    # ── 시장별 포트폴리오 요약 ──────────────────────────────────────────
    st.markdown("#### 📊 시장별 요약")
    total_all = 0.0
    for category in sp.CATEGORIES:
        prices_for_cat = current_prices if category == market_category else {}
        summary = sp.get_summary(st.session_state, category, prices_for_cat)
        total_all += summary["total"]
        currency = sp.CURRENCY_SYMBOL[category]

        with st.expander(f"{category} — 총 {currency}{summary['total']:,.0f} (손익 {summary['pnl']:+,.0f}, {summary['pnl_pct']:+.2f}%)", expanded=(category == market_category)):
            c1, c2, c3 = st.columns(3)
            c1.metric("현금", f"{currency}{summary['cash']:,.0f}")
            c2.metric("평가금액", f"{currency}{summary['holdings_value']:,.0f}")
            c3.metric("손익률", f"{summary['pnl_pct']:+.2f}%")

            if summary["holdings"]:
                st.dataframe(pd.DataFrame(summary["holdings"]), use_container_width=True)
            else:
                st.caption("보유 종목이 없습니다.")

            if summary["history"]:
                st.caption("최근 거래 내역")
                st.dataframe(pd.DataFrame(summary["history"]), use_container_width=True)

    st.divider()
    st.metric("💼 전체 통산 자산 (3개 시장 합계, 통화 단위 상이)", f"{total_all:,.0f}")

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    """
    ---
    **투자 AI 대시보드** | 멀티마켓 투자 분석 플랫폼
    - **차트**: 자체 제작 캔들스틱 + 거래량 + RSI + MACD + 볼린저밴드
    - **데이터**: Yahoo Finance (한국/미국 주식, 암호화폐 통일)
    - **AI 분석**: Claude API 기반 거래 신호
    - **포트폴리오**: 가상 페이퍼 트레이딩 (시장별 1,000,000 배정)
    """
)
