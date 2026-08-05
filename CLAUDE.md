# INVEST AI — 프로젝트 지침

이 폴더에서 작업할 때는 아래 지침을 항상 따른다.

## 0. 응답 규칙 (필수)

**모든 응답의 마지막에 진행 상황 요약을 포함한다.** 사용자가 매번 "어디까지 됐어?"라고 묻지 않아도 되도록,
다음을 간단히 정리해서 보여준다.

- 이번에 완료한 작업
- 현재 Phase / 다음에 할 일
- 사용자 확인이 필요한 것이 있다면 그것만 짧게 언급 (없으면 생략)

사용자가 별도로 확인을 요청하지 않는 한, 매 단계마다 진행 여부를 묻지 않고 계획대로 진행한다.

## 1. 프로젝트 목표

Binance 데이터를 수집하고 AI(Claude API)가 분석하여 BUY/SELL/HOLD + Confidence Score를 생성하는
투자 신호 플랫폼. 이후 자동매매까지 확장 가능한 구조로 설계한다.

## 2. 개발 원칙 (모든 기능 공통)

요구사항 분석 → 설계 → 코드 작성 → 테스트 작성 → 코드 리뷰 → 개선사항 제안 순서를 따른다.
바로 코드부터 작성하지 않는다.

- Pythonic, 함수 분리, SOLID, 타입힌트, Docstring(목적/입력/출력), 충분한 주석
- 중복 코드 금지
- 모든 API 호출에는 재시도(retry) 또는 에러 핸들링 포함
- API 키 등 민감 정보는 코드에 직접 작성 금지 → `.env` 사용
- 기능 하나당 pytest 테스트(정상 케이스 + 실패 케이스) 함께 작성

## 3. 프로젝트 구조

```
src/
 ├── fetcher/       # 데이터 수집기 (binance_fetcher.py, yahoo_fetcher.py, fetcher_registry.py, base_fetcher.py)
 ├── engine/        # AI 분석 엔진 (indicators.py, base_analyzer.py, claude_analyzer.py)
 ├── common/        # 공통 유틸 (retry.py, env_loader.py — .env/Streamlit secrets 통합 로더)
 ├── database/      # Supabase 연동 (supabase_client.py) — 자동매매 엔진 단계에서 실사용 예정
 ├── portfolio/     # 가상 포트폴리오 (session_portfolio.py — 현재는 session_state 기반 MVP)
 └── ui/            # Streamlit 대시보드 (실 사용 화면)
      ├── streamlit_app.py   # 메인 앱 — Streamlit Cloud 배포 대상
      ├── symbol_catalog.py  # 자유 검색 심볼 정규화 (고정 목록 없음)
      └── price_chart.py     # 통합 캔들스틱+거래량+RSI+MACD+볼린저밴드 차트
tests/
config/
data/
docs/              # ARCHITECTURE.md, DATABASE_SCHEMA.md, DEPLOYMENT_GUIDE.md
scripts/           # init_db.sql (Supabase 초기화 스크립트)
.streamlit/        # config.toml, secrets.toml(로컬 전용, .gitignore 처리됨)
README.md
requirements.txt
CLAUDE.md
PROJECT_ROADMAP.md
```

새 파일도 이 구조를 유지한다.

### 참고: 옛 `src/dashboard.py` / `data_source_registry.py`는 폐기됨
Phase 5부터 대시보드는 `src/ui/streamlit_app.py`, 멀티마켓 라우팅은 `src/fetcher/fetcher_registry.py`(구 `data_source_registry.py`)로 이름이 바뀌었다. 옛 이름을 언급하는 과거 대화 내용은 참고만 하고 실제 작업은 새 경로 기준으로 한다.

## 4. Git 커밋/업로드

기능 완료 시 커밋 메시지만 제안하고 끝내지 않는다. **매번 실제로 `git add` → `git commit`까지 직접 실행한다**
(사용자에게 다시 확인받지 않는다). 커밋 메시지 형식: `[PhaseN][PartM] 설명`. 예: `[Phase2][Part1] Binance 데이터 수집기 구현`

