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
 ├── fetcher/     # 거래소 데이터 수집기 (binance_fetcher.py)
 ├── engine/      # AI 분석 엔진 (indicators.py, base_analyzer.py, claude_analyzer.py)
 ├── common/      # 공통 유틸 (retry.py 등, 여러 모듈이 공유하는 로직)
 └── dashboard.py # Streamlit 대시보드 (실 사용 화면)
tests/
config/
data/
README.md
requirements.txt
CLAUDE.md
```

새 파일도 이 구조를 유지한다.

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

## 6. 현재 진행 상황

- Phase 1 (스캐폴딩): 완료
- Phase 2 Part 1 (Binance OHLCV 수집기 `src/fetcher/binance_fetcher.py` + 테스트): 완료
- Phase 3 (AI 분석 엔진): 완료
  - `src/engine/indicators.py` — RSI/MACD/이동평균/볼린저밴드/스토캐스틱/OBV/ATR 등 기술적 지표
  - `src/engine/base_analyzer.py` — BaseAnalyzer 인터페이스 + AnalysisResult(Pydantic) 스키마 (Multi AI 확장 대비)
  - `src/engine/claude_analyzer.py` — ClaudeAnalyzer (Claude API 기반 BUY/SELL/HOLD + Confidence + Reason + Risk Score)
  - `src/common/retry.py` — 재시도 로직 공통화 (fetcher/analyzer 공유, DRY)
  - 테스트 22개 전체 통과 (fetcher 8 + indicators 6 + analyzer 8)
- Phase 4 MVP (대시보드): 완료 — `src/dashboard.py` (Streamlit), `streamlit run src/dashboard.py`로 실행
- Phase 5 (자동매매 확장): 예정
- Phase 6 (대시보드 고도화)/Phase 7(Multi AI)/Phase 8(모니터링)/Phase 9(배포)/Phase 10(운영): 예정

### 실행 전 확인 사항
- `.env`의 `ANTHROPIC_API_KEY` 설정 완료 (2026-07-29, 만료 없음(Never)으로 발급).
- 샌드박스 환경은 외부 네트워크(Binance API, Anthropic API)가 막혀 있어 실제 데이터/실제 API 호출 검증은
  로컬 PC에서만 가능. 코드 자체는 mock 기반 pytest로 전량 검증됨.

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
