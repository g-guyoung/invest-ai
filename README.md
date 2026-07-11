# 💰 투자 AI 프로젝트

## 📌 프로젝트 개요

손해를 관리하면서 수익을 목표로 하는 자동매매 시스템입니다.

핵심 아이디어:
- Binance에서 실시간 가격 데이터 수집
- Claude AI가 시장을 분석
- 매수/매도 신호 자동 생성
- 웹 대시보드에서 실시간 모니터링

## 🎯 목표

- Phase 1 (7월): 설계 & 기초 구축
- Phase 2 (8월): 모듈별 개발
- Phase 3 (9월): 프로토타입 완성 & 배포

## 🔧 기술 스택

- 언어: Python 3.11+
- 웹 프레임워크: Flask
- 시장 데이터: Binance API
- AI 분석: Claude API
- 데이터 저장: PostgreSQL
- 버전관리: Git + GitHub

## 📁 프로젝트 구조

invest-ai/
├─ src/
│  ├─ fetcher/
│  │  ├─ binance.py
│  │  └─ __init__.py
│  ├─ engine/
│  │  ├─ analyzer.py
│  │  ├─ trader.py
│  │  └─ __init__.py
│  └─ dashboard.py
├─ tests/
│  ├─ test_binance.py
│  └─ test_analyzer.py
├─ data/
│  ├─ raw/
│  └─ processed/
├─ config/
│  ├─ settings.py
│  └─ .env.example
├─ README.md
├─ requirements.txt
├─ CLAUDE.md
└─ .gitignore

## ⚙️ 시스템 구조 (5개 Part)

### 1. 데이터 수집 (fetcher)
Binance API → BTC-USDT 데이터 → CSV 저장

### 2. AI 분석 (engine/analyzer)
데이터 → Claude AI → 시장 분석

### 3. 신호 생성 (engine/trader)
Claude 분석 → 매수/매도 신호 생성

### 4. 웹 대시보드 (dashboard)
Flask → 실시간 신호 표시 → 그래프

### 5. 자동화 (Cron job)
매일 09:00, 15:00 자동 실행

## 📊 진행 상황

- [x] 아키텍처 설계
- [x] GitHub 저장소 생성
- [ ] Part 1: Binance 데이터 수집기
- [ ] Part 2: Claude 분석 엔진
- [ ] Part 3: 신호 생성 로직
- [ ] Part 4: Flask 대시보드
- [ ] Part 5: 자동화 시스템
- [ ] 최종 테스트 & 배포

## 👨‍💻 개발자

- 이름: 춘식 (규영)
- 목표: 손실 관리형 수익화 자동매매 시스템 구축
- 기간: 2026년 7월 ~ 9월

## 📝 라이선스

MIT License

---

마지막 업데이트: 2026년 7월 11일
