# 🤖 Claude Code 규칙 (CLAUDE.md)

이 파일은 Claude Code에서 코드를 수정할 때 지켜야 할 규칙들을 정의합니다.

## 📋 기본 원칙

### 1. 한 번에 한 파일만 수정
- src/fetcher/binance.py 수정 → 완료
- src/engine/analyzer.py 수정 → 완료
- 동시에 여러 파일 수정하지 말기

### 2. 함수 단위로 작업
큰 파일 전체를 한 번에 요청하지 말고, 필요한 함수만 요청하기

### 3. 매 수정 후 Git 커밋
```bash
git add .
git commit -m "[Phase2] binance.py get_klines() 함수 작성"
git push
```

## 📁 프로젝트 구조 (참고용)

```
invest-ai/
├─ src/
│  ├─ fetcher/binance.py      # Part 1: 데이터 수집
│  ├─ engine/analyzer.py      # Part 2: 분석
│  ├─ engine/trader.py        # Part 3: 신호
│  └─ dashboard.py            # Part 4: 웹
├─ tests/
├─ data/
└─ config/
```

## ⚠️ 주의사항

1. API 키는 절대 코드에 직접 입력하지 말기
```python
# 나쁜 예:
BINANCE_KEY = "abc123..."

# 좋은 예:
BINANCE_KEY = os.getenv("BINANCE_API_KEY")
```

2. 민감한 정보는 .env 파일에 (GitHub에 올라가지 않음)

3. commit 메시지는 명확하게
```bash
❌ git commit -m "fix bugs"
✅ git commit -m "[Phase2] Binance API get_klines() 완성"
```

## 📝 각 Phase별 규칙

### Phase 2 (Part 1: 데이터 수집)
- 파일: src/fetcher/binance.py
- Commit: "[Phase2] [Part1] Binance 데이터 수집 함수"

### Phase 3 (Part 2-3: 분석 & 신호)
- 파일: src/engine/analyzer.py, src/engine/trader.py
- Commit: "[Phase3] [Part2] Claude 분석 엔진"

### Phase 4 (Part 4: 대시보드)
- 파일: src/dashboard.py
- Commit: "[Phase4] [Part4] Flask 대시보드"

## ✅ 수정 후 체크리스트

- [ ] 코드가 실행되는가?
- [ ] 테스트를 통과하는가?
- [ ] 주석이 충분한가?
- [ ] API 키는 .env에서 읽는가?
- [ ] 커밋 메시지는 명확한가?

---

이 규칙을 따르면 MacBook에서 개발할 때 매우 효율적으로 진행됩니다! 🚀
