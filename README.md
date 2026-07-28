# INVEST AI

Binance 시세 데이터를 수집하고 AI로 분석하여 투자 신호(BUY/SELL/HOLD)를 생성하는 투자 보조 플랫폼. 이후 자동매매까지 확장 가능한 구조로 설계한다.

## 프로젝트 구조

```
src/
 ├── fetcher/        # 거래소 데이터 수집기 (Binance)
 ├── engine/         # 기술적 지표 계산 + AI 분석 엔진 (Claude API)
 ├── common/         # 공통 유틸 (재시도 로직 등)
 └── dashboard.py    # Streamlit 대시보드 (실 사용 화면)

tests/               # pytest 테스트
config/              # 설정값 (심볼, 인터벌, 경로 등)
data/                # 수집된 OHLCV 데이터 (CSV)
```

## 현재 진행 상황

- **Phase 1** — 프로젝트 스캐폴딩: 완료
- **Phase 2 Part 1** — Binance OHLCV 데이터 수집기: 완료
- **Phase 3** — AI 분석 엔진 (Claude API 기반 BUY/SELL/HOLD + Confidence Score + Reason + Risk Score): 완료
- **Phase 4 MVP** — Streamlit 대시보드: 완료
- **Phase 5** — 자동매매 확장: 예정

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 등 API 키 입력
```

## 실행 (대시보드)

```bash
streamlit run src/dashboard.py
```

Binance 데이터 수집 → 기술적 지표 계산 → Claude AI 분석(BUY/SELL/HOLD + 확신도 + 근거 + 리스크 점수)까지
한 화면에서 확인할 수 있다. AI 분석을 쓰려면 `.env`에 `ANTHROPIC_API_KEY`가 있어야 한다.

## 테스트

```bash
pytest tests/ -v
```
