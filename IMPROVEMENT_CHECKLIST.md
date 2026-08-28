# 개선 사항 체크리스트 (2026-08-29)

## ✅ 현재 상태
- Phase 5 Part 1-3: 거의 완료
- 자동매매 엔진: 작동 중
- Paper Trading: MVP 완성
- Streamlit Cloud: 배포 완료

---

## 🎯 우선순위별 개선사항

### 1️⃣ 즉시 (1주일)
- [ ] **API 키 만료 대비**: ANTHROPIC_API_KEY, GITHUB_TOKEN, SUPABASE_KEY 갱신 주기 설정
- [ ] **모니터링 추가**: auto_trader 실행 결과 로깅 (매일 자동 매매 결과 기록)
- [ ] **테스트 커버리지**: auto_trader.py 통합 테스트 작성 (현재 unit test만 있음)
- [ ] **문서화**: 현재 실행 중인 자동매매 규칙 명확화 (deployment_pacing.py 규칙 문서화)

### 2️⃣ 단기 (2주일)
- [ ] **리스크 관리 고도화**
  - Stop Loss 자동 설정 (ATR 기반)
  - Daily Loss Limit 확인
  - Maximum Drawdown 추적
  
- [ ] **백테스트 통합**
  - 현재 AI 신호의 성과를 과거 데이터로 검증
  - Sharpe Ratio / Sortino Ratio 계산
  - Win Rate 분석

- [ ] **대시보드 고도화**
  - 자동매매 상태 실시간 모니터링
  - 거래 기록 필터링/정렬
  - 위험도 지표 시각화

### 3️⃣ 중기 (1개월)
- [ ] **다중 AI 지원 (Phase 7)**
  - GPT Analyzer 추가
  - Gemini Analyzer 추가
  - 로컬 LLM 지원
  
- [ ] **실시간 모니터링 (Phase 8)**
  - WebSocket 기반 실시간 신호
  - Slack/Email 알림
  - Dashboard 실시간 업데이트

- [ ] **Cloud Deployment 고도화 (Phase 9)**
  - AWS Lambda로 자동매매 이관 (GitHub Actions 대체)
  - CloudWatch 모니터링
  - Auto Scaling 설정

### 4️⃣ 장기 (2-3개월)
- [ ] **실거래 준비 (Phase 5 → 실거래 전환)**
  - 실제 브로커 API 연동 (업비트, 영웅문 등)
  - 주문 검증 및 재시도 로직
  - 거래세 / 슬리피지 계산

- [ ] **포트폴리오 최적화**
  - Markowitz 포트폴리오 이론
  - 상관관계 분석
  - 자산 배분 자동화

---

## 🐛 발견된 버그/주의사항

### 보안
✅ **안전함**: `.gitignore`에 `.env` 포함 (파일 자체는 push 안 됨)
⚠️ **주의**: 로컬에서 API 키 관리 — 키 노출 시 즉시 Anthropic/GitHub/Supabase에서 재발급

### 성능
- [ ] Supabase 쿼리 최적화 (인덱스 추가)
- [ ] 캐싱 레이어 추가 (Redis 고려)
- [ ] 대량 거래 시 배치 처리

### 사용성
- [ ] 에러 메시지 친화적 번역
- [ ] 거래 실패 시 자동 재시도
- [ ] 네트워크 오류 복구 로직

---

## 📊 다음 Phase 제안

### Phase 5 최종 체크리스트
- [x] 멀티마켓 대시보드
- [x] 페이퍼 트레이딩 (Session 저장소)
- [x] 페이퍼 트레이딩 (Supabase 저장소)
- [x] 자동매매 엔진
- [x] 1개월 소진 페이싱
- [ ] 자동매매 모니터링 대시보드

### Phase 6 제안
- 대시보드 고도화 (실시간 업데이트, 차트, 통계)
- 성과 분석 (Backtest, Sharpe Ratio 등)
- 위험도 시각화

### Phase 7 제안
- 다중 AI 지원 (GPT, Gemini, 로컬 LLM)
- AI별 성과 비교
- AI 투표 기반 신호 생성

---

## 📝 커밋 메시지 템플릿

```
[Phase5][Part4] 자동매매 모니터링 및 개선사항 적용

- IMPROVE: API 키 만료 알림 추가
- FEATURE: auto_trader 로깅 강화
- TEST: auto_trader 통합 테스트 작성
- DOCS: deployment_pacing 규칙 문서화
```

---

**마지막 수정**: 2026-08-29
**상태**: Phase 5 거의 완료, Phase 6 준비 단계