원격 저장소는 `https://github.com/g-guyoung/invest-ai.git` (origin/main)에 연결되어 있다.
인증 토큰은 `.env`의 `GITHUB_TOKEN`에 저장되어 있으므로, 매 기능 완료 시 커밋 후
`git push https://${GITHUB_TOKEN}@github.com/g-guyoung/invest-ai.git main:main` 형태로 실제 push까지 수행한다
(사용자에게 다시 확인받지 않는다). `.env`는 `.gitignore`에 포함되어 있어 토큰이 커밋되지 않는다.

이 저장소는 로컬 작업(2026-07-29)과 원격에 이미 있던 초기 커밋(1차 계획안, LICENSE 등)을
`--allow-unrelated-histories`로 병합한 이력이 있다 — 로컬 구현 버전을 기준으로 하고 LICENSE만 원격에서 가져왔다.

## 5. 새 대화 시작 시 제목

이 프로젝트 안에서 새 대화(세션)를 시작하면, 대화 제목을 `INVEST AI (주제)` 형식으로 짓는다.
예: `INVEST AI (Binance 수집기 구현)`, `INVEST AI (AI 분석 엔진 설계)`.
(대화 제목을 직접 바꾸는 기능이 없는 환경이라면, 응답 맨 앞에 추천 제목을 `제목: INVEST AI (주제)` 형식으로 먼저 안내한다.)

## 6. 현재 진행 상황 (2026-08-04 기준)

- Phase 1 (스캐폴딩): 완료
- Phase 2 Part 1 (Binance OHLCV 수집기): 완료
- Phase 3 (AI 분석 엔진): 완료 — indicators / base_analyzer / claude_analyzer / retry 공통화
- Phase 4 MVP (구 `src/dashboard.py`): 완료, 이후 Phase 5에서 `src/ui/streamlit_app.py`로 대체됨
- **Phase 5 Part 1 (멀티마켓 대시보드): 완료**
  - `src/fetcher/fetcher_registry.py` — 한국/미국 주식 + 암호화폐 자동 라우팅
  - `src/fetcher/yahoo_fetcher.py` — 한국(.KS)/미국 주식 지원, 네이버(035420) 등 종목코드 버그 수정 완료
  - 22개+ pytest 테스트 통과

- **Phase 5 Part 2 (클라우드 배포 + 페이퍼 트레이딩 준비): 대부분 완료, 진행 중**
  - ✅ Streamlit Cloud 배포 완료 (GitHub `main` 브랜치와 자동 연동, push하면 자동 재배포)
  - ✅ `src/common/env_loader.py` — 로컬 `.env`와 Streamlit Cloud `Secrets`를 동시에 지원하도록
    `os.environ`에 통합 로드. **Streamlit Cloud에서는 `.env`가 아니라 앱 Settings → Secrets에
    TOML 형식으로 `ANTHROPIC_API_KEY = "..."` 를 직접 입력해야 인식됨** (이미 설정 완료, 2026-08-01).
  - ✅ 고정 종목 목록 제거 → `src/ui/symbol_catalog.py`로 자유 텍스트 검색 지원 (한국 6자리 코드,
    미국 티커, 암호화폐 베이스심볼을 자동으로 Yahoo 심볼로 정규화)
  - ✅ 차트를 TradingView 위젯에서 자체 제작 Plotly 통합 차트(`src/ui/price_chart.py`)로 전환
    — TradingView 무료 위젯이 한국거래소(KRX)를 지원하지 않아 엉뚱한 종목이 표시되는 문제가 있었음.
    지금은 캔들스틱+거래량+RSI+MACD+볼린저밴드가 한 차트(850px)에 통합되어 있고, AI 분석과
    동일한 데이터를 쓰므로 화면 수치와 분석 결과가 항상 일치함.
  - ✅ 암호화폐 데이터소스를 Binance API → Yahoo Finance(`BTC-USD` 등)로 전환
    — Streamlit Cloud 서버 IP가 Binance에서 451(지역 차단)을 받아 크립토 조회가 항상 실패했었음.
  - ✅ Claude Sonnet 5의 `ThinkingBlock` 파싱 버그 수정 (`claude_analyzer.py`) — 응답 content의
    첫 블록을 무조건 텍스트로 가정하던 코드를 `type == "text"` 블록만 골라 읽도록 수정, 테스트 추가.
  - ✅ AI 신호 표시 버그 수정 — Python 3.11+에서 `str+Enum`이 `f"{signal}"` 시 "Signal.HOLD"처럼
    나오는 문제를 `result.signal.value`로 명시적으로 꺼내도록 수정.
  - ✅ `src/database/supabase_client.py` — Supabase(PostgreSQL) CRUD 모듈. Phase 5 Part 3에서
    지갑(`wallets`)/보유종목(`wallet_holdings`)/거래내역(`wallet_trades`) CRUD 메서드 추가 완료.
  - ✅ `src/portfolio/session_portfolio.py` + Streamlit "💰 포트폴리오" 탭 — 가상 매수/매도 MVP.
    시장별(한국 주식 ₩1,000,000 / 미국 주식 $1,000,000 / 암호화폐 $1,000,000) 가상자금을 배정해
    직접 매수/매도 버튼으로 체험 가능.
  - ⚠️ `src/ui/tradingview_widget.py`는 더 이상 코드에서 사용하지 않지만, 로컬 파일 잠금 문제로
    삭제하지 못해 죽은 코드로 남아있음. 언젠가 여유 있을 때 정리.

