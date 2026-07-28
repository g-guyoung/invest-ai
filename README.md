# INVEST AI

Binance 시세 데이터를 수집하고 AI로 분석하여 투자 신호(BUY/SELL/HOLD)를 생성하는 투자 보조 플랫폼. 이후 자동매매까지 확장 가능한 구조로 설계한다.

## 프로젝트 구조

```
src/
 ├── fetcher/        # 거래소 데이터 수집기 (Binance 등)
 ├── engine/         # AI 분석 엔진 (신호 생성)
 └── dashboard.py    # 대시보드 진입점

tests/               # pytest 테스트
config/              # 설정값 (심볼, 인터벌, 경로 등)
data/                # 수집된 OHLCV 데이터 (CSV)
```

## 현재 진행 상황

- **Phase 1** — 프로젝트 스캐폴딩: 완료
- **Phase 2 Part 1** — Binance OHLCV 데이터 수집기: 진행 중
- **Phase 3** — AI 분석 엔진 (Claude API 기반 BUY/SELL/HOLD + Confidence Score): 예정
- **Phase 4** — 대시보드: 예정
- **Phase 5** — 자동매매 확장: 예정

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env   # 필요 시 API 키 입력
```

## 테스트

```bash
pytest tests/ -v
```
