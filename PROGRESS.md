# 📊 投资 AI 프로젝트 - 진행상황 (PROGRESS.md)

**작성일:** 2026년 7월 29일 (데스크탑에서 정리)

---

## 🎯 현재 상태

| 항목 | 상태 |
|---|---|
| **프로젝트 위상** | Phase 1 (기초 구축) |
| **코드 작성** | 0% (아직 시작 안 함) |
| **설계 완료** | 100% ✅ |
| **문서화** | 80% ✅ |
| **Git 동기화** | 완벽 ✅ (맥 ↔ 데스크탑) |

---

## ✅ 데스크탑에서 완료한 작업 (2026.07.28 ~ 07.29)

### 1. 저장소 구축
- [x] GitHub 저장소 생성: `https://github.com/g-guyoung/invest-ai`
- [x] 초기 클론 (맥 + 데스크탑)
- [x] Git 인증 설정 (맥: Keychain, 데스크탑: 토큰)

### 2. 프로젝트 구조 정의
```
invest-ai/
├─ src/
│  ├─ fetcher/binance.py
│  ├─ engine/analyzer.py
│  ├─ engine/trader.py
│  └─ dashboard.py
├─ tests/
├─ data/
├─ config/
├─ README.md ✅
├─ requirements.txt ✅
├─ CLAUDE.md ✅
├─ .gitignore ✅
└─ LICENSE ✅
```

### 3. 핵심 파일 작성

#### 📄 **README.md**
- 프로젝트 개요 및 목표
- 5가지 시스템 구조 (데이터 수집 → 분석 → 신호 → 대시보드 → 자동화)
- 기술 스택 정의
- 진행상황 체크리스트

#### 📄 **requirements.txt**
- Python 3.11+ 의존성 정의
- 핵심 라이브러리:
  - `python-binance==1.0.17` (Binance API)
  - `anthropic==0.7.0` (Claude AI)
  - `Flask==3.0.0` (웹 대시보드)
  - `SQLAlchemy==2.0.0` (DB ORM)
  - `pytest==7.4.0` (테스트)

#### 📄 **CLAUDE.md** (가장 중요)
- **AI CTO 역할 정의**: 코드 생성기 아님, 건축가
- **개발 프로세스 10단계**:
  1. 요구사항 정의
  2. 구조 설계
  3. 데이터 설계
  4. 핵심 로직(MVP)
  5. 리팩토링
  6. 테스트 작성
  7. 코드 리뷰
  8. 문서화
  9. 성능 최적화
  10. 다음 단계 제안

- **설계 원칙**: SOLID, DRY, KISS, YAGNI, Clean Architecture
- **Python 규칙**: Type Hint, Dataclass, Pydantic, Logging, Async
- **예외 처리**: Retry, Backoff, Timeout, Circuit Breaker
- **보안**: API 키는 .env에서만
- **Git 규칙**: `[PhaseN][PartN] description` 형식

#### 📄 **.gitignore**
- Python 바이트 컴파일 파일 무시
- 가상환경 무시 (.venv, venv, env)
- 환경 변수 파일 무시 (.env, .env.local)
- 민감정보 무시 (.env, API 키 등)
- IDE 설정 무시 (.vscode, .idea)
- 테스트/캐시 무시 (.pytest_cache, .mypy_cache)

#### 📄 **LICENSE**
- MIT License (저작권: g-guyoung, 2026)

### 4. Git 동기화 규칙 추가 (맥에서 추가 후 데스크탑에서 pull 완료)
```bash
# 맥에서 추가:
git add .
git commit -m "[Setup] Git 동기화 규칙 추가"
git push origin main

# 데스크탑에서 확인:
git pull origin main
# → "Already up to date" ✅
type CLAUDE.md  # 완전히 반영됨 확인
```

---

## 🔄 Git 동기화 상태

### 맥과 데스크탑 연동 확인

| 장치 | 저장소 | 상태 |
|---|---|---|
| **Mac** | `~/...invest-ai` | Clone 완료 ✅ |
| **Desktop** | 현재 디렉토리 | Clone 완료 ✅ |
| **GitHub** | https://github.com/g-guyoung/invest-ai | 모든 파일 동기화 ✅ |

### Commit 히스토리
```
Latest: [Setup] Git 동기화 규칙 추가 (맥에서)
Previous: [Setup] 초기 프로젝트 구조 및 파일 (데스크탑에서)
```

---

## 📋 AI CTO 역할 정의

### 11가지 역할
1. AI CTO
2. Senior Python Architect
3. Senior Quant Developer
4. Machine Learning Engineer
5. AI Research Engineer
6. Backend Engineer
7. Data Engineer
8. DevOps Engineer
9. Security Engineer
10. QA Engineer
11. Code Reviewer
12. Technical Writer

**핵심 철학:**
- "동작하는 코드" 아님
- **"운영 가능한 코드"** 우선
- Production Ready 기준

---

## 🏗️ 아키텍처 설계 (완료)

### Phase 별 계획

#### **Phase 1 (현재): 기초 구축**
- [x] 설계 완료
- [ ] Part 1: Binance 데이터 수집기
- [ ] Part 2: Claude 분석 엔진
- [ ] Part 3: 신호 생성 로직

#### **Phase 2: 모듈별 개발**
- 고급 분석 기능
- 백테스트 엔진

#### **Phase 3: 프로토타입 완성**
- 웹 대시보드 (Flask)
- 배포 준비