- **Phase 5 Part 3 (포트폴리오 영구 저장 + AI 자동매매 엔진): 완료, 실사용 시작됨** (2026-08-04)
  - ✅ **포트폴리오 영구 저장 (Repository Pattern)** — `src/portfolio/base_repository.py`(인터페이스),
    `session_repository.py`(세션 폴백, 기존 동작과 동일), `supabase_repository.py`(Supabase 영구 저장),
    `repository_factory.py`(SUPABASE_URL/KEY 설정+연결 성공 시 자동으로 Supabase 사용, 그 외에는
    안전하게 세션으로 폴백). `session_portfolio.py`의 `buy()`/`sell()`/`init_portfolio()` 시그니처는
    그대로 유지했고 내부에서만 저장소를 호출하도록 바꿔서, Streamlit UI 코드는 전혀 수정하지 않았다.
  - ✅ `scripts/init_db.sql`에 `wallets`/`wallet_holdings`/`wallet_trades` 테이블 추가
    (기존 `portfolio`/`orders` 테이블은 symbols 사전 등록 FK가 필요해 자유 검색 심볼과 안 맞아서
    건드리지 않고 그대로 둠 — 새 테이블은 symbol을 문자열로 직접 저장).
  - ✅ **Supabase 프로젝트 실제 생성 완료** — `invest-ai`(Seoul 리전), URL
    `https://qvyjphmowsjcvtsqmsyy.supabase.co`. `init_db.sql` 실행 완료(RLS는 미적용 —
    단일 사용자 MVP라 anon key로 서버사이드에서만 접근하므로 지금 단계에서는 허용, 다중 사용자
    단계(Phase 6+)에서 Supabase Auth + RLS 정책 설계 필요, 다음 개선사항으로 기록).
    로컬 `.env`와 Streamlit Cloud Secrets에 `SUPABASE_URL`/`SUPABASE_KEY` 등록 완료 — 실제로
    새로고침해도 포트폴리오가 유지되는 것까지 확인됨.
  - ✅ **AI 자동 트레이딩 엔진** (`src/trading/auto_trader.py`) — `AutoTrader` 클래스가 매 실행마다
    시장별 후보 풀(`CANDIDATE_POOLS`)에서 무작위로 감시 종목을 구성(`build_daily_watchlist`)해
    Claude로 분석 → 신뢰도/위험도 규칙 통과 시 `session_portfolio.buy()/sell()`을 그대로 재사용해
    자동 체결한다. `python -m src.trading.auto_trader`로 단독 실행 가능.
  - ✅ **시장별 분석 프로필** (`src/engine/market_profiles.py`, 신규) — 한국 주식(정규장/외국인 수급),
    미국 주식(실적/연준 정책), 암호화폐(24시간/고변동성)마다 다른 프롬프트 맥락을 Claude에게
    전달하고, 리스크 파라미터도 시장별로 다르게 적용한다(암호화폐는 1회 매수 비중을 더 보수적으로:
    `max_position_pct` 0.2 vs 주식 0.3, `max_risk_score` 0.6 vs 주식 0.7). `AutoTrader`에 명시적
    `config`를 안 주면 종목별 시장 프로필이 자동 적용되고, Streamlit "AI 분석" 탭도 동일 맥락을 쓴다.
  - ✅ **감시 종목 다양화** — 기존 고정 6종목(삼성전자/SK하이닉스/AAPL/TSLA/BTC/ETH)을 시장별
    후보 풀(대형주 2개 + 중소형주 여러 개, 총 KR 12 / US 12 / 암호화폐 8종목)로 확장하고, 매 실행마다
    카테고리당 3개씩 무작위로 뽑아 분석하도록 바꿨다 — 매번 유명 종목만 반복 거래하지 않기 위함.
    (완전한 스크리너 연동은 아직 없어 임의 큐레이션한 풀 안에서만 순환함 — 다음 개선사항으로 기록.)
  - ✅ **스케줄러** — `.github/workflows/auto_trade.yml` (GitHub Actions, 매일 00:30 UTC = 한국시간
    09:30 cron + 수동 실행 버튼). GitHub 저장소 Secrets(`ANTHROPIC_API_KEY`/`SUPABASE_URL`/
    `SUPABASE_KEY`) 등록 완료, 수동 실행(workflow_dispatch)으로 실제 동작 확인됨(58초, 6개 종목
    분석, Supabase 연결/조회 성공 — 이때는 전부 신뢰도 부족으로 관망했음, 정상 동작).
  - ✅ pytest 47개 신규 테스트 전부 통과 (`test_portfolio_repository.py`, `test_session_portfolio.py`,
    `test_auto_trader.py`, `test_market_profiles.py` — 정상/실패/엣지 케이스 + 저장소 폴백 + 시장별
    설정 자동 적용 시나리오 포함).
  - GitHub Actions에 `.github/workflows/*.yml` push하려면 PAT에 **Workflows: Read and write** 권한이
    별도로 필요했음(기존 Contents 권한만으로는 거부됨) — Fine-grained PAT Edit에서 추가함, 기록해둠.

