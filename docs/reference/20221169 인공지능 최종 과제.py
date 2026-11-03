# -*- coding: utf-8 -*-
"""
AI 기반 개인 맞춤형 투자 판단 보조 시스템
20221169 김규영
"""

import warnings, os, sys
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# 윈도우 터미널 한글 출력 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import platform

import yfinance as yf

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense, Dropout, BatchNormalization
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    from tensorflow.keras.utils import to_categorical
except ImportError:
    print("\n[오류] TensorFlow가 설치되어 있지 않습니다.")
    print("다음 명령어를 실행한 후 다시 실행하세요:")
    print("    python -m pip install tensorflow")
    sys.exit(1)

from sklearn.preprocessing import StandardScaler, label_binarize
from sklearn.feature_selection import SelectFromModel
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, confusion_matrix, ConfusionMatrixDisplay,
    roc_curve, auc
)

tf.random.set_seed(42)
np.random.seed(42)

if platform.system() == "Windows":
    plt.rcParams["font.family"] = "Malgun Gothic"
elif platform.system() == "Darwin":
    plt.rcParams["font.family"] = "AppleGothic"
else:
    plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

SAVE_DIR    = os.path.dirname(os.path.abspath(__file__))
LABEL_NAMES = ["매도(0)", "관망(1)", "매수(2)"]


# ── 유틸 ────────────────────────────────────────────────
def safe_float(prompt, default=None):
    while True:
        raw = input(prompt).strip()
        if raw == "" and default is not None:
            return default
        try:
            return float(raw)
        except ValueError:
            print("  숫자를 입력해주세요.")


def score_bar(score, width=20):
    filled = int(round(score * width))
    bar = "[" + "#" * filled + "-" * (width - filled) + "]"
    return f"{bar}  {score:.2f} / 1.00"


# ── 1. 사용자 입력 ───────────────────────────────────────
print("=" * 55)
print("  AI 기반 투자 판단 보조 시스템  |  20221169 김규영")
print("=" * 55)
TICKER = input("\n  종목 코드 입력 (예: 005930.KS / AAPL): ").strip()
print("\n  [재무지표 직접 입력 - 네이버금융/HTS에서 확인]")
per_raw = safe_float("  PER  : ", 15.0)
pbr_raw = safe_float("  PBR  : ", 1.5)
psr_raw = safe_float("  PSR  : ", 1.0)


# ── 2. 데이터 수집 ──────────────────────────────────────
print(f"\n  [{TICKER}] 데이터 수집 중...")
tk = yf.Ticker(TICKER)
df_raw = tk.history(start="2018-01-01", auto_adjust=True)
if df_raw.empty:
    print("  데이터 수집 실패. 종목 코드를 확인해주세요.")
    sys.exit(1)

df_raw = df_raw.reset_index()
df_raw.columns = [str(c) for c in df_raw.columns]
df_raw["Date"] = pd.to_datetime(df_raw["Date"]).dt.tz_localize(None)
df = df_raw[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
df = df.dropna().reset_index(drop=True)
name = tk.info.get("shortName", TICKER) if hasattr(tk, "info") else TICKER
print(f"  수집 완료: {len(df)}일치 ({df['Date'].iloc[0].date()} ~ {df['Date'].iloc[-1].date()})")


# ── 3. 투자 전략 점수 ────────────────────────────────────
B_SCORE = np.mean([per_raw < 15, pbr_raw < 1.5, pbr_raw > 0,
                   per_raw > 0,  psr_raw < 2.0])
L_SCORE = np.mean([per_raw < 20, psr_raw < 1.5])


# ── 4. 특징 생성 (21개) ──────────────────────────────────
def calc_rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / (l + 1e-9))

c = df["Close"]; v = df["Volume"]

