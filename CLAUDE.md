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

- **Phase 5 Part 3 (포트폴리오 영구 저장 + AI 자동매매 엔진): 코드 완료, Supabase 프로젝트 생성만 대기 중** (2026-08-04)
  - ✅ **포트폴리오 영구 저장 (Repository Pattern)** — `src/portfolio/base_repository.py`(인터페이스),
    `session_repository.py`(세션 폴백, 기존 동작과 동일), `supabase_repository.py`(Supabase 영구 저장),
    `repository_factory.py`(SUPABASE_URL/KEY 설정+연결 성공 시 자동으로 Supabase 사용, 그 외에는
    안전하게 세션으로 폴백). `session_portfolio.py`의 `buy()`/`sell()`/`init_portfolio()` 시그니처는
    그대로 유지했고 내부에서만 저장소를 호출하도록 바꿔서, Streamlit UI 코드는 전혀 수정하지 않았다.
  - ✅ `scripts/init_db.sql`에 `wallets`/`wallet_holdings`/`wallet_trades` 테이블 추가
    (기존 `portfolio`/`orders` 테이블은 symbols 사전 등록 FK가 필요해 자유 검색 심볼과 안 맞아서
    건드리지 않고 그대로 둠 — 새 테이블은 symbol을 문자열로 직접 저장).
  - ✅ **AI 자동 트레이딩 엔진** (`src/trading/auto_trader.py`, 신규) — `AutoTrader` 클래스가
    감시 종목(`DEFAULT_WATCHLIST`: 삼성전자/SK하이닉스/AAPL/TSLA/BTC/ETH)을 순회하며 Claude 분석 →
    신뢰도/위험도 규칙(`TradingConfig`) 통과 시 `session_portfolio.buy()/sell()`을 그대로 재사용해
    자동 체결한다. `python -m src.trading.auto_trader`로 단독 실행 가능.
  - ✅ **스케줄러** — `.github/workflows/auto_trade.yml` (GitHub Actions, 매일 00:30 UTC = 한국시간
    09:30 cron + 수동 실행 버튼). **단, GitHub 저장소 Settings → Secrets에 `ANTHROPIC_API_KEY`/
    `SUPABASE_URL`/`SUPABASE_KEY`를 등록해야 실제로 동작함 (사용자 액션 필요, 아래 참고).**
  - ✅ pytest 36개 신규 테스트 전부 통과 (`test_portfolio_repository.py`, `test_session_portfolio.py`,
    `test_auto_trader.py` — 정상/실패/엣지 케이스 + 저장소 폴백 시나리오 포함).
  - ⚠️ **아직 Supabase 프로젝트가 실제로 없어서(SUPABASE_URL/KEY 미설정), 지금 배포된 앱은 여전히
    세션 저장소로 자동 폴백 중 — 위 기능들은 "키만 넣으면 바로 동작"하는 상태이지 아직 실사용 중은 아님.**

### 다음 할 일 (Phase 5 Part 3 마무리 — 사용자 액션만 남음)

사용자 목표: **Claude가 직접 한국주식/미국주식/암호화폐에 각 100만원(총 300만원) 가상 투자금으로
1~2개월간 매일 자동으로 페이퍼 트레이딩을 하고, 그 결과를 실시간 대시보드에서 지켜보는 것.**
코드(영구 저장 + 자동매매 엔진 + 스케줄러)는 다 준비됐고, 남은 건 아래 사용자 액션 2가지뿐이다.

남은 작업 우선순위:
1. **Supabase 프로젝트 실제 생성** (사용자가 https://supabase.com 에서 무료 프로젝트 생성 →
   `scripts/init_db.sql` 실행 → URL/anon key를 Streamlit Cloud Secrets에 추가 — Claude가 대신 못 함)
2. **GitHub Actions Secrets 등록** (저장소 Settings → Secrets and variables → Actions에
   `ANTHROPIC_API_KEY`/`SUPABASE_URL`/`SUPABASE_KEY` 등록 — 이것도 사용자만 할 수 있는 액션)
3. 위 2개가 끝나면 GitHub Actions가 매일 자동으로 `auto_trader`를 실행하며 실제로 1~2개월
   자동 운영이 시작된다 (코드 추가 작업 없이 바로 시작 가능).

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