- **Phase 5 Part 4 (1개월 강제 소진 페이싱 실험): 완료** (2026-08-04)
  - 사용자 판단: 관망(HOLD) 위주로는 매매 학습(데이터 축적)에 도움이 안 되고, 원래 계획한
    1~2개월 관찰 기간도 1개월로 단축하기로 함. **캠페인 시작일(2026-08-04)로부터 30일 안에
    카테고리별 100만원(한국 주식/미국 주식/암호화폐 각각, 합 300만원)을 반드시 소진한다**는
    가정을 코드로 강제하기로 결정.
  - ✅ **`src/trading/deployment_pacing.py`** (신규) — 순수 계산 모듈. 오늘까지 도달했어야 할
    소진율(경과일수/30, 선형 배분)과 실제 소진율(투입액/초기자금)을 비교해 `DeploymentStatus`를
    계산한다. 2단계 개입:
    1. **연성 유도**: 목표보다 뒤처질수록 `min_confidence`를 점진적으로 낮춘다(최저 0.35,
       `pacing_adjusted_min_confidence`) — AI 스스로 더 쉽게 매수 기회를 잡도록 문턱만 낮춤.
    2. **경성 강제**: 마감 5일 전인데도 소진율이 70% 미만이면(`force_mode`), HOLD 신호라도
       강제로 매수한다. SELL 신호는 이미 보유 중이라는 뜻이므로 강제 대상에서 제외. 강제
       매수여도 위험도가 0.9를 넘으면 보류(`FORCE_BUY_MAX_RISK_SCORE`, 최소 안전장치).
       강제 매수 금액은 "남은 현금 ÷ (잔여일수+1)"로 계산해(`catch_up_amount`) 마감일까지
       부드럽게 소진되게 하고, 마감 당일엔 남은 현금 전액을 투입한다.
  - ✅ **`src/trading/auto_trader.py` 수정** — `AutoTrader`가 매매 판단 전에
    `compute_deployment_status()`로 카테고리별 진행 상태를 계산하고, 위 2단계를 적용한다.
    `TradeDecision.forced` 필드로 이번 체결이 AI 자체 판단인지 강제 매수인지 구분해 기록하고,
    강제 매수 시 거래 사유(`ai_reason`)에 `[1개월 소진 목표 강제매수]` 표시를 남겨 대시보드에서
    구분 가능하게 했다(감사 추적). `AutoTrader(..., today=..., campaign_start_date=...,
    campaign_duration_days=...)`로 테스트 시 날짜를 고정할 수 있게 했다.
  - ✅ pytest 신규 20개 테스트 통과(`test_deployment_pacing.py` 15개, `test_auto_trader.py`
    강제매수 시나리오 5개 추가) — 정상 페이싱/뒤처짐/강제모드 전환/SELL 예외/위험도 상한/
    마감일 전액 소진 등 엣지 케이스 포함. 전체 스위트 134 passed(무관한 기존 Yahoo/Binance
    fetcher 목킹 이슈 9건은 이번 변경과 무관 — 별도 확인 필요 사항으로 기록).