df["RSI"]      = calc_rsi(c)
df["MACD"]     = c.ewm(span=12).mean() - c.ewm(span=26).mean()
df["Signal"]   = df["MACD"].ewm(span=9).mean()
df["MA5"]      = c.rolling(5).mean()
df["MA20"]     = c.rolling(20).mean()
df["MA60"]     = c.rolling(60).mean()
bb_std         = c.rolling(20).std()
df["BB_upper"] = df["MA20"] + 2 * bb_std
df["BB_lower"] = df["MA20"] - 2 * bb_std
df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / (df["MA20"] + 1e-9)
lo14           = df["Low"].rolling(14).min()
hi14           = df["High"].rolling(14).max()
df["Stoch"]    = 100 * (c - lo14) / (hi14 - lo14 + 1e-9)
df["OBV"]      = (v * np.sign(c.diff())).fillna(0).cumsum()
df["ATR"]      = (df["High"] - df["Low"]).rolling(14).mean()
df["MOM10"]    = c.pct_change(10)
df["VOL_MA"]   = v.rolling(20).mean()
df["VOL_ratio"]= v / (df["VOL_MA"] + 1e-9)
df["Trend"]    = (df["MA20"] - df["MA60"]) / (df["MA60"] + 1e-9)
df["PER_n"]    = np.clip(per_raw / 20, 0, 1)
df["PBR_n"]    = np.clip(pbr_raw / 3,  0, 1)
df["PSR_n"]    = np.clip(psr_raw / 2,  0, 1)
df["Buffett"]  = B_SCORE
df["Lynch"]    = L_SCORE

FEATURES = ["RSI","MACD","Signal","MA5","MA20","MA60",
            "BB_upper","BB_lower","BB_width","Stoch","OBV",
            "ATR","MOM10","VOL_ratio","Trend",
            "PER_n","PBR_n","PSR_n","Buffett","Lynch"]


# ── 5. 레이블 (변동성 기반 동적 임계값) ──────────────────
HORIZON = 5
df["future_ret"] = c.pct_change(HORIZON).shift(-HORIZON)
vol = c.pct_change().rolling(20).std() * (HORIZON ** 0.5)
thresh = vol * 0.5

df["label"] = 1
df.loc[df["future_ret"] >  thresh, "label"] = 2
df.loc[df["future_ret"] < -thresh, "label"] = 0

df_model = df.dropna(subset=FEATURES + ["label"]).reset_index(drop=True)
X = df_model[FEATURES].values
y = df_model["label"].values.astype(int)
print(f"  레이블 분포 — 매도:{(y==0).sum()}  관망:{(y==1).sum()}  매수:{(y==2).sum()}")


# ── 6. 학습/테스트 분할 + RF 특징 선택 ───────────────────
SPLIT_IDX = int(len(X) * 0.8)
X_train, X_test = X[:SPLIT_IDX], X[SPLIT_IDX:]
y_train, y_test = y[:SPLIT_IDX], y[SPLIT_IDX:]

print("\n  [RandomForest 특징 선택 중...]")
rf_sel = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
rf_sel.fit(X_train, y_train)
selector = SelectFromModel(rf_sel, prefit=True)
X_train_s = selector.transform(X_train)
X_test_s  = selector.transform(X_test)
selected_features = [FEATURES[i] for i, m in enumerate(selector.get_support()) if m]
n_features = len(selected_features)
print(f"  선택된 피처: {n_features}개 / {len(FEATURES)}개  →  {selected_features}")

scaler = StandardScaler()
X_train_sc = scaler.fit_transform(X_train_s)
X_test_sc  = scaler.transform(X_test_s)


# ── 7. TensorFlow 신경망 학습 ─────────────────────────────
print("\n  [TensorFlow 신경망 학습 중...]")
n_in = X_train_sc.shape[1]

model = Sequential([
    Dense(128, activation="relu", input_shape=(n_in,)),
    BatchNormalization(), Dropout(0.3),
    Dense(64,  activation="relu"),
    BatchNormalization(), Dropout(0.3),
    Dense(32,  activation="relu"), Dropout(0.2),
    Dense(3,   activation="softmax"),
])
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)
callbacks = [
    EarlyStopping(patience=15, restore_best_weights=True, verbose=0),
    ReduceLROnPlateau(factor=0.5, patience=8, verbose=0),
]
history = model.fit(
    X_train_sc, to_categorical(y_train, 3),
    validation_split=0.15,
    epochs=200, batch_size=32,
    callbacks=callbacks, verbose=0
)
print(f"  학습 완료 — 에포크: {len(history.history['loss'])}회")


