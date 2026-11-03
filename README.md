# INVEST AI

한국 주식 · 미국 주식 · 암호화폐 시세를 수집하고 Claude AI가 분석해 **BUY / SELL / HOLD + 신뢰도 + 근거 + 위험도**를
생성하는 투자 플랫폼. 현재는 매일 자동으로 **페이퍼 트레이딩**(가상 자금 매매)을 하며, 실전 브로커 연결을 위한
실행 계층과 리스크 가드까지 갖춰져 있다.

> 최신 진행 상황은 [`PROGRESS.md`](PROGRESS.md) — 2026-11-03 기준 Phase 5 완료, 테스트 175개 통과.

## 시스템 흐름

```
Yahoo Finance / Binance ─▶ fetcher ─▶ indicators ─▶ ClaudeAnalyzer ─▶ AutoTrader
                                                     (signal·conf·      │
                                                      reason·risk)      ▼
                                       DeploymentPacing ─▶ RiskGuard ─▶ Broker(Paper)
                                                                         │
                          Streamlit 대시보드 ◀──── Supabase (지갑·보유·거래내역) ◀┘
                          GitHub Actions: 매일 09:30 KST 자동 실행 + 분석 요약
```

## 프로젝트 구조

```
src/
 ├── fetcher/     # 데이터 수집 — Yahoo(주식·크립토), Binance, FetcherRegistry(시장 자동 라우팅)
 ├── engine/      # 기술적 지표, BaseAnalyzer / ClaudeAnalyzer, 시장별 분석 프로필
 ├── trading/     # AutoTrader(자동매매), 소진 페이싱, 실행 로그
 ├── execution/   # Broker 추상화(Paper/실전), RiskGuard(Kill Switch·일일손실·최대낙폭), BrokerFactory
 ├── portfolio/   # 가상 포트폴리오 + Repository Pattern (Session / Supabase)
 ├── database/    # Supabase 클라이언트
 ├── common/      # retry, env_loader(.env + Streamlit Secrets 통합)
 └── ui/          # Streamlit 앱 (streamlit_app.py), Plotly 통합 차트, 심볼 검색
scripts/          # init_db.sql, analyze_auto_trading.py, go_live_report.py, 1회성 복구 SQL
tests/            # pytest 175개 (외부 API 전부 mock)
docs/             # ARCHITECTURE, DATABASE_SCHEMA, DEPLOYMENT_GUIDE, PHASE_6_DESIGN, reference/
.github/workflows # auto_trade.yml(매일 자동매매+분석), tests.yml(CI)
```

## 설치 & 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY 입력

streamlit run src/ui/streamlit_app.py     # 대시보드
python -m src.trading.auto_trader         # 자동매매 1회 실행
python scripts/go_live_report.py          # 실전 투입 GO/NO-GO 판정
pytest -q                                 # 테스트
```

Windows PowerShell에서는 프로젝트 경로에 공백이 있으므로 항상 따옴표로 감싼다: `cd "C:\Users\us\Desktop\INVEST AI - 1"`.

## 안전장치

- 실전 매매는 기본 **잠금** — `LIVE_TRADING=true`와 `LIVE_TRADING_CONFIRM=I_UNDERSTAND_THE_RISKS`가 모두 있어야 하고, 실전 브로커는 아직 미구현이라 명시적 에러로 중단된다.
- `data/KILL_SWITCH` 파일을 만들면 모든 매수가 즉시 중단된다.
- API 키는 `.env` / Streamlit Secrets / GitHub Secrets에만 둔다.

## 라이선스

MIT