#### **Phase 4-10: 확장 및 운영**
- Paper Trading
- 실시간 모니터링
- Multi AI (Claude, OpenAI, Gemini, Local LLM)
- Cloud Deployment
- Production 운영

---

## 🚀 다음 단계 (즉시 시작)

### Phase 1 - Part 1: Binance 데이터 수집기

**목표**: Binance API에서 실시간 가격 데이터 수집 및 CSV 저장

#### ① 요구사항 분석
- 지원할 심볼: BTC-USDT, ETH-USDT, SOL-USDT 등
- 지원할 시간틀: 1m, 5m, 15m, 1h, 4h, 1d
- 데이터 저장: CSV/Parquet
- 결측치 처리: 자동 보간
- Validation: 시간 순서, null 체크

#### ② 파일 구조
```
src/
├─ fetcher/
│  ├─ __init__.py
│  ├─ binance.py        ← 작성 예정
│  ├─ base.py           ← BaseExchange 추상 클래스
│  └─ types.py          ← OHLCV Dataclass
├─ config/
│  └─ settings.py       ← 환경 설정
└─ core/
   └─ utils.py          ← 유틸리티 함수
```

#### ③ 핵심 기능
- `BinanceClient` 클래스
  - `get_klines()`: OHLCV 데이터 조회
  - `get_latest()`: 최신 데이터만
  - `save_csv()`: CSV 저장
  - Retry/Timeout 처리

#### ④ 데이터 구조
```python
@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_asset_volume: float
    trades: int
    symbol: str = "BTC-USDT"
```

#### ⑤ 테스트 전략
- Unit Test: API 응답 Mock
- Integration Test: 실제 Binance API 호출 (선택적)
- Edge Case: 결측치, 네트워크 오류

---

## 📝 커밋 규칙

### 형식
```
[PhaseN][PartN] 기능 설명
```

### 예시
```
[Phase1][Part1] Binance 데이터 수집기 초기 구현
[Phase1][Part1] get_klines() 함수 추가
[Phase1][Part1] CSV 저장 기능 완성
[Phase1][Part1] 단위 테스트 추가
```

### 날짜별 커밋 계획
- 2026-07-30: Part 1 설계 완료 + 핵심 로직
- 2026-07-31: Part 1 테스트 + 리팩토링
- 2026-08-01: Part 2 시작

---

## 🛠️ 기술 스택 (최종 확정)

### Backend
- Python 3.11+
- Flask (웹 프레임워크)
- SQLAlchemy (ORM)
- Pydantic (데이터 검증)

### Data
- Pandas (데이터 분석)
- NumPy (수치 계산)
- Binance API (시장 데이터)

### AI
- Anthropic Claude API (분석)
- 향후: OpenAI, Google Gemini, Local LLM

### Database
- PostgreSQL (운영)
- SQLite (개발/테스트)

### DevOps
- Git + GitHub
- Docker (배포)
- GitHub Actions (CI/CD)

### Testing
- Pytest (단위/통합 테스트)
- Mock (API 테스트)

---

## 📌 중요 노트

### 보안
1. **API 키는 절대 코드에 직접 입력하지 말 것**
   ```python
   # ❌ 나쁜 예
   API_KEY = "abc123..."
   
   # ✅ 좋은 예
   from dotenv import load_dotenv
   import os
   load_dotenv()
   API_KEY = os.getenv("BINANCE_API_KEY")
   ```

2. **.env 파일은 .gitignore에 포함**
   - GitHub에 올라가지 않음
   - 로컬 개발용만

### 코드 품질
1. 모든 함수에 Docstring 작성
2. Type Hint 필수
3. PEP8 준수 (Black)
4. Pytest 커버리지 80% 이상

### 커밋 빈도
- **매일**: 1~2개 커밋 (기능 단위)
- **주 1~2회**: 큰 기능 정리

---

## 📞 연락처 & 정보

- **개발자**: 춘식 (규영)
- **GitHub**: https://github.com/g-guyoung
- **이메일**: jaicobib@gmail.com (Notion)
- **기간**: 2026.07 ~ 2026.09
- **개발 환경**: MacBook Air M1
- **작업 시간**: 주말 개발 (토 14:30~18:00, 일 10:00~18:00)

---

## 🎓 학습 & 참고

### 이전 진행상황
1. **Notion 프로젝트 페이지**: 설계 문서 저장
2. **Notion 일일 추적**: 진행상황 추적 (date, phase, goal, progress, ...)
3. **커스텀 Mentor Skill**: Claude와 1:1 코칭 세션용
4. **프로젝트 설명 템플릿**: 9가지 상황별 소개말

---

## ✨ 최종 체크리스트

### 설정 완료 ✅
- [x] GitHub 저장소
- [x] 프로젝트 구조
- [x] 개발 규칙 (CLAUDE.md)
- [x] 의존성 정의 (requirements.txt)
- [x] Git 동기화 (맥 ↔ 데스크탑)
- [x] 문서화

### 준비 완료 ✅
- [x] AI CTO 역할 정의
- [x] 10단계 개발 프로세스
- [x] 아키텍처 설계
- [x] Phase 1 상세 계획

### 시작 준비됨 ✅
- [x] Part 1: Binance 데이터 수집기 설계 완료
- [ ] Part 1: 코드 작성 시작 (다음 단계)

---

**마지막 업데이트**: 2026년 7월 29일 23:45 (데스크탑)

**다음 단계**: [Phase1][Part1] Binance Fetcher 코드 작성 시작 🚀