### 다음 할 일 (Phase 5 Part 4 마무리 — 완료, 1개월 강제 소진 운영 관찰 단계)

사용자 목표: **Claude가 직접 한국주식/미국주식/암호화폐에 각 100만원(총 300만원) 가상 투자금으로
2026-08-04부터 30일 안에 반드시 소진하며 매일 자동으로 페이퍼 트레이딩을 하고, 그 결과를
실시간 대시보드에서 지켜보는 것.** (원래 1~2개월 관찰 계획에서 1개월 + 강제 소진으로 변경됨.)

남은 일:
1. 매일 자동 실행 로그에서 강제매수(`forced=True`) 비중을 지켜본다 — 너무 자주 강제 발동되면
   `FORCE_BUY_DEPLOYED_PCT_THRESHOLD`(0.7)나 `FORCE_BUY_DAYS_REMAINING_THRESHOLD`(5)를
   조정해 AI 자체 판단 비중을 더 늘릴지 판단 (며칠치 로그를 더 모아보고 결정).
2. 캠페인 종료일(2026-09-02 근처, 시작일+30일) 기준으로 3개 카테고리 모두 실제로 100만원에
   근접하게 소진됐는지 확인 — 스크린 결과가 예상과 다르면 페이싱 파라미터 재조정.
3. 스크리너 연동해서 `CANDIDATE_POOLS`를 수동 큐레이션이 아니라 실제 시장 전체에서 뽑도록 확장
   (진짜 "듣도 보도 못한" 초소형주까지 다루려면 필요).
4. 다중 사용자 단계로 갈 때 Supabase RLS 정책 설계 (지금은 단일 사용자라 미적용).

### 알려진 이슈 / 운영 메모
- **로컬(Windows) Git lock 파일 문제가 자주 발생함**: `.git/index.lock`, `.git/HEAD.lock` 등이 남아
  `git commit`/`git push`가 막히는 일이 반복됨 (추정 원인: OneDrive 동기화 또는 백신 프로그램이
  `.git` 폴더를 감시). 발생 시 사용자가 탐색기에서 해당 `.lock` 파일을 수동 삭제해야 진행 가능 —
  Claude가 대신 지울 수 없으므로(파일 잠김), 매번 사용자에게 삭제를 요청하고 대기한다.
- Anthropic API는 계정에 크레딧이 있어야 동작한다 (2026-08-01 사용자가 충전 완료, 잔액 소진 시 재충전 필요).
- Streamlit Cloud 앱 URL은 Streamlit Cloud 콘솔("내 앱" 목록)에서 확인 가능 (구체적 URL은 이 문서에 기록되지 않음).

### 실행 전 확인 사항
- Streamlit Cloud: Settings → Secrets에 `ANTHROPIC_API_KEY` 설정 완료 (2026-08-01).
  Supabase 관련 키(`SUPABASE_URL`, `SUPABASE_KEY`)는 아직 미설정.
- 로컬 개발 시 `.env`의 `ANTHROPIC_API_KEY` 설정 완료 (2026-07-29, 만료 없음(Never)으로 발급).
- 샌드박스 환경은 외부 네트워크(Binance API, Anthropic API)가 막혀 있어 실제 데이터/실제 API 호출 검증은
  로컬 PC 또는 Streamlit Cloud에서만 가능. 코드 자체는 mock 기반 pytest로 검증됨(`test_claude_analyzer.py` 등).

## 7. 구글 드라이브 동기화

`README.md`와 `CLAUDE.md`는 구글 드라이브의 "INVEST AI" 폴더에도 문서로 올려둔다.

- 폴더: https://drive.google.com/drive/folders/10gCC7AUZ9iyyzBKJQA5h7vp5u5cT9o1O
- 최초 업로드본(2026-07-29): README.md `1jScygtWIQzk7YeVoN0hLIaA3i_LF8DjGRdVw6N70y08`,
  CLAUDE.md `1U-qCOXQcGBNoWnE-pc_49h6RQcNfgJxPJYmFNQJcYA4`

