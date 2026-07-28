# -*- coding: utf-8 -*-
"""
INVEST AI 대시보드 (Phase 4 MVP).

목적: Binance 데이터 수집 → 기술적 지표 계산 → Claude AI 분석을 한 화면에서
    실행하고, 결과(신호/확신도/근거/리스크)를 시각적으로 보여준다.

실행 방법:
    streamlit run src/dashboard.py

필요 조건:
    - .env에 ANTHROPIC_API_KEY 설정 (AI 분석 실행 시)
    - 인터넷 연결 (Binance/Claude API 호출)
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.engine import AnalyzerError, ClaudeAnalyzer, Signal, add_indicators
from src.fetcher.binance_fetcher import BinanceFetcher, BinanceFetcherError

load_dotenv()

st.set_page_config(page_title="INVEST AI", page_icon="\U0001F4B0", layout="wide")

_SIGNAL_STYLE = {
    Signal.BUY: ("\U0001F7E2 매수 (BUY)", "#1e8e3e"),
    Signal.SELL: ("\U0001F534 매도 (SELL)", "#d93025"),
    Signal.HOLD: ("⚪ 관망 (HOLD)", "#5f6368"),
}


def _render_signal_card(result) -> None:
    """분석 결과(AnalysisResult)를 카드 형태로 렌더링한다."""
    label, color = _SIGNAL_STYLE[result.signal]
    st.markdown(
        f"""
        <div style="border:1px solid {color}; border-radius:10px; padding:1.2rem; background:{color}15;">
            <div style="font-size:1.6rem; font-weight:700; color:{color};">{label}</div>
            <div style="margin-top:0.5rem;">확신도(Confidence): <b>{result.confidence:.0%}</b></div>
            <div>리스크 점수(Risk Score): <b>{result.risk_score:.0%}</b></div>
            <div style="margin-top:0.8rem;">{result.reason}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """대시보드 진입점."""
    st.title("\U0001F4B0 INVEST AI")
    st.caption("Binance 데이터 수집 → 기술적 지표 → Claude AI 투자 신호 분석")

    with st.sidebar:
        st.header("설정")
        symbol = st.text_input("심볼", value="BTCUSDT")
        interval = st.selectbox("인터벌", ["1h", "4h", "1d"], index=2)
        limit = st.slider("캔들 개수", min_value=60, max_value=500, value=200, step=10)
        run = st.button("\U0001F50D 분석 시작", type="primary", use_container_width=True)

    if not run:
        st.info("왼쪽에서 심볼/인터벌을 설정하고 '분석 시작'을 눌러주세요.")
        return

    with st.spinner(f"{symbol} 데이터 수집 중..."):
        try:
            fetcher = BinanceFetcher()
            raw_df = fetcher.get_klines(symbol=symbol, interval=interval, limit=limit)
        except BinanceFetcherError as exc:
            st.error(f"데이터 수집 실패: {exc}")
            return

    if raw_df.empty:
        st.warning("수집된 데이터가 없습니다. 심볼을 확인해주세요.")
        return

    df = add_indicators(raw_df)

    col_chart, col_signal = st.columns([2, 1])

    with col_chart:
        st.subheader(f"{symbol} 종가 추이")
        chart_df = df.set_index("open_time")[["close", "ma20", "ma60"]]
        st.line_chart(chart_df)

    with col_signal:
        st.subheader("AI 투자 신호")
        with st.spinner("Claude AI 분석 중..."):
            try:
                analyzer = ClaudeAnalyzer()
                result = analyzer.analyze(df, symbol=symbol)
            except AnalyzerError as exc:
                st.error(f"AI 분석 실패: {exc}")
                st.caption("`.env`의 ANTHROPIC_API_KEY 설정을 확인해주세요.")
            else:
                _render_signal_card(result)

    st.subheader("최근 데이터 (지표 포함)")
    display_cols = [
        "open_time", "close", "rsi", "macd", "ma5", "ma20", "ma60", "bb_width", "stoch",
    ]
    st.dataframe(df[display_cols].tail(20).iloc[::-1], use_container_width=True)

    st.caption("⚠️ 본 서비스는 학습/보조 목적이며 투자 조언이 아닙니다. 최종 투자 판단과 책임은 사용자 본인에게 있습니다.")


if __name__ == "__main__":
    main()
