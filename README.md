💰 투자 AI 프로젝트 (invest-ai)

📌 프로젝트 개요

손실을 관리하면서 수익을 목표로 하는 AI 투자 분석 및 자동매매 플랫폼입니다.

핵심 아이디어:

	•	Binance(암호화폐), Yahoo Finance(주식)에서 시장 데이터 수집
	•	기술적 지표 계산 + Claude AI가 시장 분석
	•	BUY / SELL / HOLD 신호 생성 (signal, confidence, reason, risk_score)
	•	웹 대시보드에서 모니터링
	•	최종 목표: 모의투자 → 실전 자동매매

🔧 기술 스택

	•	언어: Python 3.11+
	•	대시보드: Streamlit (현재), Flask (계획)
	•	시장 데이터: Binance API, Yahoo Finance(yfinance), Alpha Vantage(일부)
	•	AI 분석: Claude API (Anthropic)
	•	데이터 저장: CSV/Parquet (현재), PostgreSQL + SQLAlchemy (계획)
	•	버전관리: Git + GitHub

📁 현재 프로젝트 구조

invest-ai/
├─ src/
│  ├─ fetcher/
│  │  ├─ base_fetcher.py          # 수집기 추상 인터페이스
│  │  ├─ binance_fetcher.py       # 암호화폐 데이터
│  │  ├─ yahoo_fetcher.py         # 미국/한국/해외 주식, 지수
│  │  ├─ alpha_vantage.py         # 미국 시장 확장 (통합 확인 필요)
│  │  └─ data_source_registry.py  # 심볼 → 데이터 소스 자동 매핑
│  ├─ engine/
│  │  ├─ base_analyzer.py         # 분석기 추상 인터페이스
│  │  ├─ claude_analyzer.py       # Claude 기반 신호 생성
│  │  └─ indicators.py            # 기술적 지표 15개 이상
│  └─ dashboard.py                # Streamlit 대시보드
├─ tests/
├─ data/
├─ config/
├─ README.md
├─ requirements.txt
├─ CLAUDE.md
└─ .gitignore

📊 진행 상황 (2026-11-03 기준)

완료

	☑︎	아키텍처 설계, GitHub 저장소 생성
	☑︎	데이터 수집: Binance / Yahoo Finance / 레지스트리
	☑︎	기술적 지표 계산 (indicators.py)
	☑︎	Claude 분석 엔진 (BUY/SELL/HOLD)
	☑︎	Streamlit 대시보드

알려진 이슈

	☐︎	dashboard.py: ClaudeAnalyzer를 base_analyzer에서 import하는 버그
	•	수정: from src.engine.base_analyzer import AnalyzerError, Signal
	•	수정: from src.engine.claude_analyzer import ClaudeAnalyzer
	☐︎	Alpha Vantage 수집기 통합 여부 확인

다음 단계

	☐︎	대시보드 import 버그 수정
	☐︎	백테스트
	☐︎	모의투자(Paper Trading)
	☐︎	PostgreSQL 연동
	☐︎	스케줄 자동 실행 (cron)
	☐︎	실전 비트코인 봇 (소액으로 시작)

🖥️ 실행 환경 계획

	1.	현재: 데스크탑 PC에서 실행 (무료, 가장 빠르게 검증 가능)
	2.	이후: 클라우드 VPS로 이동 → 24시간 실행, 폰은 대시보드·알림 확인용
	3.	코드는 동일하게 유지, 설정은 .env로만 분리

🔐 보안 원칙

	•	API 키는 코드에 직접 쓰지 않고 .env에서만 읽기
	•	.env는 .gitignore로 GitHub에 올리지 않기
	•	실전 매매 전에는 반드시 모의투자로 검증

👨‍💻 개발자

	•	이름: 춘식 (규영)
	•	목표: 손실 관리형 수익화 자동매매 시스템 구축

📝 라이선스

MIT License