**주의**: 현재 연결된 구글 드라이브 도구는 파일 생성만 가능하고 기존 문서를 덮어쓰거나 삭제하는 기능이 없다.
따라서 "동기화"는 실시간 덮어쓰기가 아니라, **두 파일 중 하나라도 내용이 바뀌면 위 폴더 안에
`README.md (YYYY-MM-DD)` / `CLAUDE.md (YYYY-MM-DD)` 형식으로 그날 날짜를 붙인 새 문서를 만드는 방식**으로
동작한다 (사용자에게 다시 확인받지 않는다). 즉 폴더에는 시간순으로 여러 버전이 쌓이며, 가장 최근 날짜가
붙은 문서가 최신본이다. 덮어쓰기/삭제 기능이 연결되면 이 방식은 개선한다.

## 8. 참고 자료

루트의 `프로젝트.pdf` / `발표자료_최종_20221169_김규영.pptx` — InvestAI 앱 기획서(학교 과제).
`20221169 인공지능 최종 과제.py` — 개별 종목 매수/매도 판단 프로토타입(yfinance + RandomForest + TensorFlow).
Phase 3 AI 엔진 설계 시 이 프로토타입의 피처 엔지니어링(RSI, MACD, 볼린저밴드 등)을 참고할 수 있다.

**디자인 시스템 원본**: `프로젝트.pdf`의 5장(프로토타이핑 디자인)에 이미 확정된 디자인 시스템이 있다.
새 웹 앱 UI를 만들 때는 매번 새로 정하지 말고 이 톤을 그대로 계승한다.
- 앱명/컨셉: "Invest AI" — "AI가 실시간으로 매수·매도를 도와주는 스마트 투자 파트너"
- 컬러: `#0092F3`(블루, 신뢰·전문성) / `#03D8C6`(민트, 스마트·AI) / `#FFFFFF`(화이트, 직관성)
- IA(정보구조): 메인 → 내 투자 / 종목 분석 / AI 추천 / 포트폴리오 / 투자 비교 (하단 탭 내비게이션)
- 확정된 화면: 인트로(스플래시), 메인(총자산+빠른메뉴+인기종목), 내 투자(자산구성 파이차트+보유종목+거래내역),
  종목 분석, AI 추천(신뢰도 %+매수/강력매수/중립 신호), 포트폴리오(리스크 등급+레이더차트+월별 수익률), 투자 비교(비중설정+리밸런싱)

## 9. 와이어프레임 & Figma 시각화 지침 (필수)

프로젝트 진행 방향(새 기능, 새 화면, 새 플로우)을 정할 때는 텍스트 설명으로만 끝내지 않고,
**와이어프레임으로 표현하고 Figma/FigJam으로 도식화**해서 눈으로 볼 수 있게 돕는다.

- 새 화면/플로우를 설계할 때: 저해상도 와이어프레임(박스+레이블 수준)을 먼저 만든다.
- Figma MCP 연동이 되어 있으면 `get_figjam`/`generate_diagram` 등으로 FigJam 보드나 Figma 디자인에 직접 반영한다.
- Figma 연동이 안 되어 있으면, 연결을 제안하거나 SVG/HTML 와이어프레임으로 대체 시각화를 제공한다.
- 기존 `프로젝트.pdf` 디자인 시스템(8장 참고)과 톤을 맞춘다.

## Git 동기화 규칙 (필수, 맥/데스크탑 공용)

이 프로젝트는 맥(MacBook Air)과 데스크탑(Windows) 두 기기에서 작업합니다.
반드시 아래 순서를 지킬 것.

**작업 시작 전 (항상 먼저!):**
```bash
git pull
```
→ 다른 기기에서 올린 최신 내용을 먼저 받아온다.

**작업 끝난 후:**
```bash
git add .
git commit -m "무슨 작업했는지 한 줄로"
git push
```
→ GitHub에 올려서 다른 기기가 받을 수 있게 한다.

**절대 하지 말 것:**
- pull 없이 바로 코드 작성 시작 (충돌 원인)
- 여러 파일 수정 후 한 번에 몰아서 커밋
- 커밋 메시지 없이 push
