# 🚀 Streamlit Cloud 배포 가이드

**목표**: 클라우드에 배포해서 핸드폰에서 접근 가능하게 만들기

---

## 📋 **Step 1: 로컬에서 준비**

### 1.1 로컬 secrets.toml 생성 (테스트용)

```bash
cd C:\Users\us\Desktop\INVEST AI - 1
```

`.streamlit/secrets.toml` 파일 생성:

```toml
# Supabase
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-public-key"

# Anthropic
ANTHROPIC_API_KEY = "sk-ant-api03-..."

# 투자 규모
INITIAL_BALANCE_KR = 1000000
INITIAL_BALANCE_US = 1000000
INITIAL_BALANCE_CRYPTO = 1000000
```

### 1.2 로컬에서 테스트

```bash
streamlit run src/ui/streamlit_app.py
```

**확인사항:**
- [ ] 브라우저에서 `http://localhost:8501` 접근 가능
- [ ] 심볼 선택 후 데이터 로드 가능
- [ ] 가격 차트 표시됨

---

## 🔐 **Step 2: GitHub에 푸시 (secrets 제외)**

### 2.1 .gitignore 확인

```bash
cat .gitignore
```

다음이 포함되어 있는지 확인:
```
.env
.streamlit/secrets.toml
*.pyc
__pycache__/
.DS_Store
data/
```

없으면 추가:
```bash
echo ".streamlit/secrets.toml" >> .gitignore
```

### 2.2 Git 커밋 & 푸시

```bash
git add -A
git commit -m "[Phase5][Part2] Streamlit Cloud 배포 설정"
git push origin main
```

**확인**: GitHub에서 최신 코드가 올라와 있는지 확인

---

## ☁️ **Step 3: Streamlit Cloud에 배포**

### 3.1 Streamlit Cloud 계정 생성

1. https://streamlit.io/cloud 접속
2. "Sign up" 클릭
3. GitHub로 로그인
4. `g-guyoung/invest-ai` 저장소 선택

### 3.2 앱 배포

1. **Create app** 클릭
2. 다음 정보 입력:
   ```
   Repository: g-guyoung/invest-ai
   Branch: main
   File path: src/ui/streamlit_app.py
   ```
3. **Deploy** 클릭

### 3.3 배포 완료

배포 완료 후:
```
Your app is live at:
https://invest-ai-[hash].streamlit.app
```

---

## 🔑 **Step 4: Streamlit Cloud에서 Secrets 설정**

1. 배포된 앱에서 우측 상단 **⋯ (More)** → **Settings**
2. **Secrets** 탭 클릭
3. 다음 정보 입력:

```toml
# Supabase
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-public-key"

# Anthropic
ANTHROPIC_API_KEY = "sk-ant-api03-..."

# 투자 규모
INITIAL_BALANCE_KR = 1000000
INITIAL_BALANCE_US = 1000000
INITIAL_BALANCE_CRYPTO = 1000000
```

4. **Save** 클릭
5. 앱이 자동으로 재배포됨

---

## 📱 **Step 5: 핸드폰에서 접근**

### 5.1 URL 접근

```
https://invest-ai-[hash].streamlit.app
```

### 5.2 설정

- 좌측 상단 **☰** → **Settings** → **Wide mode** 활성화 (옵션)
- 우측 상단 **⋯** → **Run on save** 확인

---

## ✅ **배포 체크리스트**

- [ ] 로컬에서 테스트 완료
- [ ] GitHub에 코드 푸시
- [ ] Streamlit Cloud 계정 생성
- [ ] 앱 배포
- [ ] Secrets 설정
- [ ] 핸드폰에서 접근 확인
- [ ] 심볼 선택 후 차트 표시 확인

---

## 🚨 **문제 해결**

### 배포 실패

```
ModuleNotFoundError: No module named 'supabase'
```

**해결**: `requirements.txt`에 `supabase>=2.0.0` 있는지 확인

```bash
grep supabase requirements.txt
```

### Secrets 에러

```
SupabaseError: SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해주세요.
```

**해결**: Streamlit Cloud의 Secrets 설정 재확인

### 느린 속도

- Streamlit Cloud 무료 Tier는 느림 (조건: 앱 비활성 30분 후 sleep)
- 유료로 업그레이드하면 빨라짐

---

## 🔄 **자동 배포 (GitHub → Streamlit Cloud)**

GitHub에 `main` 브랜치에 푸시하면 자동으로 Streamlit Cloud에 배포됨

```bash
git push origin main  # 자동 배포 시작!
```

---

## 📊 **다음 단계**

배포 완료 후:

1. **AI 자동 트레이딩 엔진** 구현
2. **스케줄러** 설정 (매일 자동 실행)
3. **포트폴리오 트래킹** 추가
4. **1-2개월 자동 운영** 시작

---

**작성일**: 2026-08-01  
**상태**: Phase 5-2-1 배포 가이드