# ── 8. 평가 ─────────────────────────────────────────────
y_prob = model.predict(X_test_sc, verbose=0)
y_pred = np.argmax(y_prob, axis=1)
acc    = accuracy_score(y_test, y_pred)
print(f"  테스트 정확도: {acc:.4f}  (랜덤 기준: 0.3333)")


# ── 9. 결과 그래프 저장 ──────────────────────────────────
img_path = os.path.join(SAVE_DIR, f"ml_result_{TICKER.replace('.','_')}.png")

fig = plt.figure(figsize=(18, 14))
gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.42, wspace=0.32)

NAVY = "#2c3e50"; BLUE = "#3a6ea5"; ORANGE = "#e67e22"
GREEN = "#27ae60"; RED = "#e74c3c"; GRAY = "#95a5a6"

# (A) 혼동행렬
ax1 = fig.add_subplot(gs[0, 0])
cm  = confusion_matrix(y_test, y_pred)
disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=LABEL_NAMES)
disp.plot(ax=ax1, colorbar=True, cmap="Blues")
ax1.set_title("(A) 혼동행렬 (Confusion Matrix)", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax1.set_xlabel("예측 레이블", fontsize=11); ax1.set_ylabel("실제 레이블", fontsize=11)

# (B) 특징 중요도
ax2  = fig.add_subplot(gs[0, 1])
imp  = rf_sel.feature_importances_[selector.get_support()]
idx  = np.argsort(imp)
cols = [RED if i == idx[-1] else BLUE for i in range(len(idx))]
ax2.barh([selected_features[i] for i in idx], imp[idx],
         color=[cols[i] for i in idx], edgecolor="white", height=0.7)
ax2.set_xlabel("Feature Importance", fontsize=11)
ax2.set_title("(B) 특징 중요도 (RandomForest 기준)", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax2.grid(True, axis="x", alpha=0.3)
for bar, val in zip(ax2.patches, imp[idx]):
    ax2.text(val + 0.001, bar.get_y() + bar.get_height()/2,
             f"{val:.3f}", va="center", fontsize=9, color=NAVY)

# (C) ROC 곡선
ax3 = fig.add_subplot(gs[1, 0])
y_bin = label_binarize(y_test, classes=[0, 1, 2])
for i, (col, nm) in enumerate(zip([RED, ORANGE, GREEN], LABEL_NAMES)):
    fpr, tpr, _ = roc_curve(y_bin[:, i], y_prob[:, i])
    a = auc(fpr, tpr)
    ax3.plot(fpr, tpr, color=col, lw=2, label=f"{nm}  AUC={a:.3f}")
ax3.plot([0,1],[0,1], color=GRAY, linestyle="--", lw=1)
ax3.set_xlabel("False Positive Rate", fontsize=11)
ax3.set_ylabel("True Positive Rate", fontsize=11)
ax3.set_title("(C) ROC 곡선 (클래스별)", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax3.legend(fontsize=10); ax3.grid(True, alpha=0.3)

# (D) 손실 그래프
ax4 = fig.add_subplot(gs[1, 1])
ax4.plot(history.history["loss"],     color=BLUE,   lw=2, label="학습 손실")
ax4.plot(history.history["val_loss"], color=ORANGE, lw=2, linestyle="--", label="검증 손실")
ax4.set_xlabel("에포크", fontsize=11); ax4.set_ylabel("손실", fontsize=11)
ax4.set_title("(D) 손실 그래프 (에포크별)", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax4.legend(fontsize=10); ax4.grid(True, alpha=0.3)

# (E) 정확도 그래프
ax5 = fig.add_subplot(gs[2, 0])
ax5.plot(history.history["accuracy"],     color=BLUE,   lw=2, label="학습 정확도")
ax5.plot(history.history["val_accuracy"], color=ORANGE, lw=2, linestyle="--", label="검증 정확도")
ax5.axhline(y=1/3, color=GRAY, linestyle=":", lw=1.5, label="랜덤 기준 (33%)")
ax5.set_xlabel("에포크", fontsize=11); ax5.set_ylabel("정확도", fontsize=11)
ax5.set_title("(E) 정확도 그래프 (에포크별)", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax5.legend(fontsize=10); ax5.grid(True, alpha=0.3); ax5.set_ylim(0, 1)

# (F) 예측 신호 시각화
ax6 = fig.add_subplot(gs[2, 1])
te_dates = df_model["Date"].iloc[SPLIT_IDX:].values
te_close = df_model["Close"].iloc[SPLIT_IDX:].values
ax6.plot(te_dates, te_close, color=GRAY, lw=1.2, label="종가", zorder=1)
for cls, mk, col, nm in [(2,"^",GREEN,"매수"),(1,"o",ORANGE,"관망"),(0,"v",RED,"매도")]:
    mask = y_pred == cls
    ax6.scatter(te_dates[mask], te_close[mask], marker=mk, c=col,
                s=25, zorder=2, label=f"예측:{nm}", alpha=0.85)
ax6.set_title(f"(F) 검증 구간 예측 신호  ({TICKER})", fontsize=13, fontweight="bold", color=NAVY, pad=10)
ax6.set_xlabel("날짜", fontsize=11); ax6.set_ylabel("종가", fontsize=11)
ax6.legend(loc="upper left", fontsize=9)
ax6.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f"{x:,.0f}"))
ax6.grid(True, alpha=0.3)
plt.setp(ax6.xaxis.get_majorticklabels(), rotation=20, ha="right", fontsize=8.5)

fig.suptitle(
    f"AI 기반 투자 판단 시스템  |  {name} ({TICKER})\n"
    f"정확도: {acc:.4f}   에포크: {len(history.history['loss'])}회   "
    f"선택 피처: {n_features}개   버핏:{B_SCORE:.2f}   린치:{L_SCORE:.2f}",
    fontsize=13, fontweight="bold", color=NAVY, y=0.998
)
plt.savefig(img_path, dpi=150, bbox_inches="tight", facecolor="white")
plt.close()
print(f"\n  그래프 저장 완료: {img_path}")


# ── 10. 최신 데이터로 오늘 예측 ─────────────────────────
latest_raw = df_model[FEATURES].iloc[[-1]].values
latest_sel = selector.transform(latest_raw)
latest_X   = scaler.transform(latest_sel)
latest_prob = model.predict(latest_X, verbose=0)[0]
latest_pred = int(np.argmax(latest_prob))

try:
    td = tk.history(period="1d")
    latest_price = float(td["Close"].iloc[-1])
    price_date   = str(td.index[-1].date())
except Exception:
    latest_price = float(df_model["Close"].iloc[-1])
    price_date   = str(df_model["Date"].iloc[-1].date())

verdict_map = {
    0: "[매도] 단기 하락 가능성 높음",
    1: "[관망] 방향성 불확실, 추이 확인 권장",
    2: "[매수] 단기 상승 가능성 높음",
}

print("\n" + "=" * 55)
print(f"  {name} ({TICKER})  투자 판단 리포트")
print("=" * 55)
print(f"""
  기준일   :  {price_date}
  현재가   :  {latest_price:,.2f}

  최종 판단 :  {verdict_map[latest_pred]}
  매도 확률 :  {latest_prob[0]*100:>6.2f}%
  관망 확률 :  {latest_prob[1]*100:>6.2f}%
  매수 확률 :  {latest_prob[2]*100:>6.2f}%

  --- 투자 전략 점수 ---
  워렌 버핏 (가치투자)  {score_bar(B_SCORE)}
  피터 린치 (성장주)    {score_bar(L_SCORE)}

  --- 입력 재무지표 ---
  PER={per_raw}   PBR={pbr_raw}   PSR={psr_raw}

  --- 모델 정확도 ---
  TensorFlow 신경망 :  {acc:.4f}
  학습 에포크       :  {len(history.history["loss"])}회
  선택된 피처       :  {n_features}개 / {len(FEATURES)}개

  그래프 저장 위치:
  {img_path}

  * 본 시스템은 학습 목적의 보조 도구입니다.
""")
